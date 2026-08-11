import tempfile
import zipfile
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.box_upload.services import LiteratureStorageError
from apps.box_upload.storage import NAS_WEBDAV, NJU_BOX
from apps.skills.models import SharedSkillRelease
from apps.skills.services import SkillSyncError, _archive_directory, _run_git
from apps.skills.storage import get_nas_skill_storage, open_skill_stream


class Command(BaseCommand):
    help = "Copy legacy Skill ZIP archives from NJU Box to NAS without deleting the source files."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--rebuild-from-git",
            action="store_true",
            help="Rebuild archives from their recorded Git commit when NJU Box is unavailable.",
        )

    def handle(self, *args, **options):
        storage = get_nas_skill_storage()
        try:
            storage.ensure_root()
        except LiteratureStorageError as exc:
            raise CommandError(str(exc)) from exc

        releases = SharedSkillRelease.objects.filter(storage_backend=NJU_BOX).select_related(
            "skill", "skill__source"
        ).order_by("id")
        if options["limit"] > 0:
            releases = releases[: options["limit"]]
        migrated = failed = 0
        with tempfile.TemporaryDirectory(prefix="plab-skill-migration-") as temporary_directory:
            repositories = {}
            for release in releases:
                archive_path = Path(temporary_directory) / f"{release.pk}.zip"
                try:
                    existing = SharedSkillRelease.objects.filter(
                        skill=release.skill,
                        git_commit=release.git_commit,
                        storage_backend=NAS_WEBDAV,
                    ).exclude(pk=release.pk).first()
                    if existing:
                        SharedSkillRelease.objects.filter(pk=release.pk, storage_backend=NJU_BOX).update(
                            storage_backend=NAS_WEBDAV,
                            archive_remote_path=existing.archive_remote_path,
                            archive_size=existing.archive_size,
                        )
                        migrated += 1
                        self.stdout.write(f"release={release.pk} reused existing NAS archive")
                        continue

                    if options["rebuild_from_git"]:
                        source = release.skill.source
                        if source is None:
                            raise SkillSyncError("Skill has no Git source")
                        key = (source.pk, release.git_commit)
                        repository = repositories.get(key)
                        if repository is None:
                            repository = Path(temporary_directory) / f"repository-{source.pk}-{release.git_commit[:12]}"
                            _run_git("clone", source.repository_url, str(repository))
                            _run_git("-C", str(repository), "checkout", "--detach", release.git_commit)
                            repositories[key] = repository
                        source_directory = (repository / release.skill.source_path).resolve()
                        if repository.resolve() not in source_directory.parents or not (source_directory / "SKILL.md").is_file():
                            raise SkillSyncError("recorded Skill path is unavailable at the recorded commit")
                        _archive_directory(source_directory, archive_path)
                    else:
                        upstream = open_skill_stream(release)
                        with archive_path.open("wb") as archive:
                            for chunk in upstream.iter_chunks():
                                archive.write(chunk)
                    size = archive_path.stat().st_size
                    if not options["rebuild_from_git"] and release.archive_size and size != release.archive_size:
                        raise LiteratureStorageError(
                            f"archive size mismatch: expected {release.archive_size}, got {size}"
                        )
                    with zipfile.ZipFile(archive_path) as archive:
                        corrupt_member = archive.testzip()
                    if corrupt_member:
                        raise LiteratureStorageError(f"corrupt ZIP member: {corrupt_member}")
                    with archive_path.open("rb") as archive:
                        remote_path = storage.upload(File(archive, name=release.archive_name))
                    SharedSkillRelease.objects.filter(pk=release.pk, storage_backend=NJU_BOX).update(
                        storage_backend=NAS_WEBDAV,
                        repository_id="",
                        archive_remote_path=remote_path,
                        archive_size=size,
                    )
                except (LiteratureStorageError, OSError, SkillSyncError, zipfile.BadZipFile) as exc:
                    failed += 1
                    self.stderr.write(f"release={release.pk} failed: {exc}")
                else:
                    migrated += 1
                    self.stdout.write(f"release={release.pk} migrated")

        self.stdout.write(self.style.SUCCESS(f"Migrated {migrated}; failed {failed}."))
        if failed:
            raise CommandError(f"{failed} Skill archive(s) could not be migrated; their NJU Box records were kept.")
