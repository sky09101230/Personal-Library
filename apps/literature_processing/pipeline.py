import logging
from tempfile import SpooledTemporaryFile

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.box_upload.storage import open_literature_stream

from .models import DocumentProcessingJob
from .overview import generate_and_persist_overview
from .parsers import parse_pdf
from .parsers.mineru import use_mineru_progress_callback
from .persistence import persist_parsed_document


logger = logging.getLogger(__name__)


class SourcePdfTooLarge(ValueError):
    pass


def claim_next_job(*, queue_lane=None, worker_channel=""):
    with transaction.atomic():
        lock_options = {"skip_locked": True} if connection.features.has_select_for_update_skip_locked else {}
        jobs = (
            DocumentProcessingJob.objects.select_for_update(**lock_options)
            .select_related("uploaded_document", "uploaded_document__canonical_document")
            .filter(status=DocumentProcessingJob.Status.QUEUED)
            .order_by("created_at", "pk")
        )
        if queue_lane:
            jobs = jobs.filter(queue_lane=queue_lane)
        job = jobs.first()
        if job is None:
            return None
        updated = DocumentProcessingJob.objects.filter(
            pk=job.pk,
            status=DocumentProcessingJob.Status.QUEUED,
        ).update(
            status=DocumentProcessingJob.Status.RUNNING,
            stage=DocumentProcessingJob.Stage.DOWNLOAD,
            started_at=timezone.now(),
            attempt_count=job.attempt_count + 1,
            error_code="",
            error_message="",
            provider_state="download",
            provider_batch_id="",
            progress_current=None,
            progress_total=None,
            progress_unit="",
            worker_channel=worker_channel,
            heartbeat_at=timezone.now(),
        )
        if not updated:
            return None
    return DocumentProcessingJob.objects.select_related(
        "uploaded_document", "uploaded_document__canonical_document"
    ).get(pk=job.pk)


def process_next_job(
    *,
    queue_lane=None,
    worker_channel="",
    downloader=None,
    parser=None,
    persister=None,
    overview_processor=None,
):
    job = claim_next_job(queue_lane=queue_lane, worker_channel=worker_channel)
    if job is None:
        return None
    downloader = downloader or download_source_pdf
    parser = parser or parse_pdf
    persister = persister or persist_parsed_document
    overview_processor = overview_processor or generate_and_persist_overview

    source = None
    try:
        source = downloader(job.uploaded_document)
        _set_stage(job, DocumentProcessingJob.Stage.PARSE)
        with use_mineru_progress_callback(lambda event: _update_provider_progress(job, event)):
            parsed_document = parser(source, parser_name=job.parser_name)
        _set_stage(job, DocumentProcessingJob.Stage.CHUNK)
        document_parse = persister(job, parsed_document)
        _set_stage(job, DocumentProcessingJob.Stage.OVERVIEW)
        overview_processor(document_parse)
    except Exception as exc:
        logger.exception("Literature processing job %s failed during %s.", job.pk, job.stage)
        _mark_failed(job, exc)
    else:
        job.status = DocumentProcessingJob.Status.SUCCEEDED
        job.stage = DocumentProcessingJob.Stage.COMPLETE
        job.completed_at = timezone.now()
        job.provider_state = "complete"
        job.heartbeat_at = job.completed_at
        job.save(
            update_fields=(
                "status",
                "stage",
                "provider_state",
                "heartbeat_at",
                "completed_at",
                "updated_at",
            )
        )
    finally:
        if source is not None:
            source.close()
    return job


def download_source_pdf(uploaded_document, *, max_bytes=None, stream_opener=open_literature_stream):
    max_bytes = max_bytes or getattr(settings, "MCP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)
    stream = stream_opener(uploaded_document)
    target = SpooledTemporaryFile(max_size=min(max_bytes, 8 * 1024 * 1024), mode="w+b")
    size = 0
    try:
        for chunk in stream.iter_chunks():
            size += len(chunk)
            if size > max_bytes:
                raise SourcePdfTooLarge("Source PDF exceeds the processing size limit.")
            target.write(chunk)
    except Exception:
        target.close()
        raise
    finally:
        stream.close()
    target.seek(0)
    return target


def _set_stage(job, stage):
    job.stage = stage
    provider_states = {
        DocumentProcessingJob.Stage.PARSE: "parse",
        DocumentProcessingJob.Stage.CHUNK: "chunking",
        DocumentProcessingJob.Stage.OVERVIEW: "overview",
    }
    job.provider_state = provider_states.get(stage, job.provider_state)
    job.heartbeat_at = timezone.now()
    job.save(update_fields=("stage", "provider_state", "heartbeat_at", "updated_at"))


def _mark_failed(job, error):
    failed_stage = job.stage
    job.status = DocumentProcessingJob.Status.FAILED
    detail_code = getattr(error, "code", "failed")
    job.error_code = f"{failed_stage}_{detail_code}"[:64]
    job.error_message = f"Literature processing failed during {failed_stage}."
    job.completed_at = timezone.now()
    job.provider_state = "failed"
    job.heartbeat_at = job.completed_at
    job.save(
        update_fields=(
            "status",
            "provider_state",
            "heartbeat_at",
            "error_code",
            "error_message",
            "completed_at",
            "updated_at",
        )
    )


def _update_provider_progress(job, event):
    allowed_states = {
        "allocating",
        "uploading",
        "pending",
        "running",
        "converting",
        "downloading",
        "normalizing",
    }
    state = event.get("state")
    if state not in allowed_states:
        return
    current = event.get("current")
    total = event.get("total")
    unit = event.get("unit") if event.get("unit") in {"", "pages", "segments"} else ""
    batch_id = event.get("batch_id")
    current = current if isinstance(current, int) and not isinstance(current, bool) and current >= 0 else None
    total = total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None
    batch_id = batch_id if isinstance(batch_id, str) else ""
    now = timezone.now()
    DocumentProcessingJob.objects.filter(pk=job.pk).update(
        provider_state=state,
        provider_batch_id=batch_id[:128],
        progress_current=current,
        progress_total=total,
        progress_unit=unit,
        heartbeat_at=now,
        updated_at=now,
    )
    job.provider_state = state
    job.provider_batch_id = batch_id[:128]
    job.progress_current = current
    job.progress_total = total
    job.progress_unit = unit
    job.heartbeat_at = now
