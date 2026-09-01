from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from .models import DocumentAnalysis, DocumentParse, DocumentProcessingJob


_STATUS_LABELS = {
    DocumentProcessingJob.Status.QUEUED: "等待处理",
    DocumentProcessingJob.Status.RUNNING: "处理中",
    DocumentProcessingJob.Status.SUCCEEDED: "处理完成",
    DocumentProcessingJob.Status.FAILED: "处理失败",
}
_STAGE_LABELS = {
    DocumentProcessingJob.Stage.QUEUED: "排队",
    DocumentProcessingJob.Stage.DOWNLOAD: "读取 PDF",
    DocumentProcessingJob.Stage.PARSE: "解析 PDF",
    DocumentProcessingJob.Stage.CHUNK: "生成文本片段",
    DocumentProcessingJob.Stage.OVERVIEW: "生成 AI Overview",
    DocumentProcessingJob.Stage.COMPLETE: "完成",
}


@login_required
@require_GET
def literature_detail(request, document_id):
    literature = get_object_or_404(CanonicalDocument, pk=document_id)
    jobs = DocumentProcessingJob.objects.filter(
        uploaded_document__canonical_document=literature,
        uploaded_document__status=UploadedDocument.Status.UPLOADED,
        uploaded_document__file_role=UploadedDocument.FileRole.PRIMARY,
    ).select_related("uploaded_document")
    latest_job = jobs.first()
    successful_job = jobs.filter(status=DocumentProcessingJob.Status.SUCCEEDED).first()
    result_parse = _job_parse(successful_job) or _job_parse(jobs.exclude(document_parse=None).first())
    overview = None
    pages = []
    if result_parse is not None:
        overview = result_parse.analyses.filter(
            analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
        ).first()
        pages = _group_chunks_by_page(result_parse)

    source_upload = result_parse.uploaded_document if result_parse else _primary_upload(literature)
    processing_state = {
        "label": _STATUS_LABELS.get(latest_job.status, latest_job.status) if latest_job else "尚未排队",
        "stage": _STAGE_LABELS.get(latest_job.stage, latest_job.stage) if latest_job else "—",
        "failed": bool(latest_job and latest_job.status == DocumentProcessingJob.Status.FAILED),
    }
    return render(
        request,
        "literature_processing/detail.html",
        {
            "literature": literature,
            "latest_job": latest_job,
            "processing_state": processing_state,
            "result_parse": result_parse,
            "overview": overview,
            "pages": pages,
            "source_upload": source_upload,
        },
    )


def _job_parse(job):
    if job is None:
        return None
    try:
        return job.document_parse
    except DocumentParse.DoesNotExist:
        return None


def _primary_upload(literature):
    return literature.uploads.filter(
        status=UploadedDocument.Status.UPLOADED,
        file_role=UploadedDocument.FileRole.PRIMARY,
    ).first()


def _group_chunks_by_page(document_parse):
    pages = []
    current = None
    for chunk in document_parse.chunks.order_by("sequence"):
        if current is None or current["number"] != chunk.page_number:
            current = {"number": chunk.page_number, "chunks": []}
            pages.append(current)
        current["chunks"].append(chunk)
    return pages
