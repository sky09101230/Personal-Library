import logging

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef

from apps.box_upload.models import UploadedDocument

from .models import DocumentProcessingJob
from .versions import current_versions


logger = logging.getLogger(__name__)
ACTIVE_STATUSES = (DocumentProcessingJob.Status.QUEUED, DocumentProcessingJob.Status.RUNNING)


def enqueue_processing(uploaded_document, *, force=False):
    upload_id = getattr(uploaded_document, "pk", uploaded_document)
    with transaction.atomic():
        upload = UploadedDocument.objects.select_for_update().get(pk=upload_id)
        if not _is_eligible(upload):
            return None, False

        active = upload.processing_jobs.filter(status__in=ACTIVE_STATUSES).order_by("created_at", "pk").first()
        if active is not None:
            return active, False

        versions = current_versions()
        if not force:
            succeeded = upload.processing_jobs.filter(
                status=DocumentProcessingJob.Status.SUCCEEDED,
                **versions,
            ).first()
            if succeeded is not None:
                return succeeded, False

        try:
            with transaction.atomic():
                job = DocumentProcessingJob.objects.create(
                    uploaded_document=upload,
                    status=DocumentProcessingJob.Status.QUEUED,
                    stage=DocumentProcessingJob.Stage.QUEUED,
                    **versions,
                )
        except IntegrityError:
            active = upload.processing_jobs.filter(status__in=ACTIVE_STATUSES).first()
            if active is None:
                raise
            return active, False
        return job, True


def enqueue_processing_safely(uploaded_document):
    try:
        job, _ = enqueue_processing(uploaded_document)
    except Exception:
        logger.exception("Could not enqueue literature processing for upload %s.", uploaded_document)
        return None
    return job


def backfill_processing(*, limit=100, force=False):
    limit = max(0, int(limit))
    if not limit:
        return {"created": 0, "reused": 0}

    uploads = UploadedDocument.objects.filter(
        status=UploadedDocument.Status.UPLOADED,
        file_role=UploadedDocument.FileRole.PRIMARY,
    ).order_by("pk")
    if not force:
        covered = DocumentProcessingJob.objects.filter(
            uploaded_document_id=OuterRef("pk"),
            status__in=(*ACTIVE_STATUSES, DocumentProcessingJob.Status.SUCCEEDED),
            **current_versions(),
        )
        uploads = uploads.annotate(is_covered=Exists(covered)).filter(is_covered=False)

    created = 0
    reused = 0
    for upload in uploads[:limit]:
        job, was_created = enqueue_processing(upload, force=force)
        if job is None:
            continue
        if was_created:
            created += 1
        else:
            reused += 1
    return {"created": created, "reused": reused}


def _is_eligible(upload):
    return (
        upload.status == UploadedDocument.Status.UPLOADED
        and upload.file_role == UploadedDocument.FileRole.PRIMARY
    )

