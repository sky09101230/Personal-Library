import hashlib
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from django.core.files import File
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.box_upload.services import LiteratureStorageError
from apps.box_upload.storage import NAS_WEBDAV

from .ai_enrichment import SkillEnrichmentError, generate_skill_enrichment
from .models import GitHubSkillSource, SharedSkill, SharedSkillRelease, SkillCandidate, SkillPurpose, SkillSyncJob
from .services import (
    SkillSyncError,
    _archive_directory,
    _fail_job,
    _finish_job,
    _read_metadata,
    _run_git,
    _start_job,
    _update_job,
)
from .storage import get_nas_skill_candidate_storage, get_nas_skill_storage


MAX_ARCHIVE_SIZE = 10 * 1024 * 1024
MAX_MEMBER_COUNT = 200
MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024
MAX_SKILL_DOCUMENT_SIZE = 1024 * 1024
FORBIDDEN_NAMES = {".env", "credentials", "credentials.json", "id_rsa", "id_ed25519"}
FORBIDDEN_EXTENSIONS = {
    ".pdf", ".csv", ".tsv", ".xls", ".xlsx", ".sqlite", ".sqlite3", ".db",
    ".faiss", ".index", ".pt", ".pth", ".ckpt", ".onnx", ".h5", ".hdf5",
    ".npy", ".npz", ".mat", ".pem", ".key", ".p12", ".pfx",
}
TEXT_EXTENSIONS = {".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".sh", ".ps1"}
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9]{20,}\b"),
)


class CandidateValidationError(Exception):
    pass


class CandidatePublishError(Exception):
    pass


def inspect_skill_zip(uploaded_file):
    if uploaded_file.size > MAX_ARCHIVE_SIZE:
        raise CandidateValidationError("ZIP 不能超过 10 MiB。")
    uploaded_file.seek(0)
    try:
        archive = zipfile.ZipFile(uploaded_file)
    except (zipfile.BadZipFile, OSError) as exc:
        raise CandidateValidationError("文件不是有效的 ZIP。") from exc
    with archive:
        members = sorted(
            (member for member in archive.infolist() if not member.is_dir()),
            key=lambda member: member.filename.casefold(),
        )
        if not members or len(members) > MAX_MEMBER_COUNT:
            raise CandidateValidationError("ZIP 必须包含 1 至 200 个文件。")
        if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_SIZE:
            raise CandidateValidationError("ZIP 解压后的总大小不能超过 50 MiB。")
        skill_members = []
        seen_paths = set()
        content_digest = hashlib.sha256()
        for member in members:
            path = _safe_member_path(member)
            normalized_path = path.as_posix().casefold()
            if normalized_path in seen_paths:
                raise CandidateValidationError("ZIP 包含重复文件路径。")
            seen_paths.add(normalized_path)
            _check_forbidden_file(path)
            content_digest.update(normalized_path.encode("utf-8"))
            content_digest.update(b"\0")
            inspected_text = bytearray()
            with archive.open(member) as stream:
                while chunk := stream.read(64 * 1024):
                    content_digest.update(chunk)
                    if path.suffix.lower() in TEXT_EXTENSIONS and len(inspected_text) <= 1024 * 1024:
                        inspected_text.extend(chunk)
            content_digest.update(b"\0")
            if path.name.lower() == "skill.md":
                skill_members.append(member)
            if inspected_text and any(pattern.search(inspected_text) for pattern in SECRET_PATTERNS):
                raise CandidateValidationError("ZIP 包含疑似密钥或访问令牌，不能投稿。")
        if len(skill_members) != 1:
            raise CandidateValidationError("一个 ZIP 必须且只能包含一个 SKILL.md。")
        if skill_members[0].file_size > MAX_SKILL_DOCUMENT_SIZE:
            raise CandidateValidationError("SKILL.md 不能超过 1 MiB。")
        try:
            document = archive.read(skill_members[0]).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CandidateValidationError("SKILL.md 必须使用 UTF-8 编码。") from exc
        metadata = _read_metadata(document)
        directory_name = PurePosixPath(skill_members[0].filename).parent.name or "skill"
        name = (metadata.get("name") or directory_name).strip()[:200]
        digest = content_digest.hexdigest()
        slug = (slugify(name) or slugify(directory_name) or f"skill-{digest[:12]}")[:100]
        warnings = []
        if not metadata.get("name"):
            warnings.append("SKILL.md 缺少 name，已使用目录名。")
        if not metadata.get("description"):
            warnings.append("SKILL.md 缺少 description，等待自动摘要或人工补全。")
        uploaded_file.seek(0)
        return {
            "name": name,
            "slug": slug,
            "description": metadata.get("description", "")[:400],
            "document": document,
            "content_sha256": digest,
            "source_path": str(PurePosixPath(skill_members[0].filename).parent),
            "warnings": warnings,
        }


def create_uploaded_candidate(uploaded_file, user, storage=None):
    inspected = inspect_skill_zip(uploaded_file)
    existing = SkillCandidate.objects.filter(
        origin=SkillCandidate.Origin.UPLOAD,
        submitted_by=user,
        content_sha256=inspected["content_sha256"],
    ).first()
    if existing:
        return existing, False
    storage = storage or get_nas_skill_candidate_storage()
    try:
        storage.ensure_root()
        uploaded_file.seek(0)
        remote_path = storage.upload(uploaded_file)
    except LiteratureStorageError as exc:
        raise CandidateValidationError(str(exc)) from exc
    try:
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=user,
            name=inspected["name"],
            slug=inspected["slug"],
            description=inspected["description"],
            original_name=Path(uploaded_file.name).name[:255],
            source_path=inspected["source_path"],
            content_sha256=inspected["content_sha256"],
            archive_remote_path=remote_path,
            archive_size=uploaded_file.size,
            validation_warnings=inspected["warnings"],
        )
    except Exception:
        try:
            storage.delete(remote_path)
        except LiteratureStorageError:
            pass
        raise
    enrich_candidate(candidate, inspected["document"])
    return candidate, True


def enrich_candidate(candidate, document):
    purposes = list(SkillPurpose.objects.filter(subpurposes__isnull=True).select_related("parent"))
    purposes_by_slug = {purpose.slug: purpose for purpose in purposes}
    try:
        enrichment = generate_skill_enrichment(candidate.name, document, purposes)
    except SkillEnrichmentError as exc:
        warning = f"自动摘要与分类暂不可用（{exc.code}）。"
        candidate.validation_warnings = [
            item for item in candidate.validation_warnings if not item.startswith("自动摘要与分类暂不可用")
        ] + [warning]
        candidate.save(update_fields=["validation_warnings", "updated_at"])
        return candidate
    candidate.ai_generated_description = enrichment["summary"]
    candidate.description = enrichment["summary"]
    candidate.ai_summary_model = enrichment["model"]
    candidate.ai_summary_prompt_version = enrichment["prompt_version"]
    update_fields = [
        "ai_generated_description", "description", "ai_summary_model",
        "ai_summary_prompt_version", "updated_at",
    ]
    if not candidate.purpose_is_manual:
        candidate.purpose = purposes_by_slug.get(enrichment["purpose_slug"])
        update_fields.append("purpose")
    candidate.validation_warnings = [
        item for item in candidate.validation_warnings
        if not item.startswith("自动摘要与分类暂不可用")
    ]
    update_fields.append("validation_warnings")
    candidate.save(update_fields=update_fields)
    return candidate


def scan_github_candidates(
    job=None,
    source_id=None,
    source_path=None,
    expected_commit=None,
    license_path=None,
    license_spdx=None,
):
    _start_job(job)
    sources = GitHubSkillSource.objects.filter(is_enabled=True)
    if source_id is not None:
        sources = sources.filter(pk=source_id)
    sources = list(sources)
    if not sources:
        raise _fail_job(job, "Selected GitHub skill source is not enabled or does not exist.")
    if source_path is not None and len(sources) != 1:
        raise _fail_job(job, "A selected Skill directory requires exactly one GitHub source.")
    storage = get_nas_skill_candidate_storage()
    try:
        storage.ensure_root()
    except LiteratureStorageError as exc:
        raise _fail_job(job, str(exc)) from exc
    if job is not None:
        _update_job(job, sources_total=len(sources))
    results = []
    errors = []
    for source in sources:
        _update_job(job, current_source=source.name, current_skill="")
        try:
            scan_options = {}
            if source_path is not None:
                scan_options = {
                    "source_path": source_path,
                    "expected_commit": expected_commit,
                    "license_path": license_path,
                    "license_spdx": license_spdx,
                }
            results.append(_scan_source(source, storage, job=job, **scan_options))
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


def _scan_source(
    source,
    storage,
    job=None,
    source_path=None,
    expected_commit=None,
    license_path=None,
    license_spdx=None,
):
    with tempfile.TemporaryDirectory(prefix="plab-skill-scan-") as temporary_directory:
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
        if expected_commit and commit.casefold() != expected_commit.casefold():
            raise SkillSyncError(f"{source.name}: 仓库已有新提交，请重新搜索后再导入。")
        repository_root = repository.resolve()
        license_file = _repository_file(repository_root, license_path) if license_path else None
        if license_file is not None and (license_file.is_symlink() or not license_file.is_file()):
            raise SkillSyncError(f"{source.name}: 仓库许可证文件已不存在，请重新搜索后再导入。")
        if source_path is None:
            skill_files = list(repository.rglob("SKILL.md"))
        else:
            skill_directory = _repository_file(repository_root, source_path, allow_root=True)
            skill_file = skill_directory / "SKILL.md"
            if skill_file.is_symlink() or not skill_file.is_file():
                raise SkillSyncError(f"{source.name}: 所选 SKILL.md 已不存在，请重新搜索后再导入。")
            skill_files = [skill_file]
        if job is not None:
            _update_job(job, skills_total=job.skills_total + len(skill_files))
        refreshed = []
        skipped = []
        for index, skill_file in enumerate(skill_files):
            source_path = skill_file.parent.relative_to(repository).as_posix()
            archive_path = Path(temporary_directory) / f"candidate-{index}.zip"
            if license_file is None or license_file.is_relative_to(skill_file.parent):
                _archive_directory(skill_file.parent, archive_path)
            else:
                _archive_directory(skill_file.parent, archive_path, license_file=license_file)
            with archive_path.open("rb") as raw:
                archive = File(raw, name=f"{source.slug}-{skill_file.parent.name}-{commit[:12]}.zip")
                try:
                    inspected = inspect_skill_zip(archive)
                except CandidateValidationError as exc:
                    _update_job(job, skipped_count=(job.skipped_count + 1) if job is not None else 0, skills_processed=(job.skills_processed + 1) if job is not None else 0)
                    skipped.append((source_path, str(exc)))
                    continue
                if license_spdx:
                    inspected["warnings"].append(f"GitHub 仓库许可证：{license_spdx}（已随快照保存）。")
                _update_job(job, current_skill=inspected["name"])
                candidate = SkillCandidate.objects.filter(source=source, source_path=source_path).first()
                if candidate and candidate.content_sha256 == inspected["content_sha256"]:
                    candidate.source_commit = commit
                    candidate.save(update_fields=["source_commit", "updated_at"])
                    skipped.append(candidate)
                    _update_job(job, skipped_count=(job.skipped_count + 1) if job is not None else 0, skills_processed=(job.skills_processed + 1) if job is not None else 0)
                    continue
                archive.seek(0)
                try:
                    remote_path = storage.upload(archive)
                except LiteratureStorageError as exc:
                    raise SkillSyncError(f"{inspected['name']}: {exc}") from exc
            old_remote_path = candidate.archive_remote_path if candidate else ""
            defaults = {
                "origin": SkillCandidate.Origin.GITHUB,
                "status": SkillCandidate.Status.PENDING,
                "name": inspected["name"],
                "slug": inspected["slug"],
                "description": inspected["description"],
                "original_name": archive.name,
                "source_commit": commit,
                "content_sha256": inspected["content_sha256"],
                "archive_remote_path": remote_path,
                "archive_size": archive_path.stat().st_size,
                "validation_errors": [],
                "validation_warnings": inspected["warnings"],
                "rejection_reason": "",
                "reviewed_by": None,
                "reviewed_at": None,
            }
            if candidate and candidate.purpose_is_manual:
                defaults["purpose"] = candidate.purpose
                defaults["purpose_is_manual"] = True
            candidate, _ = SkillCandidate.objects.update_or_create(
                source=source,
                source_path=source_path,
                defaults=defaults,
            )
            enrich_candidate(candidate, inspected["document"])
            if old_remote_path and old_remote_path != remote_path:
                try:
                    storage.delete(old_remote_path)
                except LiteratureStorageError:
                    pass
            refreshed.append(candidate)
            _update_job(job, uploaded_count=(job.uploaded_count + 1) if job is not None else 0, skills_processed=(job.skills_processed + 1) if job is not None else 0)
        return source, refreshed, skipped, commit


def _repository_file(repository_root, relative_path, allow_root=False):
    relative_path = str(relative_path or "")
    path = PurePosixPath(relative_path)
    if (
        "\\" in relative_path
        or "\0" in relative_path
        or path.is_absolute()
        or ".." in path.parts
        or (not path.parts and not allow_root)
    ):
        raise SkillSyncError("GitHub repository path is invalid.")
    resolved = repository_root.joinpath(*path.parts).resolve()
    if not resolved.is_relative_to(repository_root):
        raise SkillSyncError("GitHub repository path escapes the repository.")
    return resolved


def publish_candidate(candidate, reviewer, formal_storage=None, candidate_storage=None):
    if candidate.status != SkillCandidate.Status.PENDING:
        raise CandidatePublishError("只有待审核候选可以发布。")
    if candidate.validation_errors or not candidate.description or candidate.purpose is None:
        raise CandidatePublishError("候选必须通过校验并具有摘要和分类。")
    if not candidate.archive_remote_path:
        raise CandidatePublishError("候选快照不存在，请重新投稿或扫描。")
    if candidate.origin == SkillCandidate.Origin.UPLOAD and candidate.published_skill is None:
        if SharedSkill.objects.filter(slug=candidate.slug).exists():
            raise CandidatePublishError("正式库中已存在同名 slug，请先处理冲突。")
    candidate_storage = candidate_storage or get_nas_skill_candidate_storage()
    formal_storage = formal_storage or get_nas_skill_storage()
    try:
        formal_storage.ensure_root()
        stream = candidate_storage.open_stream(candidate.archive_remote_path)
        archive_name = candidate.original_name or f"{candidate.slug}-{candidate.content_sha256[:12]}.zip"
        with tempfile.SpooledTemporaryFile(max_size=MAX_ARCHIVE_SIZE) as temporary:
            for chunk in stream.iter_chunks():
                temporary.write(chunk)
            temporary.seek(0)
            remote_path = formal_storage.upload(File(temporary, name=archive_name))
    except LiteratureStorageError as exc:
        raise CandidatePublishError(str(exc)) from exc
    revision = candidate.source_commit or candidate.content_sha256
    try:
        with transaction.atomic():
            candidate = SkillCandidate.objects.select_for_update().get(pk=candidate.pk)
            if candidate.status != SkillCandidate.Status.PENDING:
                raise CandidatePublishError("只有待审核候选可以发布。")
            if candidate.published_skill_id:
                skill = candidate.published_skill
            elif candidate.origin == SkillCandidate.Origin.GITHUB:
                skill = SharedSkill.objects.filter(source=candidate.source, slug=candidate.slug).first()
            else:
                skill = None
            if skill is None:
                skill = SharedSkill(source=candidate.source, slug=candidate.slug)
            skill.name = candidate.name
            skill.description = candidate.description
            skill.purpose = candidate.purpose
            skill.purpose_is_manual = candidate.purpose_is_manual
            skill.ai_generated_description = candidate.ai_generated_description
            skill.ai_summary_commit = revision
            skill.ai_summary_model = candidate.ai_summary_model
            skill.ai_summary_prompt_version = candidate.ai_summary_prompt_version
            skill.source_path = candidate.source_path
            skill.last_synced_commit = revision
            skill.save()
            SharedSkillRelease.objects.create(
                skill=skill,
                git_commit=revision,
                storage_backend=NAS_WEBDAV,
                repository_id="",
                archive_name=archive_name,
                archive_remote_path=remote_path,
                archive_size=candidate.archive_size,
            )
            candidate.status = SkillCandidate.Status.PUBLISHED
            candidate.published_skill = skill
            candidate.reviewed_by = reviewer
            candidate.reviewed_at = timezone.now()
            candidate.rejection_reason = ""
            candidate.save(update_fields=["status", "published_skill", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
    except Exception as exc:
        try:
            formal_storage.delete(remote_path)
        except LiteratureStorageError:
            pass
        if isinstance(exc, CandidatePublishError):
            raise
        raise CandidatePublishError("正式记录写入失败，已清理本次发布对象。") from exc
    _delete_candidate_snapshot(candidate, candidate_storage)
    return skill


def reject_candidate(candidate, reviewer, reason, storage=None):
    if candidate.status != SkillCandidate.Status.PENDING:
        raise CandidatePublishError("只有待审核候选可以拒绝。")
    candidate.status = SkillCandidate.Status.REJECTED
    candidate.reviewed_by = reviewer
    candidate.reviewed_at = timezone.now()
    candidate.rejection_reason = reason.strip()
    candidate.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
    _delete_candidate_snapshot(candidate, storage or get_nas_skill_candidate_storage())
    return candidate


def _delete_candidate_snapshot(candidate, storage):
    if not candidate.archive_remote_path:
        return
    try:
        storage.delete(candidate.archive_remote_path)
    except LiteratureStorageError:
        return
    candidate.archive_remote_path = ""
    candidate.archive_size = 0
    candidate.save(update_fields=["archive_remote_path", "archive_size", "updated_at"])


def _safe_member_path(member):
    name = member.filename
    path = PurePosixPath(name)
    mode = (member.external_attr >> 16) & 0o170000
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or (path.parts and ":" in path.parts[0])
        or mode == stat.S_IFLNK
        or member.flag_bits & 0x1
    ):
        raise CandidateValidationError("ZIP 包含不安全路径、符号链接或加密文件。")
    return path


def _check_forbidden_file(path):
    name = path.name.lower()
    if ".git" in {part.lower() for part in path.parts} or name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_EXTENSIONS:
        raise CandidateValidationError(f"ZIP 包含禁止入库的文件类型：{path.suffix.lower() or name}。")
