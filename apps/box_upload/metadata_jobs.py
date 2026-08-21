import os
from io import BytesIO

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .ai_metadata import (
    DeepSeekProposalError,
    PROMPT_VERSION,
    ProposalValidationError,
    build_evidence_packet,
    deepseek_configured,
    evidence_fingerprint,
    generate_deepseek_proposal,
)
from .models import CanonicalDocument, MetadataProposal
from .services import LiteratureStorageError
from .storage import open_literature_stream


ACTIVE_STATUSES = (MetadataProposal.Status.QUEUED, MetadataProposal.Status.RUNNING)


def enqueue_metadata_proposal(canonical, requested_by=None, source_upload=None, uploaded_file=None, *, force=False):
    if canonical.metadata_status == CanonicalDocument.MetadataStatus.VERIFIED and not force:
        return None
    active = canonical.metadata_proposals.filter(status__in=ACTIVE_STATUSES).first()
    if active:
        return active
    source_upload = source_upload or canonical.uploads.filter(status="uploaded").first()
    packet = build_evidence_packet(canonical, uploaded_file=uploaded_file)
    configured = deepseek_configured()
    try:
        return MetadataProposal.objects.create(
            canonical_document=canonical,
            source_upload=source_upload,
            status=MetadataProposal.Status.QUEUED if configured else MetadataProposal.Status.FAILED,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash") if configured else "",
            prompt_version=PROMPT_VERSION,
            input_fingerprint=evidence_fingerprint(packet),
            evidence_snapshot=packet,
            error_code="" if configured else "disabled",
            error_message="" if configured else "DeepSeek API key is not configured.",
            completed_at=None if configured else timezone.now(),
            canonical_updated_at=canonical.updated_at,
            requested_by=requested_by,
        )
    except IntegrityError:
        return canonical.metadata_proposals.filter(status__in=ACTIVE_STATUSES).first()


def enqueue_metadata_proposal_safely(*args, **kwargs):
    try:
        return enqueue_metadata_proposal(*args, **kwargs)
    except Exception:
        return None


def queue_existing_metadata_proposals(*, requested_by=None, limit=100, force=False):
    queryset = CanonicalDocument.objects.order_by("created_at")
    if not force:
        queryset = queryset.exclude(metadata_status=CanonicalDocument.MetadataStatus.VERIFIED)
    created = 0
    reused = 0
    for canonical in queryset[:max(0, min(int(limit), 500))]:
        existing_ids = set(canonical.metadata_proposals.filter(status__in=ACTIVE_STATUSES).values_list("id", flat=True))
        proposal = enqueue_metadata_proposal(canonical, requested_by=requested_by, force=force)
        if proposal is None or proposal.id in existing_ids:
            reused += 1
        else:
            created += 1
    return {"created": created, "reused": reused}


def process_next_metadata_proposal(generator=None):
    with transaction.atomic():
        proposal = (
            MetadataProposal.objects.select_for_update()
            .select_related("canonical_document", "source_upload")
            .filter(status=MetadataProposal.Status.QUEUED)
            .order_by("requested_at")
            .first()
        )
        if proposal is None:
            return None
        proposal.status = MetadataProposal.Status.RUNNING
        proposal.started_at = timezone.now()
        proposal.error_code = ""
        proposal.error_message = ""
        proposal.save(update_fields=("status", "started_at", "error_code", "error_message"))

    try:
        packet = _ensure_page_evidence(proposal)
        result = (generator or generate_deepseek_proposal)(packet)
    except DeepSeekProposalError as exc:
        _fail_proposal(proposal, exc.code, str(exc), attempts=2 if exc.retryable else 1)
    except ProposalValidationError as exc:
        _fail_proposal(proposal, "invalid_proposal", str(exc), attempts=1)
    except Exception:
        _fail_proposal(proposal, "worker_error", "Metadata proposal worker failed.", attempts=1)
    else:
        proposal.status = MetadataProposal.Status.SUCCEEDED
        proposal.evidence_snapshot = packet
        proposal.input_fingerprint = evidence_fingerprint(packet)
        proposal.proposal = result["proposal"]
        proposal.validation_warnings = result.get("warnings") or []
        proposal.model = result.get("model") or proposal.model
        proposal.prompt_version = result.get("prompt_version") or proposal.prompt_version
        proposal.attempt_count = result.get("attempt_count") or 1
        proposal.completed_at = timezone.now()
        proposal.save(update_fields=(
            "status",
            "evidence_snapshot",
            "input_fingerprint",
            "proposal",
            "validation_warnings",
            "model",
            "prompt_version",
            "attempt_count",
            "completed_at",
        ))
    return proposal


def _ensure_page_evidence(proposal):
    packet = proposal.evidence_snapshot or build_evidence_packet(proposal.canonical_document)
    if packet.get("pdf", {}).get("pages") or proposal.source_upload is None:
        return packet
    try:
        pdf_file = _download_source_pdf(proposal.source_upload)
    except (LiteratureStorageError, OSError, ValueError):
        return packet
    return build_evidence_packet(proposal.canonical_document, uploaded_file=pdf_file)


def _download_source_pdf(upload):
    limit = int(os.environ.get("MCP_MAX_UPLOAD_BYTES", getattr(settings, "MCP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)))
    stream = open_literature_stream(upload)
    content = bytearray()
    try:
        for chunk in stream.iter_chunks():
            content.extend(chunk)
            if len(content) > limit:
                raise ValueError("PDF is too large for metadata extraction.")
    finally:
        stream.close()
    if len(content) > limit:
        raise ValueError("PDF is too large for metadata extraction.")
    return BytesIO(bytes(content))


def _fail_proposal(proposal, code, message, *, attempts):
    proposal.status = MetadataProposal.Status.FAILED
    proposal.error_code = code[:64]
    proposal.error_message = message[:2000]
    proposal.attempt_count = attempts
    proposal.completed_at = timezone.now()
    proposal.save(update_fields=("status", "error_code", "error_message", "attempt_count", "completed_at"))
