import hashlib
import json

from .models import DocumentAnalysis
from .overview_provider import OverviewGenerationError, generate_deepseek_overview
from .versions import PROMPT_VERSION


OVERVIEW_SCHEMA_VERSION = "plab.overview.v1"
OVERVIEW_INPUT_MAX_CHARS = 80_000


def build_overview_packet(document_parse, *, max_chars=OVERVIEW_INPUT_MAX_CHARS):
    chunks = []
    remaining = max(0, int(max_chars))
    truncated = False
    for chunk in document_parse.chunks.order_by("sequence"):
        if remaining <= 0:
            truncated = True
            break
        text = chunk.text[:remaining]
        chunks.append(
            {
                "chunk_id": chunk.pk,
                "chunk_key": chunk.chunk_key,
                "page": chunk.page_number,
                "text": text,
            }
        )
        remaining -= len(text)
        if len(text) < len(chunk.text):
            truncated = True
            break
    if not chunks:
        raise OverviewGenerationError("no_text", "No parsed text is available for an overview.")
    return {
        "schema_version": OVERVIEW_SCHEMA_VERSION,
        "parse_id": document_parse.pk,
        "truncated": truncated,
        "chunks": chunks,
    }


def overview_input_fingerprint(packet):
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def generate_and_persist_overview(document_parse, *, generator=generate_deepseek_overview):
    packet = build_overview_packet(document_parse)
    generated = generator(packet)
    return DocumentAnalysis.objects.create(
        document_parse=document_parse,
        analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
        schema_version=OVERVIEW_SCHEMA_VERSION,
        provider=generated["provider"],
        model=generated["model"],
        prompt_version=generated.get("prompt_version") or PROMPT_VERSION,
        input_fingerprint=overview_input_fingerprint(packet),
        payload=generated["payload"],
    )

