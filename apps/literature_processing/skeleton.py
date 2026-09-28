"""Paper Skeleton analysis generation and validation."""

import hashlib
import json
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .evidence import validate_claims
from .models import DocumentAnalysis, PaperAnalysisRun
from .paper_context import build_skeleton_context


SKELETON_SCHEMA_VERSION = "personal.paper-skeleton.v1"
SKELETON_PROMPT_VERSION = "paper-skeleton-v1"
SECTION_KEYS = ("introduction", "motivation", "gap", "proposed_idea", "method", "experiments", "results", "conclusion")


class SkeletonError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def generate_skeleton(document_parse, user, *, provider=None, force=False, request_id=None, catalog=None):
    from .evidence import build_catalog
    catalog = catalog or build_catalog(document_parse)
    context = build_skeleton_context(catalog, budget=3000)
    generation_key = hashlib.sha256(json.dumps({"parse": document_parse.pk, "artifact": document_parse.artifact_sha256,
                                                "context": context, "prompt": SKELETON_PROMPT_VERSION}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    request_id = request_id or uuid.uuid4().hex
    existing = PaperAnalysisRun.objects.filter(requested_by=user, request_id=request_id).first()
    if existing is not None:
        return existing
    if not force:
        cached = PaperAnalysisRun.objects.filter(document_parse=document_parse, generation_key=generation_key,
                                                  status=PaperAnalysisRun.Status.SUCCEEDED).select_related("result").first()
        if cached is not None:
            return cached
    now = timezone.now()
    with transaction.atomic():
        run = PaperAnalysisRun.objects.create(document_parse=document_parse, requested_by=user, request_id=request_id,
            generation_key=generation_key, generation_nonce=uuid.uuid4().hex if force else "",
            status=PaperAnalysisRun.Status.RUNNING, started_at=now,
            lease_expires_at=now + timedelta(seconds=120), context_manifest=context)
    try:
        if provider is None:
            raise SkeletonError("provider_unavailable", "Paper LLM provider is unavailable.")
        provider_context = {**context, "coverage": {
            "partial": context["coverage"].get("partial", False),
            "omitted_figures": context["coverage"].get("omitted_figures", []),
        }}
        messages = [{"role": "system", "content": _prompt()},
                    {"role": "user", "content": json.dumps(provider_context, ensure_ascii=False)}]
        try:
            result = provider("overview", messages, output_mode="json", max_tokens=512)
        except TypeError:
            result = provider("overview", messages, output_mode="json")
        payload = json.loads(result.content if hasattr(result, "content") else result)
        validate_skeleton_payload(payload)
        allowed = context.get("allowed_evidence_ids", [])
        for section in payload["sections"].values():
            if section.get("claims"):
                validate_claims(catalog, section["claims"], allowed)
        for figure in payload["figures"]:
            for claim in figure.get("claims", []):
                validate_claims(catalog, [claim], allowed)
        analysis = DocumentAnalysis.objects.create(document_parse=document_parse, analysis_type=DocumentAnalysis.AnalysisType.PAPER_SKELETON,
            schema_version=SKELETON_SCHEMA_VERSION, provider=getattr(result, "provider", "paper"),
            model=getattr(result, "returned_model", ""), prompt_version=SKELETON_PROMPT_VERSION,
            input_fingerprint=hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest(), payload=payload)
        run.result = analysis
        run.status = PaperAnalysisRun.Status.SUCCEEDED
        run.provider = getattr(result, "provider", "paper")
        run.requested_model = getattr(result, "requested_model", "")
        run.model = getattr(result, "returned_model", "")
        run.prompt_version = SKELETON_PROMPT_VERSION
        run.schema_version = SKELETON_SCHEMA_VERSION
        run.completed_at = timezone.now()
        run.lease_expires_at = None
        run.save()
        return run
    except Exception as exc:
        run.status = PaperAnalysisRun.Status.FAILED
        run.error_code = (getattr(exc, "code", None) or "generation_failed")[:64]
        run.error_message = str(exc)[:500]
        run.completed_at = timezone.now()
        run.lease_expires_at = None
        run.save(update_fields=("status", "error_code", "error_message", "completed_at", "lease_expires_at"))
        if isinstance(exc, SkeletonError):
            raise
        raise SkeletonError(run.error_code, "Paper Skeleton generation failed.") from exc


def validate_skeleton_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {"language", "sections", "figures", "limitations", "coverage"}:
        raise ValidationError("Paper Skeleton payload fields are invalid.")
    if not isinstance(payload["language"], str) or not payload["language"].strip():
        raise ValidationError("Paper Skeleton language is required.")
    sections = payload["sections"]
    if not isinstance(sections, dict) or set(sections) != set(SECTION_KEYS):
        raise ValidationError("Paper Skeleton sections are incomplete.")
    for section in sections.values():
        if not isinstance(section, dict) or set(section) != {"claims", "status"}:
            raise ValidationError("Paper Skeleton section schema is invalid.")
        if section["status"] not in {"supported", "insufficient_evidence"} or not isinstance(section["claims"], list):
            raise ValidationError("Paper Skeleton section status is invalid.")
    if not isinstance(payload["figures"], list) or len(payload["figures"]) > 100:
        raise ValidationError("Paper Skeleton figures are invalid.")
    for figure in payload["figures"]:
        if not isinstance(figure, dict) or set(figure) != {"evidence_id", "claims", "status"}:
            raise ValidationError("Paper Skeleton figure schema is invalid.")
        if not isinstance(figure["claims"], list) or figure["status"] not in {"supported", "insufficient_evidence"}:
            raise ValidationError("Paper Skeleton figure status is invalid.")
    if not isinstance(payload["limitations"], list) or not isinstance(payload["coverage"], dict):
        raise ValidationError("Paper Skeleton coverage is invalid.")
    return payload


def _prompt():
    return """Return JSON only. Build a paper skeleton from the supplied evidence. Include language, sections with keys introduction/motivation/gap/proposed_idea/method/experiments/results/conclusion, figures, limitations and coverage. Each claim has text, evidence_ids and kind. Use insufficient_evidence when unsupported. Use only supplied evidence IDs."""
