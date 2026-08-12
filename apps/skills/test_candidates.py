from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .candidate_services import (
    CandidatePublishError,
    CandidateValidationError,
    _scan_source,
    create_uploaded_candidate,
    enrich_candidate,
    inspect_skill_zip,
    publish_candidate,
    scan_github_candidates,
)
from .models import GitHubSkillSource, SharedSkill, SharedSkillRelease, SkillCandidate, SkillPurpose, SkillSyncJob
from .services import SkillSyncError, _archive_directory, _read_metadata


def skill_zip(files, name="skill.zip"):
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return SimpleUploadedFile(name, payload.getvalue(), content_type="application/zip")


class CandidateArchiveTests(TestCase):
    def test_valid_zip_uses_multiline_metadata(self):
        archive = skill_zip({
            "demo/SKILL.md": "---\nname: demo-skill\ndescription: >\n  First line\n  second line\n---\n# Demo",
        })

        result = inspect_skill_zip(archive)

        self.assertEqual(result["name"], "demo-skill")
        self.assertEqual(result["description"], "First line second line")
        self.assertEqual(_read_metadata("---\ndescription: |\n  a\n  b\n---")["description"], "a\nb")

    def test_zip_rejects_ambiguous_or_forbidden_content(self):
        for archive in (
            skill_zip({"a/SKILL.md": "# A", "b/SKILL.md": "# B"}),
            skill_zip({"../SKILL.md": "# Escape"}),
            skill_zip({"demo/SKILL.md": "# Demo", "demo/data.csv": "1,2"}),
            skill_zip({"demo/SKILL.md": "# Demo", "demo/.git/config": "secret"}),
            skill_zip({"demo/SKILL.md": "# Demo", "demo/note.txt": "ghp_abcdefghijklmnopqrstuvwxyz"}),
        ):
            with self.subTest(archive=archive.name), self.assertRaises(CandidateValidationError):
                inspect_skill_zip(archive)

    def test_content_fingerprint_ignores_zip_member_order(self):
        first = skill_zip({"demo/SKILL.md": "# Demo", "demo/readme.txt": "same"})
        second = skill_zip({"demo/readme.txt": "same", "demo/SKILL.md": "# Demo"})

        self.assertEqual(
            inspect_skill_zip(first)["content_sha256"],
            inspect_skill_zip(second)["content_sha256"],
        )

    def test_repository_archive_rejects_symbolic_links(self):
        source = MagicMock()
        source.rglob.return_value = [MagicMock(is_symlink=MagicMock(return_value=True))]
        with self.assertRaisesMessage(SkillSyncError, "symbolic link"):
            _archive_directory(source, BytesIO())


class CandidateWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="researcher", password="Strong-pass-1234")
        self.admin = User.objects.create_user(username="admin", password="Strong-pass-1234", is_staff=True)
        self.purpose = SkillPurpose.objects.get(slug="literature-read")

    @patch("apps.skills.candidate_services.generate_skill_enrichment")
    def test_upload_creates_private_enriched_candidate_only(self, generate):
        generate.return_value = {
            "summary": "该技能读取论文并整理关键信息。适合需要快速形成文献笔记时使用。",
            "purpose_slug": self.purpose.slug,
            "model": "deepseek-test",
            "prompt_version": "test-v1",
        }
        storage = MagicMock()
        storage.upload.return_value = "/private/candidate.zip"
        archive = skill_zip({"demo/SKILL.md": "---\nname: demo\ndescription: Demo\n---\n# Demo"})

        candidate, created = create_uploaded_candidate(archive, self.user, storage=storage)

        self.assertTrue(created)
        self.assertEqual(candidate.purpose, self.purpose)
        self.assertEqual(candidate.status, SkillCandidate.Status.PENDING)
        self.assertEqual(SharedSkill.objects.count(), 0)
        storage.ensure_root.assert_called_once_with()

    def test_non_staff_cannot_read_another_users_candidate(self):
        other = User.objects.create_user(username="other", password="Strong-pass-1234")
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=other,
            name="private",
            slug="private",
            content_sha256="a" * 64,
        )
        self.client.force_login(self.user)

        response = self.client.get(f"/skills/candidates/{candidate.pk}/")

        self.assertEqual(response.status_code, 404)

    @patch("apps.skills.candidate_services.generate_skill_enrichment")
    def test_manual_category_survives_enrichment(self, generate):
        manual = SkillPurpose.objects.get(slug="instrument-control")
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=self.user,
            name="manual",
            slug="manual",
            purpose=manual,
            purpose_is_manual=True,
            content_sha256="b" * 64,
        )
        generate.return_value = {
            "summary": "该技能完成新的自动摘要。适合对应科研流程中使用。",
            "purpose_slug": self.purpose.slug,
            "model": "deepseek-test",
            "prompt_version": "test-v1",
        }

        enrich_candidate(candidate, "# Document")

        candidate.refresh_from_db()
        self.assertEqual(candidate.purpose, manual)
        self.assertEqual(candidate.description, generate.return_value["summary"])

    def test_unchanged_rejected_github_candidate_stays_rejected(self):
        source = GitHubSkillSource.objects.create(
            name="External", slug="external", repository_url="https://github.com/example/skills.git"
        )
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.GITHUB,
            source=source,
            source_path="demo",
            name="demo",
            slug="demo",
            status=SkillCandidate.Status.REJECTED,
            content_sha256="c" * 64,
        )
        skill_file = MagicMock()
        skill_file.parent.relative_to.return_value = Path("demo")
        skill_file.parent.name = "demo"

        def write_archive(_source, destination):
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("demo/SKILL.md", "# Demo")

        with (
            patch("apps.skills.candidate_services._run_git", side_effect=["", "d" * 40]),
            patch("apps.skills.candidate_services.Path.rglob", return_value=[skill_file]),
            patch("apps.skills.candidate_services._archive_directory", side_effect=write_archive),
            patch("apps.skills.candidate_services.inspect_skill_zip", return_value={
                "name": "demo", "slug": "demo", "description": "", "document": "# Demo",
                "content_sha256": "c" * 64, "warnings": [],
            }),
        ):
            _scan_source(source, MagicMock())

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, SkillCandidate.Status.REJECTED)
        self.assertEqual(candidate.source_commit, "d" * 40)

    @patch("apps.skills.candidate_services._scan_source")
    @patch("apps.skills.candidate_services.get_nas_skill_candidate_storage")
    def test_scan_runner_processes_only_selected_source(self, get_storage, scan_source):
        selected = GitHubSkillSource.objects.create(
            name="Selected", slug="selected", repository_url="https://github.com/example/selected.git"
        )
        GitHubSkillSource.objects.create(
            name="Other", slug="other", repository_url="https://github.com/example/other.git"
        )
        scan_source.return_value = (selected, [], [], "a" * 40)
        job = SkillSyncJob.objects.create(operation=SkillSyncJob.SCAN)

        scan_github_candidates(job=job, source_id=selected.pk)

        scan_source.assert_called_once_with(selected, get_storage.return_value, job=job)
        job.refresh_from_db()
        self.assertEqual(job.status, SkillSyncJob.COMPLETED)
        self.assertEqual(job.sources_total, 1)

    def test_publish_copies_snapshot_then_creates_formal_records(self):
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=self.user,
            name="publish-demo",
            slug="publish-demo",
            description="两句话摘要。第二句话摘要。",
            purpose=self.purpose,
            content_sha256="e" * 64,
            archive_remote_path="/private/demo.zip",
            archive_size=3,
        )
        candidate_storage = MagicMock()
        candidate_storage.open_stream.return_value.iter_chunks.return_value = iter((b"zip",))
        formal_storage = MagicMock()
        formal_storage.upload.return_value = "/formal/demo.zip"

        skill = publish_candidate(candidate, self.admin, formal_storage=formal_storage, candidate_storage=candidate_storage)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, SkillCandidate.Status.PUBLISHED)
        self.assertEqual(candidate.archive_remote_path, "")
        self.assertEqual(skill.releases.get().archive_remote_path, "/formal/demo.zip")
        candidate_storage.delete.assert_called_once_with("/private/demo.zip")

    @patch("apps.skills.candidate_services.SharedSkillRelease.objects.create", side_effect=RuntimeError("database failed"))
    def test_publish_rolls_back_database_and_deletes_formal_object(self, _create_release):
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=self.user,
            name="rollback-demo",
            slug="rollback-demo",
            description="两句话摘要。第二句话摘要。",
            purpose=self.purpose,
            content_sha256="f" * 64,
            archive_remote_path="/private/rollback.zip",
            archive_size=3,
        )
        candidate_storage = MagicMock()
        candidate_storage.open_stream.return_value.iter_chunks.return_value = iter((b"zip",))
        formal_storage = MagicMock()
        formal_storage.upload.return_value = "/formal/rollback.zip"

        with self.assertRaises(CandidatePublishError):
            publish_candidate(candidate, self.admin, formal_storage=formal_storage, candidate_storage=candidate_storage)

        self.assertFalse(SharedSkill.objects.filter(slug="rollback-demo").exists())
        formal_storage.delete.assert_called_once_with("/formal/rollback.zip")


class CandidateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="researcher", password="Strong-pass-1234")
        self.other = User.objects.create_user(username="other", password="Strong-pass-1234")
        self.admin = User.objects.create_user(username="admin", password="Strong-pass-1234", is_staff=True)
        self.purpose = SkillPurpose.objects.get(slug="literature-read")
        self.own = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=self.user,
            name="own-candidate",
            slug="own-candidate",
            description="候选摘要。第二句摘要。",
            purpose=self.purpose,
            content_sha256="1" * 64,
            archive_remote_path="/private/own.zip",
        )
        self.foreign = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=self.other,
            name="foreign-candidate",
            slug="foreign-candidate",
            content_sha256="2" * 64,
        )

    def test_researcher_pages_show_only_own_submission(self):
        self.client.force_login(self.user)

        upload_response = self.client.get("/skills/submit/")
        list_response = self.client.get("/skills/candidates/")

        self.assertContains(upload_response, "上传一个 Skill ZIP")
        self.assertContains(list_response, "own-candidate")
        self.assertNotContains(list_response, "foreign-candidate")

    def test_staff_can_render_review_and_lock_manual_category(self):
        self.client.force_login(self.admin)
        detail_response = self.client.get(f"/skills/candidates/{self.own.pk}/")
        self.assertContains(detail_response, "批准并发布")

        with patch("apps.skills.views.publish_candidate") as publish:
            response = self.client.post(
                f"/skills/candidates/{self.own.pk}/review/",
                {
                    "description": "管理员确认的摘要。第二句摘要。",
                    "purpose": self.purpose.pk,
                    "rejection_reason": "",
                    "action": "publish",
                },
            )

        self.assertRedirects(response, "/skills/candidates/")
        self.own.refresh_from_db()
        self.assertTrue(self.own.purpose_is_manual)
        publish.assert_called_once()

    def test_staff_can_reject_unclassified_candidate(self):
        candidate = SkillCandidate.objects.create(
            origin=SkillCandidate.Origin.UPLOAD,
            submitted_by=self.user,
            name="unclassified",
            slug="unclassified",
            content_sha256="3" * 64,
        )
        self.client.force_login(self.admin)

        with patch("apps.skills.views.reject_candidate") as reject:
            response = self.client.post(
                f"/skills/candidates/{candidate.pk}/review/",
                {"action": "reject", "rejection_reason": "内容不适合当前科研库。"},
            )

        self.assertRedirects(response, "/skills/candidates/")
        reject.assert_called_once_with(candidate, self.admin, "内容不适合当前科研库。")

    def test_staff_can_batch_publish_selected_candidates(self):
        self.client.force_login(self.admin)

        with patch("apps.skills.views.publish_candidate") as publish:
            response = self.client.post(
                "/skills/candidates/publish/",
                {"candidate_ids": [self.own.pk]},
            )

        self.assertRedirects(response, "/skills/candidates/")
        publish.assert_called_once_with(self.own, self.admin)

    def test_staff_candidate_list_can_select_all_publishable_rows(self):
        self.client.force_login(self.admin)

        response = self.client.get("/skills/candidates/")

        self.assertContains(response, 'class="content content-wide"')
        self.assertContains(response, "全选当前页")
        self.assertContains(response, 'value="%s"' % self.own.pk)
        self.assertContains(response, 'querySelectorAll(\'input[name="candidate_ids"]\')')
