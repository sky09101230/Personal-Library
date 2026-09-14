import logging

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q

from apps.box_upload.models import UploadedDocument

from .models import DocumentAnalysis, DocumentProcessingJob
from .overview import OVERVIEW_SCHEMA_VERSION
from .versions import DEFAULT_PARSER_NAME, PROMPT_VERSION, current_versions, versions_for


logger = logging.getLogger(__name__)
ACTIVE_STATUSES = (DocumentProcessingJob.Status.QUEUED, DocumentProcessingJob.Status.RUNNING)


def enqueue_processing(
    uploaded_document,
    *,
    force=False,
    parser_name=DEFAULT_PARSER_NAME,
    queue_lane=DocumentProcessingJob.QueueLane.BACKFILL,
):
    upload_id = getattr(uploaded_document, "pk", uploaded_document)
    with transaction.atomic():
        upload = UploadedDocument.objects.select_for_update().get(pk=upload_id)
        if not _is_eligible(upload):
            return None, False

        active = upload.processing_jobs.filter(status__in=ACTIVE_STATUSES).order_by("created_at", "pk").first()
        if active is not None:
            return active, False

        versions = versions_for(parser_name)
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
                    queue_lane=queue_lane,
                    parser_name=parser_name,
                    **versions,
                )
        except IntegrityError:
            active = upload.processing_jobs.filter(status__in=ACTIVE_STATUSES).first()
            if active is None:
                raise
            return active, False
        return job, True


def enqueue_processing_safely(
    uploaded_document,
    *,
    parser_name=DEFAULT_PARSER_NAME,
    queue_lane=DocumentProcessingJob.QueueLane.BACKFILL,
):
    try:
        job, _ = enqueue_processing(
            uploaded_document,
            parser_name=parser_name,
            queue_lane=queue_lane,
        )
    except Exception:
        logger.exception("Could not enqueue literature processing for upload %s.", uploaded_document)
        return None
    return job


def backfill_processing(
    *,
    limit=100,
    force=False,
    parser_name=DEFAULT_PARSER_NAME,
    queue_lane=DocumentProcessingJob.QueueLane.BACKFILL,
    on_progress=None,
):
    limit = max(0, int(limit))
    if not limit:
        return {"created": 0, "reused": 0}

    uploads = UploadedDocument.objects.filter(
        status=UploadedDocument.Status.UPLOADED,
        file_role=UploadedDocument.FileRole.PRIMARY,
    ).order_by("pk")
    if not force:
        versions = versions_for(parser_name)
        covered = DocumentProcessingJob.objects.filter(
            uploaded_document_id=OuterRef("pk"),
            status__in=(*ACTIVE_STATUSES, DocumentProcessingJob.Status.SUCCEEDED),
            parser_name=parser_name,
            **versions,
        )
        uploads = uploads.annotate(is_covered=Exists(covered)).filter(is_covered=False)

    selected_uploads = uploads[:limit]
    total = selected_uploads.count()
    created = 0
    reused = 0
    if on_progress is not None:
        on_progress(current=0, total=total, created=created, reused=reused)
    for current, upload in enumerate(selected_uploads, start=1):
        job, was_created = enqueue_processing(
            upload,
            force=force,
            parser_name=parser_name,
            queue_lane=queue_lane,
        )
        if job is not None:
            if was_created:
                created += 1
            else:
                reused += 1
        if on_progress is not None:
            on_progress(current=current, total=total, created=created, reused=reused)
    return {"created": created, "reused": reused}


def processing_status():
    uploads = UploadedDocument.objects.filter(
        status=UploadedDocument.Status.UPLOADED,
        file_role=UploadedDocument.FileRole.PRIMARY,
    )
    successful_overviews = DocumentAnalysis.objects.filter(
        analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
        document_parse__job__uploaded_document_id=OuterRef("pk"),
        document_parse__job__status=DocumentProcessingJob.Status.SUCCEEDED,
    )
    overview_counts = uploads.annotate(
        has_v2=Exists(successful_overviews.filter(
            schema_version=OVERVIEW_SCHEMA_VERSION,
            prompt_version=PROMPT_VERSION,
        )),
        has_v1=Exists(successful_overviews.filter(schema_version="plab.overview.v1")),
    ).aggregate(
        total=Count("pk"),
        v2=Count("pk", filter=Q(has_v2=True)),
        v1_only=Count("pk", filter=Q(has_v2=False, has_v1=True)),
        unprocessed=Count("pk", filter=Q(has_v2=False, has_v1=False)),
    )
    covered = DocumentProcessingJob.objects.filter(
        uploaded_document_id=OuterRef("pk"),
        status__in=(*ACTIVE_STATUSES, DocumentProcessingJob.Status.SUCCEEDED),
        **current_versions(),
    )
    job_counts = {
        row["status"]: row["count"]
        for row in DocumentProcessingJob.objects.values("status").annotate(count=Count("pk"))
    }
    lane_counts = {
        lane: {
            status: DocumentProcessingJob.objects.filter(
                queue_lane=lane,
                status=status,
            ).count()
            for status in ACTIVE_STATUSES
        }
        for lane in DocumentProcessingJob.QueueLane.values
    }
    return {
        "uploads": overview_counts["total"],
        "uncovered": uploads.annotate(is_covered=Exists(covered)).filter(is_covered=False).count(),
        "overview": {
            "v2": overview_counts["v2"],
            "v1_only": overview_counts["v1_only"],
            "unprocessed": overview_counts["unprocessed"],
        },
        "jobs": {
            status: job_counts.get(status, 0)
            for status in (
                DocumentProcessingJob.Status.QUEUED,
                DocumentProcessingJob.Status.RUNNING,
                DocumentProcessingJob.Status.SUCCEEDED,
                DocumentProcessingJob.Status.FAILED,
            )
        },
        "lanes": lane_counts,
    }


def _is_eligible(upload):
    return (
        upload.status == UploadedDocument.Status.UPLOADED
        and upload.file_role == UploadedDocument.FileRole.PRIMARY
    )
