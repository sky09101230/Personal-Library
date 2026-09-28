"""Deterministic, parse-scoped evidence projection."""

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re

from django.core.exceptions import PermissionDenied, ValidationError

from apps.box_upload.models import CanonicalDocument, UploadedDocument
from apps.box_upload.storage import get_literature_storage

from .models import DocumentParse, LiteratureChunk


EVIDENCE_SCHEMA_VERSION = "personal.evidence.v1"
EVIDENCE_BUILDER_VERSION = "evidence-catalog-v1"
_FIGURE_LABEL = re.compile(r"\b(?:fig(?:ure)?|图)\.?\s*(\d+(?:\s*[a-z])?)\b", re.I)


class EvidenceError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    kind: str
    parse_id: int
    artifact_sha256: str
    text: str
    pages: tuple[int, ...]
    section_path: tuple[str, ...] = ()
    chunk_ids: tuple[int, ...] = ()
    block_ids: tuple[str, ...] = ()
    source_spans: tuple[dict, ...] = ()
    bbox: dict | None = None
    figure_label: str = ""
    caption_evidence_ids: tuple[str, ...] = ()
    mention_evidence_ids: tuple[str, ...] = ()
    asset_handle: dict | None = None
    availability: str = "available"
    locator: tuple = ()

    def as_dict(self):
        return asdict(self)


class EvidenceCatalog:
    def __init__(self, document_parse, items):
        self.document_parse = document_parse
        self.items = tuple(items)
        self.by_id = {item.evidence_id: item for item in self.items}

    def get(self, evidence_id):
        item = self.by_id.get(evidence_id)
        if item is None:
            raise EvidenceError("unknown_evidence", "Evidence does not belong to this parse.")
        return item

    @property
    def evidence_ids(self):
        return frozenset(self.by_id)

    def allowlist(self, evidence_ids):
        ids = frozenset(evidence_ids)
        if not ids <= self.evidence_ids:
            raise EvidenceError("unknown_evidence", "Evidence allowlist contains an unknown ID.")
        return ids


def select_active_parse(user, document_id, parse_id=None):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication is required.")
    document = CanonicalDocument.objects.filter(
        pk=document_id, index_status=CanonicalDocument.IndexStatus.PUBLISHED,
    ).first()
    if document is None:
        raise EvidenceError("unavailable", "Published literature is unavailable.")
    uploads = UploadedDocument.objects.filter(
        canonical_document=document, status=UploadedDocument.Status.UPLOADED,
        file_role=UploadedDocument.FileRole.PRIMARY,
    )
    parses = DocumentParse.objects.filter(job__uploaded_document__in=uploads).select_related("job")
    if parse_id is not None:
        parse = parses.filter(pk=parse_id).first()
        if parse is None or not _parse_usable(parse):
            raise EvidenceError("unavailable", "Requested parse is unavailable.")
        return parse
    parse = parses.filter(job__status="succeeded").order_by("-created_at", "-pk").first()
    if parse is None:
        parse = parses.filter(job__stage="overview").order_by("-created_at", "-pk").first()
    if parse is None or not _parse_usable(parse):
        raise EvidenceError("unavailable", "No complete parse is available.")
    return parse


def build_catalog(document_parse):
    if not _parse_usable(document_parse):
        raise EvidenceError("invalid_parse", "Parse is not complete or its source upload is unavailable.")
    items = []
    chunks = list(LiteratureChunk.objects.filter(document_parse=document_parse).order_by("sequence"))
    for chunk in chunks:
        locator = ("chunk", chunk.pk, chunk.content_sha256, chunk.start_offset, chunk.end_offset)
        items.append(_make_evidence(document_parse, "text", chunk.text, (chunk.page_number,),
                                    section_path=tuple(chunk.section_path or ()), chunk_ids=(chunk.pk,),
                                    source_spans=tuple(chunk.source_spans or ()), locator=locator))
    for block in _structured_blocks(document_parse):
        kind = {
            "figure": "figure", "figure_caption": "text", "table": "table", "equation": "equation",
            "heading": "text", "paragraph": "text",
        }.get(block.get("type"), "text")
        text = str(block.get("text") or "")
        content = block.get("structured_content") or {}
        asset = None
        if kind == "figure":
            asset_path = content.get("asset_path")
            asset = {"segment_index": (block.get("source") or {}).get("segment_index"), "asset_path": asset_path} if asset_path else None
        locator = ("block", block.get("block_id"), block.get("page_number"), text, kind)
        items.append(_make_evidence(document_parse, kind, text, (block.get("page_number"),),
                                    section_path=tuple(block.get("section_path") or ()), block_ids=(block.get("block_id"),),
                                    bbox=block.get("bbox"), asset_handle=asset, availability="available" if asset or kind != "figure" else "asset_unavailable",
                                    locator=locator))
    figures = [item for item in items if item.kind == "figure"]
    captions = [item for item in items if item.kind == "text" and item.block_ids and _looks_like_caption(item.text)]
    texts = [item for item in items if item.kind == "text"]
    if figures:
        enriched = []
        for item in items:
            if item.kind != "figure":
                enriched.append(item)
                continue
            same_page = [caption for caption in captions if set(caption.pages) & set(item.pages)]
            caption = same_page[0] if len(same_page) == 1 else None
            label = _figure_label(caption.text) if caption else ""
            mentions = tuple(text.evidence_id for text in texts if label and label in _figure_labels(text.text))
            enriched.append(replace(item, figure_label=label,
                                    caption_evidence_ids=(caption.evidence_id,) if caption else (),
                                    mention_evidence_ids=mentions,
                                    availability=item.availability if caption or item.asset_handle else "degraded"))
        items = enriched
    return EvidenceCatalog(document_parse, items)


def validate_claims(catalog, claims, allowed_evidence_ids):
    allowed = catalog.allowlist(allowed_evidence_ids)
    if not isinstance(claims, list):
        raise ValidationError("Claims must be a list.")
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"text", "evidence_ids", "kind"}:
            raise ValidationError("Claim schema is invalid.")
        if not isinstance(claim["text"], str) or not claim["text"].strip():
            raise ValidationError("Claim text is required.")
        ids = claim["evidence_ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 8 or not set(ids) <= allowed:
            raise ValidationError("Claim evidence is not in the current allowlist.")
        if claim["kind"] not in {"finding", "interpretation", "limitation"}:
            raise ValidationError("Claim kind is invalid.")
    return claims


def _make_evidence(parse, kind, text, pages, *, section_path=(), chunk_ids=(), block_ids=(), source_spans=(), bbox=None,
                   figure_label="", caption_evidence_ids=(), mention_evidence_ids=(), asset_handle=None,
                   availability="available", locator=()):
    canonical = json.dumps((parse.pk, parse.artifact_sha256, EVIDENCE_BUILDER_VERSION, locator), ensure_ascii=False, sort_keys=True, default=str)
    evidence_id = f"ev1:{parse.pk}:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
    return Evidence(evidence_id, kind, parse.pk, parse.artifact_sha256, text, tuple(pages), tuple(section_path),
                    tuple(chunk_ids), tuple(block_ids), tuple(source_spans), bbox, figure_label,
                    tuple(caption_evidence_ids), tuple(mention_evidence_ids), asset_handle, availability, tuple(locator))


def _looks_like_caption(text):
    return bool(re.match(r"\s*(?:fig(?:ure)?|图)\.?\s*\d+", text, re.I))


def _figure_label(text):
    match = _FIGURE_LABEL.search(text or "")
    return match.group(1).replace(" ", "") if match else ""


def _figure_labels(text):
    return {match.group(1).replace(" ", "") for match in _FIGURE_LABEL.finditer(text or "")}


def _parse_usable(parse):
    return bool(parse and parse.page_count > 0 and parse.job.uploaded_document.status == UploadedDocument.Status.UPLOADED
                and parse.job.uploaded_document.file_role == UploadedDocument.FileRole.PRIMARY
                and parse.job.uploaded_document.canonical_document.index_status == CanonicalDocument.IndexStatus.PUBLISHED)


def _structured_blocks(parse):
    if parse.schema_version != "plab.parse.v2":
        return ()
    try:
        stream = get_literature_storage(parse.artifact_storage_backend).open_stream(parse.artifact_path)
        raw = b"".join(stream.iter_chunks())
        stream.close()
        payload = json.loads(raw)
    except Exception:
        return ()
    blocks = []
    for page in payload.get("pages", []):
        for block in page.get("blocks", []):
            blocks.append(block)
    return tuple(blocks)
