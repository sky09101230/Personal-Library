import hashlib
import json
import os
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from .downloads import load_literature_download_token
from .forms import BoxUploadForm, MetadataReviewForm, ZoteroImportForm
from .metadata import MetadataResolutionError, extract_pdf_evidence, fetch_doi_bibtex, resolve_pdf_metadata_safely
from .metadata_jobs import enqueue_metadata_proposal, enqueue_metadata_proposal_safely
from .metadata_review import apply_metadata_proposal, can_review_document, proposals_for_user, reject_metadata_proposal
from .models import CanonicalDocument, MetadataProposal, UploadedDocument
from .services import LiteratureStorageError
from .storage import delete_literature, get_literature_storage, open_literature_stream, store_literature
from .zotero import ZoteroImportError, import_zotero_library, iter_zotero_import_library


_SINGLE_BYTE_RANGE = re.compile(r"^bytes=(?:\d+-\d*|-\d+)$")


def _sha256(uploaded_file):
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def _proposal_form_values(proposed):
    proposed = proposed or {}
    return {
        "title": proposed.get("title", ""),
        "authors": "\n".join(
            author.get("name", "") + (f" | {author['orcid']}" if author.get("orcid") else "")
            for author in proposed.get("authors", [])
            if author.get("name")
        ),
        "abstract": proposed.get("abstract", ""),
        "journal": proposed.get("journal", ""),
        "publication_year": proposed.get("publication_year"),
        "doi": proposed.get("doi", ""),
        "ai_tags": ", ".join(proposed.get("ai_tags", [])),
    }


def _proposal_is_bulk_safe(proposal):
    proposed = proposal.proposal or {}
    named_authors = [author for author in proposed.get("authors", []) if author.get("name")]
    return bool(
        proposal.status == MetadataProposal.Status.SUCCEEDED
        and not proposal.validation_warnings
        and proposed.get("title")
        and named_authors
        and proposed.get("publication_year")
        and (proposed.get("doi") or proposed.get("journal"))
    )


def _preview_document_for_proposal(proposal):
    source_upload = proposal.source_upload
    if source_upload is not None and source_upload.status == UploadedDocument.Status.UPLOADED:
        return source_upload
    return proposal.canonical_document.uploads.filter(status=UploadedDocument.Status.UPLOADED).first()


@login_required
def home(request):
    records = UploadedDocument.objects.filter(status=UploadedDocument.Status.UPLOADED).select_related("uploader")
    return render(request, "box_upload/home.html", {
        "record_count": records.count(),
        "canonical_count": CanonicalDocument.objects.count(),
        "contributor_count": records.values("uploader_id").distinct().count(),
        "recent_uploads": records[:5],
    })


@login_required
def upload(request):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.method == "POST":
        form = BoxUploadForm(request.POST, request.FILES)
        if form.is_valid():
            remote_paths = []
            try:
                prepared_files = []
                prefetched_bibtex = {}
                for uploaded_file in form.cleaned_data["files"]:
                    digest = _sha256(uploaded_file)
                    if digest not in prefetched_bibtex:
                        bibtex = None
                        if not CanonicalDocument.objects.filter(sha256=digest).exists():
                            evidence = extract_pdf_evidence(uploaded_file)
                            if evidence["doi"]:
                                bibtex = fetch_doi_bibtex(evidence["doi"])
                        prefetched_bibtex[digest] = bibtex
                    prepared_files.append((uploaded_file, digest))

                for uploaded_file, digest in prepared_files:
                    stored = store_literature(uploaded_file)
                    remote_paths.append(stored.remote_path)
                    try:
                        with transaction.atomic():
                            canonical, created = CanonicalDocument.objects.get_or_create(
                                sha256=digest,
                                defaults={"index_status": CanonicalDocument.IndexStatus.PUBLISHED},
                            )
                            if not created and canonical.index_status != CanonicalDocument.IndexStatus.PUBLISHED:
                                canonical.index_status = CanonicalDocument.IndexStatus.PUBLISHED
                                canonical.save(update_fields=["index_status", "updated_at"])
                            upload_record = UploadedDocument.objects.create(
                                canonical_document=canonical,
                                uploader=request.user,
                                original_name=uploaded_file.name,
                                remote_path=stored.remote_path,
                                storage_backend=stored.backend,
                                sha256=digest,
                                size=uploaded_file.size,
                                content_type=uploaded_file.content_type or "",
                                duplicate_type=(UploadedDocument.DuplicateType.NEW if created else UploadedDocument.DuplicateType.EXACT),
                            )
                    except Exception:
                        try:
                            get_literature_storage(stored.backend).delete(stored.remote_path)
                        except LiteratureStorageError:
                            pass
                        raise
                    if created:
                        bibtex = prefetched_bibtex[digest]
                        resolve_pdf_metadata_safely(
                            canonical,
                            uploaded_file,
                            bibtex_fetcher=(lambda _doi, value=bibtex: value) if bibtex is not None else None,
                        )
                    enqueue_metadata_proposal_safely(
                        canonical,
                        requested_by=request.user,
                        source_upload=upload_record,
                        uploaded_file=uploaded_file,
                    )
            except (LiteratureStorageError, MetadataResolutionError) as exc:
                preflight_failed = isinstance(exc, MetadataResolutionError)
                message = (
                    f"DOI BibTeX 预检失败，已停止上传：{exc}"
                    if preflight_failed
                    else f"已上传 {len(remote_paths)} 个文件后失败：{exc}"
                )
                if is_ajax:
                    return JsonResponse({
                        "ok": False,
                        "code": "doi_bibtex_preflight_failed" if preflight_failed else "upload_failed",
                        "message": message,
                    }, status=400)
                form.add_error(None, message)
            else:
                if is_ajax:
                    return JsonResponse({"ok": True, "count": len(remote_paths), "paths": remote_paths})
                messages.success(request, f"已完成 {len(remote_paths)} 个文件上传。")
                return redirect("box-upload")
        elif is_ajax:
            file_errors = form.errors.get("files")
            message = str(file_errors[0]) if file_errors else "请选择至少一个 PDF 文件。"
            return JsonResponse({"ok": False, "message": message}, status=400)
    else:
        form = BoxUploadForm()
    return render(request, "box_upload/upload.html", {"form": form})


@login_required
def upload_history(request):
    return library(request, uploader=request.user)


@login_required
def library(request, uploader=None):
    uploads = UploadedDocument.objects.select_related("uploader")
    if uploader is not None:
        uploads = uploads.filter(uploader=uploader)
    records = CanonicalDocument.objects.prefetch_related(
        Prefetch("uploads", queryset=uploads),
        Prefetch(
            "metadata_proposals",
            queryset=MetadataProposal.objects.select_related("requested_by", "reviewed_by", "source_upload"),
        ),
        "external_references",
    ).order_by("-created_at")
    if uploader is not None:
        records = records.filter(uploads__uploader=uploader).distinct()
    scoped_records = records
    workflow = request.GET.get("workflow", "").strip()
    if workflow == "review":
        records = records.exclude(metadata_status=CanonicalDocument.MetadataStatus.VERIFIED)
    elif workflow == "unpublished":
        records = records.exclude(index_status=CanonicalDocument.IndexStatus.PUBLISHED)
    else:
        workflow = ""
    journal = request.GET.get("journal", "").strip()
    if journal:
        records = records.filter(journal=journal)
    year = request.GET.get("year", "").strip()
    if year:
        try:
            records = records.filter(publication_year=int(year))
        except ValueError:
            records = records.none()
    uploader_id = "" if uploader is not None else request.GET.get("uploader", "").strip()
    if uploader_id:
        try:
            records = records.filter(uploads__uploader_id=int(uploader_id)).distinct()
        except ValueError:
            records = records.none()
    query = request.GET.get("q", "").strip()
    if query:
        records = records.filter(
            Q(uploads__original_name__icontains=query)
            | Q(sha256__icontains=query)
            | Q(title__icontains=query)
            | Q(doi__icontains=query)
            | Q(journal__icontains=query)
        ).distinct()
    page = Paginator(records, 20).get_page(request.GET.get("page"))
    for literature in page.object_list:
        literature.latest_metadata_proposal = next(iter(literature.metadata_proposals.all()), None)
        literature.can_review_ai_metadata = can_review_document(request.user, literature)
    review_proposals = MetadataProposal.objects.filter(status=MetadataProposal.Status.SUCCEEDED)
    if not request.user.is_staff:
        review_proposals = review_proposals.filter(canonical_document__uploads__uploader=request.user).distinct()
    pagination_query = request.GET.copy()
    pagination_query.pop("page", None)
    return render(request, "box_upload/library.html", {
        "page": page,
        "record_count": records.count(),
        "canonical_count": scoped_records.count(),
        "review_count": scoped_records.exclude(
            metadata_status=CanonicalDocument.MetadataStatus.VERIFIED
        ).count(),
        "published_count": scoped_records.filter(
            index_status=CanonicalDocument.IndexStatus.PUBLISHED
        ).count(),
        "proposal_review_count": review_proposals.count(),
        "deepseek_enabled": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "query": query,
        "workflow": workflow,
        "journal": journal,
        "year": year,
        "uploader_id": uploader_id,
        "journal_options": scoped_records.exclude(journal="").order_by("journal").values_list("journal", flat=True).distinct(),
        "year_options": scoped_records.exclude(publication_year=None).order_by("-publication_year").values_list("publication_year", flat=True).distinct(),
        "uploader_options": UploadedDocument.objects.filter(
            canonical_document__in=scoped_records,
            status=UploadedDocument.Status.UPLOADED,
        ).order_by("uploader__username").values("uploader_id", "uploader__username").distinct(),
        "pagination_query": pagination_query.urlencode(),
        "is_my_uploads": uploader is not None,
        "list_url_name": "upload-history" if uploader is not None else "library",
    })


@login_required
@require_POST
def delete_upload(request, pk):
    document = get_object_or_404(UploadedDocument, pk=pk, uploader=request.user)
    try:
        delete_literature(document)
    except LiteratureStorageError:
        messages.error(request, f"删除 {document.original_name} 失败，存储文件和记录均已保留。")
        return redirect("upload-history")

    canonical = document.canonical_document
    document.delete()
    if not canonical.uploads.exists() and not canonical.external_references.exists():
        canonical.delete()
    messages.success(request, f"已删除 {document.original_name}。")
    return redirect("upload-history")


@login_required
def zotero_import(request):
    if not request.user.is_staff:
        return render(
            request,
            "box_upload/zotero_import.html",
            {"upgrade_mode": True},
            status=403 if request.method == "POST" else 200,
        )

    form = ZoteroImportForm(request.POST or None)
    wants_progress = request.headers.get("Accept") == "application/x-ndjson"
    if request.method == "POST" and wants_progress and not form.is_valid():
        return JsonResponse({"ok": False, "message": "请填写完整且有效的 Zotero 导入参数。"}, status=400)
    if request.method == "POST" and form.is_valid():
        if wants_progress:
            def events():
                try:
                    for event in iter_zotero_import_library(
                        form.cleaned_data["library_type"],
                        form.cleaned_data["library_id"],
                        form.cleaned_data["api_key"],
                        collection_key=form.cleaned_data["collection_key"],
                        uploader=request.user,
                    ):
                        yield json.dumps({"ok": True, **event}, ensure_ascii=False) + "\n"
                except ZoteroImportError as exc:
                    yield json.dumps({"ok": False, "done": True, "message": str(exc)}, ensure_ascii=False) + "\n"

            response = StreamingHttpResponse(events(), content_type="application/x-ndjson; charset=utf-8")
            response["Cache-Control"] = "no-cache, no-store"
            response["X-Accel-Buffering"] = "no"
            return response
        try:
            result = import_zotero_library(
                form.cleaned_data["library_type"],
                form.cleaned_data["library_id"],
                form.cleaned_data["api_key"],
                collection_key=form.cleaned_data["collection_key"],
                uploader=request.user,
            )
        except ZoteroImportError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                f"Zotero 导入完成：文献新增 {result['created']}，复用 {result['reused']}，"
                f"跳过 {result['skipped']}；PDF 导入 {result['pdf_imported']}，复用 {result['pdf_reused']}，"
                f"跳过 {result['pdf_skipped']}，失败 {result['pdf_failed']}。",
            )
            return redirect("library")
    return render(request, "box_upload/zotero_import.html", {"form": form, "upgrade_mode": False})


@login_required
def metadata_review_queue(request):
    user_proposals = proposals_for_user(request.user)
    status_groups = {
        "pending": (MetadataProposal.Status.SUCCEEDED,),
        "processing": (MetadataProposal.Status.QUEUED, MetadataProposal.Status.RUNNING),
        "issues": (MetadataProposal.Status.FAILED, MetadataProposal.Status.STALE),
        "reviewed": (MetadataProposal.Status.ACCEPTED, MetadataProposal.Status.REJECTED),
        "all": (
            MetadataProposal.Status.QUEUED,
            MetadataProposal.Status.RUNNING,
            MetadataProposal.Status.SUCCEEDED,
            MetadataProposal.Status.FAILED,
            MetadataProposal.Status.STALE,
            MetadataProposal.Status.ACCEPTED,
            MetadataProposal.Status.REJECTED,
        ),
    }
    status_filter = request.GET.get("status", "pending")
    if status_filter not in status_groups:
        status_filter = "pending"
    query = request.GET.get("q", "").strip()
    proposals = user_proposals.filter(status__in=status_groups[status_filter])
    if query:
        proposals = proposals.filter(
            Q(canonical_document__title__icontains=query)
            | Q(canonical_document__doi__icontains=query)
            | Q(source_upload__original_name__icontains=query)
        )
    page = Paginator(proposals, 50).get_page(request.GET.get("page"))
    page_bulk_safe_count = 0
    page_individual_review_count = 0
    for proposal in page.object_list:
        proposed = proposal.proposal or {}
        proposal.proposed_authors = [author for author in proposed.get("authors", []) if author.get("name")]
        proposal.proposed_is_complete = bool(
            proposed.get("title")
            and proposal.proposed_authors
            and proposed.get("publication_year")
            and (proposed.get("doi") or proposed.get("journal"))
        )
        proposal.bulk_safe = _proposal_is_bulk_safe(proposal)
        if status_filter == "pending":
            if proposal.bulk_safe:
                page_bulk_safe_count += 1
            else:
                page_individual_review_count += 1
    return render(request, "box_upload/metadata_review_queue.html", {
        "page": page,
        "deepseek_enabled": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
        "status_filter": status_filter,
        "query": query,
        "page_bulk_safe_count": page_bulk_safe_count,
        "page_individual_review_count": page_individual_review_count,
        "pending_count": user_proposals.filter(status=MetadataProposal.Status.SUCCEEDED).count(),
        "processing_count": user_proposals.filter(
            status__in=(MetadataProposal.Status.QUEUED, MetadataProposal.Status.RUNNING)
        ).count(),
        "issue_count": user_proposals.filter(
            status__in=(MetadataProposal.Status.FAILED, MetadataProposal.Status.STALE)
        ).count(),
        "reviewed_count": user_proposals.filter(
            status__in=(MetadataProposal.Status.ACCEPTED, MetadataProposal.Status.REJECTED)
        ).count(),
    })


@login_required
def metadata_review_detail(request, pk):
    proposal = get_object_or_404(proposals_for_user(request.user), pk=pk)
    return render(request, "box_upload/metadata_review_detail.html", {
        "proposal": proposal,
        "form": MetadataReviewForm(initial=_proposal_form_values(proposal.proposal)),
        "remaining_count": proposals_for_user(request.user).filter(status=MetadataProposal.Status.SUCCEEDED).count(),
        "preview_document": _preview_document_for_proposal(proposal),
    })


@login_required
@require_POST
def metadata_review_bulk_accept(request):
    proposal_ids = []
    for raw_id in request.POST.getlist("proposal_ids")[:50]:
        try:
            proposal_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    proposal_ids = list(dict.fromkeys(proposal_ids))
    if not proposal_ids:
        messages.warning(request, "请先勾选要确认的 AI metadata。")
        return redirect("metadata-review-queue")

    available = proposals_for_user(request.user).filter(
        pk__in=proposal_ids,
        status=MetadataProposal.Status.SUCCEEDED,
    )
    proposals_by_id = {proposal.pk: proposal for proposal in available}
    applied_count = 0
    stale_count = 0
    invalid_count = 0
    individual_review_count = 0
    for proposal_id in proposal_ids:
        proposal = proposals_by_id.get(proposal_id)
        if proposal is None:
            invalid_count += 1
            continue
        if not _proposal_is_bulk_safe(proposal):
            individual_review_count += 1
            continue
        form = MetadataReviewForm(_proposal_form_values(proposal.proposal))
        if not form.is_valid():
            invalid_count += 1
            continue
        _, applied = apply_metadata_proposal(proposal.id, request.user, form.cleaned_data)
        if applied:
            applied_count += 1
        else:
            stale_count += 1

    if applied_count:
        messages.success(request, f"已确认 {applied_count} 篇 metadata；均未发布给 Agent。")
    if stale_count:
        messages.warning(request, f"有 {stale_count} 篇因原 metadata 已变化而跳过，请重新生成。")
    if invalid_count:
        messages.warning(request, f"有 {invalid_count} 篇无权限、状态已变化或候选不完整，未确认。")
    if individual_review_count:
        messages.warning(request, f"有 {individual_review_count} 篇含证据警告或字段不完整，需进入详情逐篇确认。")
    return redirect("metadata-review-queue")


@login_required
@require_POST
def metadata_review_enqueue(request, document_id):
    canonical = get_object_or_404(CanonicalDocument, pk=document_id)
    if not can_review_document(request.user, canonical):
        raise PermissionDenied
    proposal = enqueue_metadata_proposal(
        canonical,
        requested_by=request.user,
        source_upload=canonical.uploads.filter(uploader=request.user).first() or canonical.uploads.first(),
        force=True,
    )
    if proposal.status == MetadataProposal.Status.FAILED and proposal.error_code == "disabled":
        messages.warning(request, "DeepSeek 尚未配置，未发送任何文献内容。")
    else:
        messages.success(request, "AI metadata 补全任务已入队。")
    return redirect("metadata-review-queue")


@login_required
@require_POST
def metadata_review_accept(request, pk):
    proposal = get_object_or_404(proposals_for_user(request.user), pk=pk)
    form = MetadataReviewForm(request.POST)
    if not form.is_valid():
        return render(request, "box_upload/metadata_review_detail.html", {
            "proposal": proposal,
            "form": form,
            "remaining_count": proposals_for_user(request.user).filter(
                status=MetadataProposal.Status.SUCCEEDED
            ).count(),
            "preview_document": _preview_document_for_proposal(proposal),
        }, status=400)
    _, applied = apply_metadata_proposal(proposal.id, request.user, form.cleaned_data)
    if applied:
        messages.success(request, "已保存你确认的 metadata；发布状态没有改变。")
        if request.POST.get("continue") == "next":
            next_proposal = proposals_for_user(request.user).filter(
                status=MetadataProposal.Status.SUCCEEDED,
            ).order_by("requested_at").first()
            if next_proposal is not None:
                return redirect("metadata-review-detail", pk=next_proposal.pk)
    else:
        messages.warning(request, "该文献在建议生成后已被修改，AI 建议已标记为过期。")
    return redirect("metadata-review-queue")


@login_required
@require_POST
def metadata_review_reject(request, pk):
    proposal = get_object_or_404(proposals_for_user(request.user), pk=pk)
    reject_metadata_proposal(proposal.id, request.user)
    messages.success(request, "已退回 AI 建议，当前 metadata 未改变。")
    return redirect("metadata-review-queue")


@login_required
@require_POST
def metadata_review_regenerate(request, pk):
    old_proposal = get_object_or_404(proposals_for_user(request.user), pk=pk)
    proposal = enqueue_metadata_proposal(
        old_proposal.canonical_document,
        requested_by=request.user,
        source_upload=old_proposal.source_upload,
        force=True,
    )
    if proposal.status == MetadataProposal.Status.FAILED and proposal.error_code == "disabled":
        messages.warning(request, "DeepSeek 尚未配置，无法重新生成。")
    else:
        messages.success(request, "新的 AI metadata 任务已入队。")
    return redirect("metadata-review-queue")


@login_required
@require_GET
def view_document(request, pk):
    document = get_object_or_404(UploadedDocument, pk=pk, status=UploadedDocument.Status.UPLOADED)
    return _stream_document_request(request, document, as_attachment=False)


@login_required
@require_GET
def download_document(request, pk):
    document = get_object_or_404(UploadedDocument, pk=pk, status=UploadedDocument.Status.UPLOADED)
    return _stream_document_request(request, document, as_attachment=True)


@require_GET
def signed_download_document(request, token):
    try:
        upload_id = load_literature_download_token(token)
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise Http404("Literature download link is unavailable.") from exc
    document = get_object_or_404(
        UploadedDocument.objects.select_related("canonical_document"),
        pk=upload_id,
        status=UploadedDocument.Status.UPLOADED,
        canonical_document__index_status=CanonicalDocument.IndexStatus.PUBLISHED,
    )
    return _stream_document_request(request, document, as_attachment=True)


def _stream_document_request(request, document, *, as_attachment):
    byte_range = request.headers.get("Range", "").strip()
    if byte_range and not _SINGLE_BYTE_RANGE.fullmatch(byte_range):
        response = HttpResponse("Invalid PDF byte range.", status=416, content_type="text/plain; charset=utf-8")
        response["Accept-Ranges"] = "bytes"
        return response
    try:
        upstream = open_literature_stream(document, byte_range=byte_range or None)
    except LiteratureStorageError:
        return HttpResponse(
            "暂时无法读取 PDF，请稍后重试。",
            status=502,
            content_type="text/plain; charset=utf-8",
        )

    response = StreamingHttpResponse(
        upstream.iter_chunks(),
        status=upstream.status,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = content_disposition_header(as_attachment, document.original_name)
    response["Accept-Ranges"] = upstream.get_header("Accept-Ranges") or "bytes"
    for header in ("Content-Length", "Content-Range", "ETag", "Last-Modified"):
        value = upstream.get_header(header)
        if value:
            response[header] = value
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
