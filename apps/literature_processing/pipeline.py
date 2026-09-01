import logging
from tempfile import SpooledTemporaryFile

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.box_upload.storage import open_literature_stream

from .models import DocumentProcessingJob
from .overview import generate_and_persist_overview
from .parsers import parse_pdf
from .persistence import persist_parsed_document
from .versions import PARSER_NAME


logger = logging.getLogger(__name__)


class SourcePdfTooLarge(ValueError):
    pass


def claim_next_job():
    with transaction.atomic():
        job = (
            DocumentProcessingJob.objects.select_for_update()
            .select_related("uploaded_document", "uploaded_document__canonical_document")
            .filter(status=DocumentProcessingJob.Status.QUEUED)
            .order_by("created_at", "pk")
            .first()
        )
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
        )
        if not updated:
            return None
    return DocumentProcessingJob.objects.select_related(
        "uploaded_document", "uploaded_document__canonical_document"
    ).get(pk=job.pk)


def process_next_job(*, downloader=None, parser=None, persister=None, overview_processor=None):
    job = claim_next_job()
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
        parsed_document = parser(source, parser_name=PARSER_NAME)
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
        job.save(update_fields=("status", "stage", "completed_at", "updated_at"))
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
    job.save(update_fields=("stage", "updated_at"))


def _mark_failed(job, error):
    failed_stage = job.stage
    job.status = DocumentProcessingJob.Status.FAILED
    detail_code = getattr(error, "code", "failed")
    job.error_code = f"{failed_stage}_{detail_code}"[:64]
    job.error_message = f"Literature processing failed during {failed_stage}."
    job.completed_at = timezone.now()
    job.save(update_fields=("status", "error_code", "error_message", "completed_at", "updated_at"))
