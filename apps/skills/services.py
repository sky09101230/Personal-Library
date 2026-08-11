import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from django.core.files import File
from django.utils import timezone
from django.utils.text import slugify

from apps.box_upload.services import LiteratureStorageError
from apps.box_upload.storage import NAS_WEBDAV

from .ai_enrichment import SkillEnrichmentError, generate_skill_enrichment
from .models import GitHubSkillSource, SharedSkill, SharedSkillRelease, SkillPurpose, SkillSyncJob
from .storage import get_nas_skill_storage


class SkillSyncError(Exception):
    pass


def sync_shared_skills(job=None, source_id=None):
    if job is not None:
        job.status = SkillSyncJob.RUNNING
        job.started_at = timezone.now()
        job.error = ""
        job.save(update_fields=["status", "started_at", "error"])
    try:
        storage = get_nas_skill_storage()
        storage.ensure_root()
    except LiteratureStorageError as exc:
        raise _fail_job(job, str(exc)) from exc
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
        job.sources_total = len(sources)
        job.save(update_fields=["sources_total"])
    results = []
    errors = []
    for source in sources:
        _update_job(job, current_source=source.name, current_skill="")
        try:
            results.append(_sync_source(source, storage, job=job))
        except SkillSyncError as exc:
            errors.append(str(exc))
            if job is not None:
                job.failed_sources += 1
                job.error = "\n".join(errors)
                job.save(update_fields=["failed_sources", "error"])
        else:
            _update_job(job, sources_completed=(job.sources_completed + 1) if job is not None else 0)
    if job is not None:
        job.status = SkillSyncJob.FAILED if errors and not results else SkillSyncJob.COMPLETED
        job.current_source = ""
        job.current_skill = ""
        job.error = "\n".join(errors)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "current_source", "current_skill", "error", "finished_at"])
    if errors and not results:
        raise SkillSyncError("\n".join(errors))
    return results


def enrich_shared_skills(job=None, source_id=None):
    if job is not None:
        job.status = SkillSyncJob.RUNNING
        job.started_at = timezone.now()
        job.error = ""
        job.save(update_fields=["status", "started_at", "error"])
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
        job.sources_total = len(sources)
        job.save(update_fields=["sources_total"])
    results = []
    errors = []
    for source in sources:
        _update_job(job, current_source=source.name, current_skill="")
        try:
            results.append(_enrich_source(source, job=job))
        except SkillSyncError as exc:
            errors.append(str(exc))
            if job is not None:
                job.failed_sources += 1
                job.error = "\n".join(errors)
                job.save(update_fields=["failed_sources", "error"])
        else:
            _update_job(job, sources_completed=(job.sources_completed + 1) if job is not None else 0)
    if job is not None:
        job.status = SkillSyncJob.FAILED if errors and not results else SkillSyncJob.COMPLETED
        job.current_source = ""
        job.current_skill = ""
        job.error = "\n".join(errors)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "current_source", "current_skill", "error", "finished_at"])
    if errors and not results:
        raise SkillSyncError("\n".join(errors))
    return results


def _sync_source(source, storage, job=None):
    with tempfile.TemporaryDirectory(prefix="plab-skills-") as temporary_directory:
        repository = Path(temporary_directory) / "repository"
        clone_args = ["clone", "--depth", "1"]
        if source.branch:
            clone_args.extend(["--branch", source.branch])
        clone_args.extend([source.repository_url, str(repository)])
        try:
            _run_git(*clone_args)
        except SkillSyncError as exc:
            raise SkillSyncError(f"{source.name}: {exc}") from exc
        commit = _run_git("-C", str(repository), "rev-parse", "HEAD").strip()
        synced = []
        skipped = []
        skill_files = list(repository.rglob("SKILL.md"))
        if job is not None:
            job.skills_total += len(skill_files)
            job.save(update_fields=["skills_total"])
        for skill_file in skill_files:
            document = skill_file.read_text(encoding="utf-8")
            metadata = _read_metadata(document)
            skill_name = metadata.get("name") or skill_file.parent.name
            skill_slug = slugify(skill_name) or slugify(skill_file.parent.name)
            description = metadata.get("description", "")
            _update_job(job, current_skill=skill_name)
            source_path = skill_file.parent.relative_to(repository).as_posix()
            skill = SharedSkill.objects.filter(source=source, slug=skill_slug).first()
            defaults = {"name": skill_name, "source_path": source_path}
            if skill is None or (not skill.ai_summary_commit and not skill.description_is_manual):
                defaults["description"] = description
            skill, _ = SharedSkill.objects.update_or_create(
                source=source,
                slug=skill_slug,
                defaults=defaults,
            )
            if SharedSkillRelease.objects.filter(
                skill=skill,
                git_commit=commit,
                storage_backend=NAS_WEBDAV,
            ).exists():
                if skill.last_synced_commit != commit:
                    skill.last_synced_commit = commit
                    skill.save(update_fields=["last_synced_commit", "updated_at"])
                skipped.append(skill)
                _update_job(job, skipped_count=(job.skipped_count + 1) if job is not None else 0, skills_processed=(job.skills_processed + 1) if job is not None else 0)
                continue

            archive_name = f"{source.slug}-{skill_slug}-{commit[:12]}.zip"
            archive_path = Path(temporary_directory) / archive_name
            _archive_directory(skill_file.parent, archive_path)
            try:
                with archive_path.open("rb") as archive:
                    remote_path = storage.upload(File(archive, name=archive_name))
            except LiteratureStorageError as exc:
                raise SkillSyncError(f"{skill_name}: {exc}") from exc
            SharedSkillRelease.objects.create(
                skill=skill,
                git_commit=commit,
                storage_backend=NAS_WEBDAV,
                repository_id="",
                archive_name=archive_name,
                archive_remote_path=remote_path,
                archive_size=archive_path.stat().st_size,
            )
            skill.last_synced_commit = commit
            skill.save(update_fields=["last_synced_commit", "updated_at"])
            synced.append(skill)
            _update_job(job, uploaded_count=(job.uploaded_count + 1) if job is not None else 0, skills_processed=(job.skills_processed + 1) if job is not None else 0)
        return source, synced, skipped, commit


def _enrich_source(source, job=None):
    with tempfile.TemporaryDirectory(prefix="plab-skill-enrichment-") as temporary_directory:
        repository = Path(temporary_directory) / "repository"
        clone_args = ["clone", "--depth", "1"]
        if source.branch:
            clone_args.extend(["--branch", source.branch])
        clone_args.extend([source.repository_url, str(repository)])
        try:
            _run_git(*clone_args)
        except SkillSyncError as exc:
            raise SkillSyncError(f"{source.name}: {exc}") from exc
        commit = _run_git("-C", str(repository), "rev-parse", "HEAD").strip()
        purposes = list(SkillPurpose.objects.filter(subpurposes__isnull=True).select_related("parent"))
        purposes_by_slug = {purpose.slug: purpose for purpose in purposes}
        skill_files = list(repository.rglob("SKILL.md"))
        if job is not None:
            job.skills_total += len(skill_files)
            job.save(update_fields=["skills_total"])
        enriched = []
        skipped = []
        for skill_file in skill_files:
            document = skill_file.read_text(encoding="utf-8")
            metadata = _read_metadata(document)
            skill_name = metadata.get("name") or skill_file.parent.name
            skill_slug = slugify(skill_name) or slugify(skill_file.parent.name)
            _update_job(job, current_skill=skill_name)
            skill = SharedSkill.objects.filter(source=source, slug=skill_slug).first()
            if skill is None:
                skipped.append(skill_slug)
                _update_job(
                    job,
                    skipped_count=(job.skipped_count + 1) if job is not None else 0,
                    skills_processed=(job.skills_processed + 1) if job is not None else 0,
                )
                continue
            try:
                enrichment = generate_skill_enrichment(skill_name, document, purposes)
            except SkillEnrichmentError as exc:
                raise SkillSyncError(f"{skill_name}: DeepSeek enrichment failed ({exc.code}): {exc}") from exc
            skill.name = skill_name
            skill.ai_generated_description = enrichment["summary"]
            skill.ai_summary_commit = commit
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
        return source, enriched, skipped, commit


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
    for field, value in fields.items():
        setattr(job, field, value)
    job.save(update_fields=list(fields))


def _fail_job(job, message):
    if job is not None:
        job.status = SkillSyncJob.FAILED
        job.error = message
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
    return SkillSyncError(message)


def _read_metadata(content):
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    metadata = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() in {"name", "description"}:
            metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata


def _archive_directory(source_directory, archive_path):
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_directory.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(source_directory.parent))
