import os
import subprocess
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path, PurePosixPath

from django.db import IntegrityError, transaction
from django.utils import timezone

from .ai_enrichment import SkillEnrichmentError, generate_skill_enrichment
from .models import GitHubSkillSource, SharedSkill, SkillPurpose, SkillSyncJob


class SkillSyncError(Exception):
    pass


class InactiveSkillJob(Exception):
    pass


ACTIVE_JOB_STATUSES = (SkillSyncJob.QUEUED, SkillSyncJob.RUNNING)
DEFAULT_JOB_STALE_SECONDS = 3600


def get_or_create_skill_job(requested_by, operation):
    now = timezone.now()
    cutoff = now - timedelta(seconds=_job_stale_seconds())
    with transaction.atomic():
        active_jobs = list(
            SkillSyncJob.objects.select_for_update()
            .filter(status__in=ACTIVE_JOB_STATUSES)
            .order_by("-created_at", "-pk")
        )
        for job in active_jobs:
            last_activity = job.heartbeat_at or job.started_at or job.created_at
            if last_activity <= cutoff:
                SkillSyncJob.objects.filter(pk=job.pk, status__in=ACTIVE_JOB_STATUSES).update(
                    status=SkillSyncJob.FAILED,
                    error="任务长时间没有活动，已自动关闭。",
                    heartbeat_at=now,
                    finished_at=now,
                )
            else:
                return job, False
        try:
            with transaction.atomic():
                return SkillSyncJob.objects.create(
                    requested_by=requested_by,
                    operation=operation,
                    heartbeat_at=now,
                ), True
        except IntegrityError:
            job = (
                SkillSyncJob.objects.filter(status__in=ACTIVE_JOB_STATUSES)
                .order_by("-created_at", "-pk")
                .first()
            )
            if job is None:
                raise
            return job, False


def enrich_shared_skills(job=None, source_id=None):
    _start_job(job)
    source_query = GitHubSkillSource.objects.filter(is_enabled=True)
    if source_id is not None:
        source_query = source_query.filter(pk=source_id)
    sources = list(source_query)
    if not sources:
        message = (
            "Selected GitHub skill source is not enabled or does not exist."
            if source_id is not None
            else "No enabled GitHub skill source is configured."
        )
        raise _fail_job(job, message)
    if job is not None:
        _update_job(job, sources_total=len(sources))
    results = []
    errors = []
    for source in sources:
        _update_job(job, current_source=source.name, current_skill="")
        try:
            results.append(_enrich_source(source, job=job))
        except SkillSyncError as exc:
            errors.append(str(exc))
            if job is not None:
                _update_job(job, failed_sources=job.failed_sources + 1, error="\n".join(errors))
        else:
            _update_job(job, sources_completed=(job.sources_completed + 1) if job is not None else 0)
    if job is not None:
        _finish_job(
            job,
            SkillSyncJob.FAILED if errors and not results else SkillSyncJob.COMPLETED,
            "\n".join(errors),
        )
    if errors and not results:
        raise SkillSyncError("\n".join(errors))
    return results


def _enrich_source(source, job=None):
    with tempfile.TemporaryDirectory(prefix="plab-skill-enrichment-") as temporary_directory:
        repository = Path(temporary_directory) / "repository"
        clone_args = ["clone"]
        if source.branch:
            clone_args.extend(["--branch", source.branch])
        clone_args.extend([source.repository_url, str(repository)])
        try:
            _run_git(*clone_args)
        except SkillSyncError as exc:
            raise SkillSyncError(f"{source.name}: {exc}") from exc
        purposes = list(SkillPurpose.objects.filter(subpurposes__isnull=True).select_related("parent"))
        purposes_by_slug = {purpose.slug: purpose for purpose in purposes}
        skills = list(SharedSkill.objects.filter(source=source).prefetch_related("releases"))
        if job is not None:
            _update_job(job, skills_total=job.skills_total + len(skills))
        enriched = []
        skipped = []
        repository_root = repository.resolve()
        for skill in skills:
            _update_job(job, current_skill=skill.name)
            release = skill.releases.first()
            if release is None or not skill.source_path:
                skipped.append(skill)
                _update_job(
                    job,
                    skipped_count=(job.skipped_count + 1) if job is not None else 0,
                    skills_processed=(job.skills_processed + 1) if job is not None else 0,
                )
                continue
            try:
                _run_git("-C", str(repository), "checkout", "--detach", "--force", release.git_commit)
                skill_directory = repository.joinpath(*PurePosixPath(skill.source_path).parts).resolve()
                if not skill_directory.is_relative_to(repository_root):
                    raise OSError("Skill source path escapes the repository.")
                document = (skill_directory / "SKILL.md").read_text(encoding="utf-8")
            except (OSError, UnicodeError, SkillSyncError) as exc:
                raise SkillSyncError(
                    f"{skill.name}: published commit {release.git_commit[:12]} is unavailable: {exc}"
                ) from exc
            skill_name = _read_metadata(document).get("name") or skill.name
            try:
                enrichment = generate_skill_enrichment(skill_name, document, purposes)
            except SkillEnrichmentError as exc:
                raise SkillSyncError(f"{skill_name}: DeepSeek enrichment failed ({exc.code}): {exc}") from exc
            skill.name = skill_name
            skill.ai_generated_description = enrichment["summary"]
            skill.ai_summary_commit = release.git_commit
            skill.ai_summary_model = enrichment["model"]
            skill.ai_summary_prompt_version = enrichment["prompt_version"]
            update_fields = [
                "name",
                "ai_generated_description",
                "ai_summary_commit",
                "ai_summary_model",
                "ai_summary_prompt_version",
                "updated_at",
            ]
            if not skill.description_is_manual:
                skill.description = enrichment["summary"]
                update_fields.append("description")
            if not skill.purpose_is_manual:
                skill.purpose = purposes_by_slug.get(enrichment["purpose_slug"])
                update_fields.append("purpose")
            skill.save(update_fields=update_fields)
            enriched.append(skill)
            _update_job(
                job,
                enriched_count=(job.enriched_count + 1) if job is not None else 0,
                skills_processed=(job.skills_processed + 1) if job is not None else 0,
            )
        return source, enriched, skipped


def _run_git(*arguments):
    command = ["git", "-c", "http.sslBackend=openssl", *arguments]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise SkillSyncError(f"Git command failed: {detail[:500] or 'unknown error'}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillSyncError("Git command timed out after 120 seconds.") from exc
    except OSError as exc:
        raise SkillSyncError(f"Git is unavailable: {exc}") from exc
    return result.stdout


def _update_job(job, **fields):
    if job is None:
        return
    fields["heartbeat_at"] = timezone.now()
    updated = SkillSyncJob.objects.filter(pk=job.pk, status__in=ACTIVE_JOB_STATUSES).update(**fields)
    if not updated:
        job.refresh_from_db()
        raise InactiveSkillJob("Skill job is no longer active.")
    for field, value in fields.items():
        setattr(job, field, value)


def _start_job(job):
    if job is None:
        return
    now = timezone.now()
    updated = SkillSyncJob.objects.filter(pk=job.pk, status=SkillSyncJob.QUEUED).update(
        status=SkillSyncJob.RUNNING,
        started_at=now,
        heartbeat_at=now,
        error="",
    )
    if not updated:
        job.refresh_from_db()
        raise InactiveSkillJob("Skill job is no longer queued.")
    job.status = SkillSyncJob.RUNNING
    job.started_at = now
    job.heartbeat_at = now
    job.error = ""


def _finish_job(job, status, error=""):
    if job is None:
        return True
    now = timezone.now()
    fields = {
        "status": status,
        "current_source": "",
        "current_skill": "",
        "error": error[:2000],
        "heartbeat_at": now,
        "finished_at": now,
    }
    updated = SkillSyncJob.objects.filter(pk=job.pk, status__in=ACTIVE_JOB_STATUSES).update(**fields)
    if updated:
        for field, value in fields.items():
            setattr(job, field, value)
    else:
        job.refresh_from_db()
    return bool(updated)


def mark_job_failed(job, message):
    return _finish_job(job, SkillSyncJob.FAILED, str(message))


def _fail_job(job, message):
    mark_job_failed(job, message)
    return SkillSyncError(message)


def _job_stale_seconds():
    try:
        return max(1, int(os.environ.get("SKILL_JOB_STALE_SECONDS", DEFAULT_JOB_STALE_SECONDS)))
    except ValueError:
        return DEFAULT_JOB_STALE_SECONDS


def _read_metadata(content):
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    metadata = {}
    lines = parts[1].splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in {"name", "description"}:
            if value in {"|", ">", "|-", ">-", "|+", ">+"}:
                block = []
                index += 1
                while index < len(lines) and (not lines[index].strip() or lines[index][:1].isspace()):
                    block.append(lines[index].strip())
                    index += 1
                metadata[key] = ("\n" if value.startswith("|") else " ").join(block).strip()
                continue
            metadata[key] = value.strip('"').strip("'")
        index += 1
    return metadata


def _archive_directory(source_directory, archive_path):
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_directory.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and ".git" not in path.parts:
                archive.write(path, path.relative_to(source_directory.parent))
