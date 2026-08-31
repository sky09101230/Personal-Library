from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required

from .forms import BoxUploadForm
from .ingestion import PdfValidationError, associate_existing_pdf, prepare_pdf
from .metadata import (
    BIBTEX_EVIDENCE_LIMIT,
    DOI_PATTERN,
    MetadataResolutionError,
    extract_pdf_evidence,
    fetch_doi_bibtex,
    normalize_doi,
    parse_bibtex_metadata,
    select_pdf_doi,
)
from .models import CanonicalDocument, UploadedDocument, UploadReviewBatch, UploadReviewItem
from .services import LiteratureStorageError
from .storage import delete_literature, get_literature_storage, store_literature


_METADATA_FIELDS = ("title", "authors", "abstract", "journal", "publication_year", "source_tags")


def _issue_for(metadata):
    if not str(metadata.get("title") or "").strip():
        return "missing_title"
    if not str(metadata.get("journal") or "").strip():
        return "missing_journal"
    return "ready"


def _serialize_item(item):
    metadata = item.metadata or {}
    return {
        "id": item.pk,
        "filename": item.original_name,
        "metadata": metadata,
        "issue": _issue_for(metadata),
    }


def _pdf_fallback_metadata(evidence):
    authors = evidence.get("authors") or []
    return {
        "title": str(evidence.get("title") or "").strip(),
        "authors": [author if isinstance(author, dict) else {"name": author} for author in authors],
        "abstract": "",
        "journal": "",
        "publication_year": None,
        "doi": normalize_doi(evidence.get("doi")),
        "source_tags": [],
        "metadata_source": "pdf",
    }


def _bibtex_preview(doi, raw_bibtex=None):
    doi = normalize_doi(doi)
    if not doi or DOI_PATTERN.fullmatch(doi) is None:
        raise MetadataResolutionError("请输入有效 DOI。")
    raw_bibtex = raw_bibtex or fetch_doi_bibtex(doi)
    _, metadata = parse_bibtex_metadata(raw_bibtex, expected_doi=doi)
    metadata["doi"] = doi
    metadata["metadata_source"] = "bibtex"
    return metadata, {
        "doi": doi,
        "raw": raw_bibtex[:BIBTEX_EVIDENCE_LIMIT],
        "raw_truncated": len(raw_bibtex) > BIBTEX_EVIDENCE_LIMIT,
    }


def _preview_pdf(uploaded_file):
    evidence = extract_pdf_evidence(uploaded_file)
    metadata = _pdf_fallback_metadata(evidence)
    preview_evidence = {"pdf": evidence}
    doi = metadata["doi"]
    raw_bibtex = None
    try:
        if len(evidence.get("doi_candidates") or []) > 1:
            doi, raw_bibtex = select_pdf_doi(evidence, bibtex_fetcher=fetch_doi_bibtex)
        if doi:
            resolved, bibtex_evidence = _bibtex_preview(doi, raw_bibtex=raw_bibtex)
            metadata.update({key: value for key, value in resolved.items() if value not in (None, "", [])})
            metadata["doi"] = doi
            preview_evidence["bibtex"] = bibtex_evidence
    except MetadataResolutionError as exc:
        preview_evidence["provider_error"] = str(exc)
    uploaded_file.seek(0)
    return metadata, preview_evidence


def _pending_batch(user, batch_id, lock=False):
    queryset = UploadReviewBatch.objects
    if lock:
        queryset = queryset.select_for_update()
    return get_object_or_404(
        queryset,
        pk=batch_id,
        uploader=user,
        status=UploadReviewBatch.Status.PENDING,
    )


def _pending_item(user, item_id, lock=False):
    queryset = UploadReviewItem.objects.select_related("batch")
    if lock:
        queryset = queryset.select_for_update()
    return get_object_or_404(
        queryset,
        pk=item_id,
        batch__uploader=user,
        batch__status=UploadReviewBatch.Status.PENDING,
    )


@login_required
@require_GET
def upload_page(request):
    return render(request, "box_upload/upload.html", {"form": BoxUploadForm()})


@login_required
@require_POST
def create_batch(request):
    batch = UploadReviewBatch.objects.create(uploader=request.user)
    return JsonResponse({"ok": True, "batch_id": batch.pk})


@login_required
@require_POST
def stage_file(request, batch_id):
    batch = _pending_batch(request.user, batch_id)
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return JsonResponse({"ok": False, "message": "请选择 PDF 文件。"}, status=400)
    try:
        prepared = prepare_pdf(uploaded_file)
        metadata, evidence = _preview_pdf(prepared.uploaded_file)
        stored = store_literature(prepared.uploaded_file)
    except (PdfValidationError, LiteratureStorageError) as exc:
        return JsonResponse({"ok": False, "filename": uploaded_file.name, "message": str(exc)}, status=400)

    try:
        with transaction.atomic():
            batch = _pending_batch(request.user, batch_id, lock=True)
            item = UploadReviewItem.objects.create(
                batch=batch,
                original_name=prepared.filename,
                remote_path=stored.remote_path,
                storage_backend=stored.backend,
                sha256=prepared.sha256,
                size=prepared.size,
                metadata=metadata,
                evidence=evidence,
            )
    except Exception:
        try:
            get_literature_storage(stored.backend).delete(stored.remote_path)
        except LiteratureStorageError:
            pass
        raise
    return JsonResponse({"ok": True, "item": _serialize_item(item)})


@login_required
@require_POST
def update_item(request, item_id):
    action = request.POST.get("action")
    if action == "save_title":
        with transaction.atomic():
            item = _pending_item(request.user, item_id, lock=True)
            metadata = dict(item.metadata or {})
            metadata["title"] = " ".join(request.POST.get("title", "").split())[:500]
            item.metadata = metadata
            item.save(update_fields=("metadata", "updated_at"))
        return JsonResponse({"ok": True, "item": _serialize_item(item)})
    if action != "reparse_doi":
        return JsonResponse({"ok": False, "message": "无效的 metadata 操作。"}, status=400)

    _pending_item(request.user, item_id)
    doi = normalize_doi(request.POST.get("doi"))
    try:
        resolved, bibtex_evidence = _bibtex_preview(doi)
    except MetadataResolutionError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    with transaction.atomic():
        item = _pending_item(request.user, item_id, lock=True)
        metadata = dict(item.metadata or {})
        metadata.update(resolved)
        metadata["doi"] = doi
        evidence = dict(item.evidence or {})
        evidence["bibtex"] = bibtex_evidence
        evidence["doi_override"] = {"value": doi, "source": "uploader"}
        evidence.pop("provider_error", None)
        item.metadata = metadata
        item.evidence = evidence
        item.save(update_fields=("metadata", "evidence", "updated_at"))
    return JsonResponse({"ok": True, "item": _serialize_item(item)})


def _apply_confirmed_metadata(canonical, item):
    metadata = item.metadata or {}
    for field in _METADATA_FIELDS:
        value = metadata.get(field)
        if value not in (None, "", []):
            setattr(canonical, field, value)
    doi = normalize_doi(metadata.get("doi"))
    if doi:
        canonical.doi = doi
        canonical.identifiers = {**canonical.identifiers, "doi": doi}
    canonical.metadata_source = metadata.get("metadata_source") or "uploader"
    canonical.metadata_status = CanonicalDocument.MetadataStatus.VERIFIED
    canonical.metadata_confidence = 1.000
    canonical.metadata_evidence = {
        **(item.evidence or {}),
        "uploader_confirmation": {"user_id": item.batch.uploader_id, "confirmed": True},
    }
    canonical.index_status = CanonicalDocument.IndexStatus.PUBLISHED
    if not canonical.sha256 and not CanonicalDocument.objects.exclude(pk=canonical.pk).filter(sha256=item.sha256).exists():
        canonical.sha256 = item.sha256
    canonical.save()


@login_required
@require_POST
def confirm_batch(request, batch_id):
    cleanup_items = []
    with transaction.atomic():
        batch = _pending_batch(request.user, batch_id, lock=True)
        items = list(batch.items.select_for_update().all())
        if not items:
            return JsonResponse({"ok": False, "message": "该批次没有可确认文件。"}, status=400)
        missing_titles = [item.original_name for item in items if _issue_for(item.metadata or {}) == "missing_title"]
        if missing_titles:
            return JsonResponse({
                "ok": False,
                "message": "仍有文件缺少标题，请先补全：" + "、".join(missing_titles),
            }, status=400)

        results = []
        for item in items:
            metadata = item.metadata or {}
            doi = normalize_doi(metadata.get("doi"))
            canonical = CanonicalDocument.objects.filter(doi__iexact=doi).first() if doi else None
            canonical = canonical or CanonicalDocument.objects.filter(sha256=item.sha256).first()
            if canonical is not None and canonical.uploads.filter(
                status=UploadedDocument.Status.UPLOADED,
                file_role=UploadedDocument.FileRole.PRIMARY,
            ).exists():
                if canonical.metadata_status != CanonicalDocument.MetadataStatus.VERIFIED:
                    _apply_confirmed_metadata(canonical, item)
                association = associate_existing_pdf(canonical, request.user)
                state = "skipped" if association == "skipped" else "merged"
                result = {"state": state, "filename": item.original_name}
                item.commit_result = result
                item.save(update_fields=("commit_result", "updated_at"))
                cleanup_items.append(item)
                results.append(result)
                continue

            if canonical is None:
                canonical = CanonicalDocument.objects.create()
            _apply_confirmed_metadata(canonical, item)
            duplicate_type = (
                UploadedDocument.DuplicateType.EXACT
                if UploadedDocument.objects.filter(sha256=item.sha256).exists()
                else UploadedDocument.DuplicateType.NEW
            )
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=request.user,
                original_name=item.original_name,
                remote_path=item.remote_path,
                storage_backend=item.storage_backend,
                sha256=item.sha256,
                size=item.size,
                content_type=item.content_type,
                file_role=UploadedDocument.FileRole.PRIMARY,
                duplicate_type=duplicate_type,
            )
            result = {"state": "uploaded", "filename": item.original_name, "document_id": canonical.pk}
            item.commit_result = result
            item.save(update_fields=("commit_result", "updated_at"))
            results.append(result)

        batch.status = UploadReviewBatch.Status.COMMITTED
        batch.completed_at = timezone.now()
        batch.save(update_fields=("status", "completed_at", "updated_at"))

    cleanup_failures = []
    for item in cleanup_items:
        try:
            delete_literature(item)
        except LiteratureStorageError:
            cleanup_failures.append(item.original_name)
            result = {**item.commit_result, "cleanup": "failed"}
        else:
            result = {**item.commit_result, "cleanup": "deleted"}
        UploadReviewItem.objects.filter(pk=item.pk).update(commit_result=result)
    return JsonResponse({
        "ok": True,
        "results": results,
        "cleanup_failures": cleanup_failures,
        "message": f"已确认并入库 {len(results)} 个文件。",
    })


@login_required
@require_POST
def cancel_batch(request, batch_id):
    failures = []
    with transaction.atomic():
        batch = _pending_batch(request.user, batch_id, lock=True)
        for item in list(batch.items.select_for_update().all()):
            try:
                delete_literature(item)
            except LiteratureStorageError:
                failures.append(item.original_name)
            else:
                item.delete()
        if not failures:
            batch.delete()
    if failures:
        return JsonResponse({
            "ok": False,
            "message": "以下暂存文件未能从 NAS 删除：" + "、".join(failures),
        }, status=502)
    return JsonResponse({"ok": True, "message": "已取消本批上传。"})
