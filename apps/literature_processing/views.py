from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from .models import DocumentAnalysis, DocumentParse, DocumentProcessingJob
from .skeleton import has_supported_claims


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
_PROVIDER_STATE_LABELS = {
    "download": "读取原始 PDF",
    "parse": "准备解析",
    "allocating": "创建 MinerU 任务",
    "uploading": "上传至 MinerU",
    "pending": "MinerU 排队中",
    "running": "MinerU 解析中",
    "converting": "MinerU 转换中",
    "downloading": "下载 MinerU 结果",
    "normalizing": "转换文献结构",
    "chunking": "生成文本片段",
    "overview": "生成 AI Overview",
    "complete": "处理完成",
    "failed": "处理失败",
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
    skeleton = None
    pages = []
    if result_parse is not None:
        overview = result_parse.analyses.filter(
            analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
        ).first()
        skeleton = result_parse.analyses.filter(
            analysis_type=DocumentAnalysis.AnalysisType.PAPER_SKELETON,
        ).first()
        pages = _group_chunks_by_page(result_parse)

    source_upload = result_parse.uploaded_document if result_parse else _primary_upload(literature)
    processing_state = _processing_state(latest_job)
    return render(
        request,
        "literature_processing/detail.html",
        {
            "literature": literature,
            "latest_job": latest_job,
            "processing_state": processing_state,
            "result_parse": result_parse,
            "overview": overview,
            "skeleton": skeleton,
            "paper_ai_enabled": literature.index_status == CanonicalDocument.IndexStatus.PUBLISHED,
            "skeleton_empty": bool(skeleton and not has_supported_claims(skeleton.payload)),
            "skeleton_sections": [(label, (skeleton.payload.get("sections") or {}).get(key, {})) for key, label in (
                ("introduction", "研究背景"), ("motivation", "研究动机"), ("gap", "现有工作的不足"),
                ("proposed_idea", "核心思路"), ("method", "方法与架构"), ("experiments", "实验设置"),
                ("results", "主要结果"), ("conclusion", "结论"))] if skeleton else [],
            "pages": pages,
            "source_upload": source_upload,
        },
    )


@login_required
@require_GET
def literature_processing_status(request, document_id):
    literature = get_object_or_404(CanonicalDocument, pk=document_id)
    latest_job = (
        DocumentProcessingJob.objects.filter(
            uploaded_document__canonical_document=literature,
            uploaded_document__status=UploadedDocument.Status.UPLOADED,
            uploaded_document__file_role=UploadedDocument.FileRole.PRIMARY,
        )
        .select_related("uploaded_document")
        .first()
    )
    return JsonResponse(_processing_state(latest_job, include_machine_values=True))


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


def _processing_state(job, *, include_machine_values=False):
    if job is None:
        state = {
            "label": "尚未排队",
            "stage": "—",
            "failed": False,
            "terminal": True,
            "progress_current": None,
            "progress_total": None,
            "progress_unit": "",
            "progress_percent": None,
            "error_message": "",
        }
        if include_machine_values:
            state.update({"job_id": None, "status": "not_queued", "provider_state": ""})
        return state

    progress_percent = None
    if job.progress_total and job.progress_current is not None:
        progress_percent = min(100, round(job.progress_current * 100 / job.progress_total))
    provider_stage = _PROVIDER_STATE_LABELS.get(job.provider_state)
    state = {
        "label": _STATUS_LABELS.get(job.status, job.status),
        "stage": provider_stage or _STAGE_LABELS.get(job.stage, job.stage),
        "failed": job.status == DocumentProcessingJob.Status.FAILED,
        "terminal": job.status in {
            DocumentProcessingJob.Status.SUCCEEDED,
            DocumentProcessingJob.Status.FAILED,
        },
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "progress_unit": job.progress_unit,
        "progress_percent": progress_percent,
        "error_message": job.error_message if job.status == DocumentProcessingJob.Status.FAILED else "",
    }
    if include_machine_values:
        state.update({
            "job_id": job.pk,
            "status": job.status,
            "provider_state": job.provider_state,
            "parser_name": job.parser_name,
            "queue_lane": job.queue_lane,
            "updated_at": job.updated_at.isoformat(),
            "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        })
    return state
