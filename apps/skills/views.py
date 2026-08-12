from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.core import signing
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from apps.box_upload.services import LiteratureStorageError
from apps.box_upload.storage import NAS_WEBDAV

from .downloads import load_skill_download_token
from .candidate_services import CandidatePublishError, CandidateValidationError, create_uploaded_candidate, publish_candidate, reject_candidate
from .forms import SkillCandidateReviewForm, SkillCandidateUploadForm, SkillDescriptionForm
from .models import FeaturedSkill, GitHubSkillSource, SharedSkill, SharedSkillRelease, SkillCandidate, SkillPurpose
from .storage import open_skill_stream
from .tasks import launch_enrichment_job, launch_scan_job
from .models import SkillSyncJob


@login_required
def index(request):
    query = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "")
    selected_purpose = request.GET.get("purpose", "")
    page_number = request.GET.get("page")
    skills = SharedSkill.objects.prefetch_related("releases")
    if query:
        skills = skills.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(slug__icontains=query))
    subpurposes = SkillPurpose.objects.filter(parent__isnull=False)
    purposes = list(SkillPurpose.objects.filter(parent__isnull=True).prefetch_related(
        Prefetch("subpurposes", queryset=subpurposes, to_attr="purpose_tabs")
    ))
    for purpose in purposes:
        purpose.has_results = False
        for subpurpose in purpose.purpose_tabs:
            subpurpose.skills_for_display = skills.filter(purpose=subpurpose)
            purpose.has_results = purpose.has_results or subpurpose.skills_for_display.exists()
        if not purpose.purpose_tabs:
            purpose.skills_for_display = skills.filter(purpose=purpose)
            purpose.has_results = purpose.skills_for_display.exists()
    if query:
        purposes = [purpose for purpose in purposes if purpose.has_results]
    active_purpose = next((purpose for purpose in purposes if purpose.slug == selected_category), None)
    if active_purpose is None and purposes and selected_category != "uncategorized":
        active_purpose = purposes[0]
    uncategorized_skills = skills.filter(purpose__isnull=True)
    for purpose in purposes:
        purpose.is_active = purpose == active_purpose
        active_subpurpose = next(
            (subpurpose for subpurpose in purpose.purpose_tabs if subpurpose.slug == selected_purpose), None
        )
        if purpose.is_active and active_subpurpose is None and purpose.purpose_tabs:
            active_subpurpose = purpose.purpose_tabs[0]
        for subpurpose in purpose.purpose_tabs:
            subpurpose.is_active = purpose.is_active and subpurpose == active_subpurpose
            subpurpose.page = Paginator(subpurpose.skills_for_display, 24).get_page(
                page_number if subpurpose.is_active else 1
            )
        if not purpose.purpose_tabs:
            purpose.page = Paginator(purpose.skills_for_display, 24).get_page(
                page_number if purpose.is_active else 1
            )
    uncategorized_is_active = selected_category == "uncategorized" or active_purpose is None
    uncategorized_page = Paginator(uncategorized_skills, 24).get_page(page_number if uncategorized_is_active else 1)
    active_job = SkillSyncJob.objects.filter(status__in=[SkillSyncJob.QUEUED, SkillSyncJob.RUNNING]).first()
    return render(request, "skills/index.html", {
        "purposes": purposes,
        "uncategorized_page": uncategorized_page,
        "uncategorized_is_active": uncategorized_is_active,
        "query": query,
        "active_job": active_job,
        "sync_sources": GitHubSkillSource.objects.filter(is_enabled=True),
    })


@login_required
def featured(request):
    entries = FeaturedSkill.objects.select_related("skill", "skill__purpose", "skill__source").prefetch_related("skill__releases")
    return render(request, "skills/featured.html", {"entries": entries})


@login_required
def submit_candidate(request):
    form = SkillCandidateUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            candidate, created = create_uploaded_candidate(form.cleaned_data["archive"], request.user)
        except CandidateValidationError as exc:
            form.add_error("archive", str(exc))
        else:
            if created:
                messages.success(request, "Skill 已进入候选池，管理员批准前不会出现在正式库中。")
            else:
                messages.info(request, "相同内容已经投稿，本次未重复保存。")
            return redirect("skills-candidate-detail", candidate_id=candidate.pk)
    return render(request, "skills/submit_candidate.html", {"form": form})


@login_required
def candidates(request):
    queryset = SkillCandidate.objects.select_related("source", "submitted_by", "purpose", "purpose__parent")
    if not request.user.is_staff:
        queryset = queryset.filter(origin=SkillCandidate.Origin.UPLOAD, submitted_by=request.user)
    status = request.GET.get("status", "").strip()
    source_id = request.GET.get("source", "").strip()
    if status in SkillCandidate.Status.values:
        queryset = queryset.filter(status=status)
    if request.user.is_staff and source_id.isdecimal():
        queryset = queryset.filter(source_id=int(source_id))
    page = Paginator(queryset, 30).get_page(request.GET.get("page"))
    return render(request, "skills/candidates.html", {
        "page": page,
        "selected_status": status,
        "selected_source": source_id,
        "status_choices": SkillCandidate.Status.choices,
        "sources": GitHubSkillSource.objects.filter(is_enabled=True),
    })


@login_required
def candidate_detail(request, candidate_id):
    queryset = SkillCandidate.objects.select_related("source", "submitted_by", "purpose", "purpose__parent", "published_skill")
    if not request.user.is_staff:
        queryset = queryset.filter(origin=SkillCandidate.Origin.UPLOAD, submitted_by=request.user)
    candidate = get_object_or_404(queryset, pk=candidate_id)
    form = SkillCandidateReviewForm(initial={
        "description": candidate.description,
        "purpose": candidate.purpose_id,
        "rejection_reason": candidate.rejection_reason,
    }) if request.user.is_staff else None
    return render(request, "skills/candidate_detail.html", {"candidate": candidate, "form": form})


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def review_candidate(request, candidate_id):
    candidate = get_object_or_404(SkillCandidate, pk=candidate_id)
    form = SkillCandidateReviewForm(request.POST)
    action = request.POST.get("action")
    if action == "reject":
        reason = request.POST.get("rejection_reason", "").strip()
        if not reason:
            form.add_error("rejection_reason", "拒绝时必须填写原因。")
            return render(request, "skills/candidate_detail.html", {"candidate": candidate, "form": form}, status=400)
        try:
            reject_candidate(candidate, request.user, reason)
        except CandidatePublishError as exc:
            messages.error(request, str(exc))
            return redirect("skills-candidate-detail", candidate_id=candidate.pk)
        messages.success(request, f"已拒绝 {candidate.name}。")
        return redirect("skills-candidates")
    if not form.is_valid():
        return render(request, "skills/candidate_detail.html", {"candidate": candidate, "form": form}, status=400)
    candidate.description = form.cleaned_data["description"]
    candidate.purpose = form.cleaned_data["purpose"]
    candidate.purpose_is_manual = True
    candidate.save(update_fields=["description", "purpose", "purpose_is_manual", "updated_at"])
    try:
        if action == "publish":
            publish_candidate(candidate, request.user)
            messages.success(request, f"已发布 {candidate.name}。")
        else:
            raise CandidatePublishError("未知审核操作。")
    except CandidatePublishError as exc:
        messages.error(request, str(exc))
        return redirect("skills-candidate-detail", candidate_id=candidate.pk)
    return redirect("skills-candidates")


@login_required
@user_passes_test(lambda user: user.is_staff)
@require_POST
def batch_publish_candidates(request):
    candidate_ids = [int(value) for value in request.POST.getlist("candidate_ids") if value.isdecimal()]
    published = 0
    failures = []
    for candidate in SkillCandidate.objects.filter(pk__in=candidate_ids, status=SkillCandidate.Status.PENDING):
        try:
            publish_candidate(candidate, request.user)
        except CandidatePublishError as exc:
            failures.append(f"{candidate.name}: {exc}")
        else:
            published += 1
    if published:
        messages.success(request, f"已发布 {published} 个候选。")
    if failures:
        messages.error(request, "；".join(failures))
    return redirect("skills-candidates")


@login_required
def detail(request, slug, source_slug=None):
    skill_query = SharedSkill.objects.prefetch_related("releases")
    if source_slug:
        skill = get_object_or_404(skill_query, source__slug=source_slug, slug=slug)
    else:
        skill = skill_query.filter(slug=slug).order_by("id").first()
        if skill is None:
            raise Http404
    release = _preferred_release(skill)
    return render(request, "skills/detail.html", {"skill": skill, "release": release})


@login_required
@user_passes_test(lambda user: user.is_staff)
def edit_description(request, source_slug, slug):
    skill = get_object_or_404(SharedSkill, source__slug=source_slug, slug=slug)
    form = SkillDescriptionForm(request.POST or None, initial={"description": skill.description})
    if request.method == "POST" and form.is_valid():
        skill.description = form.cleaned_data["description"]
        skill.description_is_manual = True
        skill.save(update_fields=["description", "description_is_manual", "updated_at"])
        messages.success(request, "Skill 展示描述已保存；后续 DeepSeek 重生成不会覆盖此人工版本。")
        return redirect("skills-source-detail", source_slug=skill.source.slug, slug=skill.slug)
    return render(request, "skills/edit_description.html", {"skill": skill, "form": form})


@login_required
def download(request, slug, source_slug=None):
    if source_slug:
        skill = get_object_or_404(SharedSkill, source__slug=source_slug, slug=slug)
    else:
        skill = SharedSkill.objects.filter(slug=slug).order_by("id").first()
        if skill is None:
            raise Http404
    release = _preferred_release(skill, request.GET.get("commit", ""))
    if release is None:
        return redirect("skills-source-detail", source_slug=skill.source.slug, slug=skill.slug) if skill.source else redirect("skills-detail", slug=skill.slug)
    return _stream_skill_release(release)


@require_GET
def signed_download(request, token):
    try:
        release_id = load_skill_download_token(token)
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise Http404("Skill download link is unavailable.") from exc
    return _stream_skill_release(get_object_or_404(SharedSkillRelease, pk=release_id))


def _preferred_release(skill, commit=""):
    releases = skill.releases.filter(git_commit=commit) if commit else skill.releases.all()
    return releases.filter(storage_backend=NAS_WEBDAV).first() or releases.first()


def _stream_skill_release(release):
    try:
        upstream = open_skill_stream(release)
    except LiteratureStorageError:
        return HttpResponse(
            "暂时无法读取 Skill 发布包，请稍后重试。",
            status=502,
            content_type="text/plain; charset=utf-8",
        )
    response = StreamingHttpResponse(
        upstream.iter_chunks(),
        status=upstream.status,
        content_type="application/zip",
    )
    response["Content-Disposition"] = content_disposition_header(True, release.archive_name)
    for header in ("Content-Length", "ETag", "Last-Modified"):
        value = upstream.get_header(header)
        if value:
            response[header] = value
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@user_passes_test(lambda user: user.is_staff)
def sync(request):
    if request.method != "POST":
        return redirect("skills-index")
    selected_source, error_response = _selected_source(request)
    if error_response:
        return error_response
    job = SkillSyncJob.objects.filter(status__in=[SkillSyncJob.QUEUED, SkillSyncJob.RUNNING]).first()
    if job is None:
        job = SkillSyncJob.objects.create(requested_by=request.user, operation=SkillSyncJob.SCAN)
        try:
            launch_scan_job(job.pk, source_id=selected_source.pk if selected_source else None)
        except OSError as exc:
            job.status = SkillSyncJob.FAILED
            job.error = f"无法启动候选扫描任务: {exc}"
            job.save(update_fields=["status", "error"])
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"job_id": job.pk, "status": job.status, "operation": job.operation}, status=202)
    messages.info(request, "候选扫描已开始；扫描结果不会直接发布。")
    return redirect("skills-index")


@login_required
@user_passes_test(lambda user: user.is_staff)
def enrich(request):
    if request.method != "POST":
        return redirect("skills-index")
    selected_source, error_response = _selected_source(request)
    if error_response:
        return error_response
    job = SkillSyncJob.objects.filter(status__in=[SkillSyncJob.QUEUED, SkillSyncJob.RUNNING]).first()
    if job is None:
        job = SkillSyncJob.objects.create(requested_by=request.user, operation=SkillSyncJob.ENRICHMENT)
        try:
            launch_enrichment_job(job.pk, source_id=selected_source.pk if selected_source else None)
        except OSError as exc:
            job.status = SkillSyncJob.FAILED
            job.error = f"无法启动摘要与分类任务: {exc}"
            job.save(update_fields=["status", "error"])
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"job_id": job.pk, "status": job.status, "operation": job.operation}, status=202)
    messages.info(request, "摘要与分类任务已开始，请在页面上查看进度。")
    return redirect("skills-index")


def _selected_source(request):
    source_id = request.POST.get("source_id", "").strip()
    selected_source = None
    if source_id and source_id.isdecimal():
        selected_source = GitHubSkillSource.objects.filter(pk=source_id, is_enabled=True).first()
    if source_id and selected_source is None:
        error = "请选择有效且已启用的 GitHub 仓库。"
        if request.headers.get("Accept") == "application/json":
            return None, JsonResponse({"error": error}, status=400)
        messages.error(request, error)
        return None, redirect("skills-index")
    return selected_source, None


@login_required
@user_passes_test(lambda user: user.is_staff)
def sync_status(request, job_id):
    job = get_object_or_404(SkillSyncJob, pk=job_id)
    return JsonResponse({
        "operation": job.operation,
        "status": job.status,
        "current_source": job.current_source,
        "current_skill": job.current_skill,
        "sources_completed": job.sources_completed,
        "sources_total": job.sources_total,
        "skills_processed": job.skills_processed,
        "skills_total": job.skills_total,
        "uploaded_count": job.uploaded_count,
        "enriched_count": job.enriched_count,
        "skipped_count": job.skipped_count,
        "failed_sources": job.failed_sources,
        "percent": job.percent,
        "error": job.error,
    })
