from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from io import BytesIO
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch
from urllib.parse import urlsplit
import json
import subprocess
import zipfile

from .ai_enrichment import SkillEnrichmentError, generate_skill_enrichment
from .models import FeaturedSkill, GitHubSkillSource, SharedSkill, SharedSkillRelease, SkillPurpose, SkillSyncJob
from .downloads import build_skill_download_url
from .services import (
    SkillSyncError,
    _enrich_source,
    _run_git,
    _sync_source,
    enrich_shared_skills,
    sync_shared_skills,
)
from .tasks import launch_enrichment_job, launch_sync_job


class SkillsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="Strong-pass-1234")
        self.client.force_login(self.user)
        self.source = GitHubSkillSource.objects.create(
            name="PLAB Shared Skills",
            slug="plab-shared-skills",
            repository_url="https://github.com/example/plab-skills.git",
        )
        self.major_purpose = SkillPurpose.objects.create(name="文献工作", slug="literature")
        self.subpurpose = SkillPurpose.objects.create(name="文献提取", slug="literature-extraction", parent=self.major_purpose)
        self.skill = SharedSkill.objects.create(
            source=self.source,
            purpose=self.subpurpose,
            slug="pdf2md",
            name="PDF to Markdown",
            description="Convert academic PDFs to Markdown.",
            source_path="skills/pdf2md",
            last_synced_commit="a" * 40,
        )
        SharedSkillRelease.objects.create(
            skill=self.skill,
            git_commit="a" * 40,
            repository_id="2a38677f-00c6-472e-8265-30b4fa14ff78",
            archive_name="pdf2md-aaaaaaaaaaaa.zip",
            archive_remote_path="/PLAB Skills/pdf2md-aaaaaaaaaaaa.zip",
            archive_size=10,
        )

    def test_skills_index_searches_metadata(self):
        response = self.client.get("/skills/?q=Markdown")

        self.assertContains(response, "PDF to Markdown")
        self.assertContains(response, "详情")

    def test_skills_index_groups_skills_by_purpose(self):
        other_subpurpose = SkillPurpose.objects.create(
            name="文献筛选",
            slug="literature-screening",
            parent=self.major_purpose,
        )
        SharedSkill.objects.create(
            source=self.source,
            purpose=other_subpurpose,
            slug="literature-filter",
            name="Literature Filter",
            description="Screen papers.",
            source_path="filter",
        )

        response = self.client.get("/skills/")

        self.assertContains(response, "文献工作")
        self.assertContains(response, "文献提取")
        self.assertContains(response, "文献筛选")
        self.assertContains(response, "/skills/plab-shared-skills/pdf2md/")
        self.assertContains(response, "/skills/plab-shared-skills/literature-filter/")

    def test_top_level_leaf_purpose_displays_assigned_skills(self):
        leaf_purpose = SkillPurpose.objects.create(name="Standalone Literature Search", slug="standalone-literature-search")
        self.skill.purpose = leaf_purpose
        self.skill.save(update_fields=["purpose", "updated_at"])

        response = self.client.get("/skills/?category=standalone-literature-search")

        self.assertContains(response, "Standalone Literature Search")
        self.assertContains(response, "/skills/plab-shared-skills/pdf2md/")

    def test_featured_page_shows_admin_recommendation_only(self):
        FeaturedSkill.objects.create(
            skill=self.skill,
            recommendation="把 PDF 转成后续阅读和引用流程可用的 Markdown。",
        )
        SharedSkill.objects.create(
            source=self.source,
            purpose=self.subpurpose,
            slug="not-featured",
            name="Not Featured",
            description="Not selected by the administrator.",
            source_path="not-featured",
        )

        response = self.client.get("/skills/featured/")

        self.assertContains(response, "把 PDF 转成后续阅读和引用流程可用的 Markdown。")
        self.assertContains(response, "PDF to Markdown")
        self.assertNotContains(response, "Not Featured")

    def test_uncategorized_skills_are_paginated(self):
        for index in range(25):
            SharedSkill.objects.create(
                source=self.source,
                slug=f"uncategorized-{index}",
                name=f"Uncategorized {index:02d}",
                description="Needs classification.",
                source_path=f"uncategorized/{index}",
            )

        response = self.client.get("/skills/")

        self.assertContains(response, "Uncategorized 00")
        self.assertNotContains(response, "Uncategorized 24")
        self.assertContains(response, "category=uncategorized&page=2")

    def test_skills_detail_shows_latest_release(self):
        response = self.client.get("/skills/plab-shared-skills/pdf2md/")

        self.assertContains(response, "pdf2md-aaaaaaaaaaaa.zip")

    def test_non_staff_cannot_trigger_sync(self):
        response = self.client.post("/skills/sync/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_non_staff_cannot_edit_skill_description(self):
        response = self.client.get("/skills/plab-shared-skills/pdf2md/description/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

        index_response = self.client.get("/skills/")
        self.assertNotContains(index_response, "编辑描述")

    def test_skills_index_lists_only_enabled_sync_sources(self):
        GitHubSkillSource.objects.create(
            name="Disabled source",
            slug="disabled-source",
            repository_url="https://github.com/example/disabled.git",
            is_enabled=False,
        )

        response = self.client.get("/skills/")

        self.assertContains(response, "PLAB Shared Skills")
        self.assertNotContains(response, "Disabled source")

    @patch("apps.skills.views.open_skill_stream")
    def test_download_prefers_nas_release(self, open_stream):
        nas_release = SharedSkillRelease.objects.create(
            skill=self.skill,
            git_commit="a" * 40,
            storage_backend="nas_webdav",
            archive_name="nas.zip",
            archive_remote_path="/public/PLAB_KnowledgeBase/Skills/nas.zip",
            archive_size=10,
        )
        upstream = MagicMock(status=200)
        upstream.iter_chunks.return_value = iter((b"zip",))
        upstream.get_header.return_value = None
        open_stream.return_value = upstream

        response = self.client.get("/skills/pdf2md/download/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"zip")
        self.assertIn("nas.zip", response["Content-Disposition"])
        open_stream.assert_called_once_with(nas_release)

    @patch("apps.skills.views.open_skill_stream")
    def test_signed_download_streams_without_login(self, open_stream):
        release = self.skill.releases.first()
        upstream = MagicMock(status=200)
        upstream.iter_chunks.return_value = iter((b"zip",))
        upstream.get_header.return_value = None
        open_stream.return_value = upstream
        self.client.logout()

        response = self.client.get(urlsplit(build_skill_download_url(release)).path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"zip")


class SkillSyncTests(TestCase):
    @patch("apps.skills.services._archive_directory")
    @patch("apps.skills.services._run_git")
    def test_sync_source_clones_configured_repository_and_branch(
        self, run_git, archive_directory
    ):
        source = GitHubSkillSource.objects.create(
            name="Research Skills",
            slug="research-skills",
            repository_url="https://github.com/example/research-skills.git",
            branch="stable",
        )
        run_git.side_effect = ["", "b" * 40]
        storage = MagicMock()

        with patch("apps.skills.services.Path.rglob", return_value=[]):
            result = _sync_source(source, storage)

        self.assertEqual(result, (source, [], [], "b" * 40))
        self.assertEqual(
            run_git.call_args_list[0],
            call(
                "clone",
                "--depth",
                "1",
                "--branch",
                "stable",
                "https://github.com/example/research-skills.git",
                ANY,
            ),
        )

    @patch("apps.skills.services.generate_skill_enrichment")
    @patch("apps.skills.services._run_git")
    def test_independent_flow_enriches_and_auto_classifies_existing_skill(self, run_git, generate_enrichment):
        source = GitHubSkillSource.objects.create(
            name="Research Skills",
            slug="research-skills",
            repository_url="https://github.com/example/research-skills.git",
        )
        purpose = SkillPurpose.objects.create(name="Test Literature Read", slug="test-literature-read")
        commit = "b" * 40
        skill = SharedSkill.objects.create(
            source=source,
            slug="paper-card-extract",
            name="paper-card-extract",
            description="Old English description.",
            source_path="skills/paper-card-extract",
            last_synced_commit=commit,
        )
        SharedSkillRelease.objects.create(
            skill=skill,
            git_commit=commit,
            storage_backend="nas_webdav",
            archive_name="paper-card.zip",
            archive_remote_path="/skills/paper-card.zip",
            archive_size=10,
        )
        document = "---\nname: paper-card-extract\n---\n# Full Skill documentation"
        skill_file = MagicMock()
        skill_file.read_text.return_value = document
        skill_file.parent.name = "paper-card-extract"
        skill_file.parent.relative_to.return_value = Path("skills/paper-card-extract")
        run_git.side_effect = ["", commit]
        generate_enrichment.return_value = {
            "summary": "该技能从论文 Markdown 中提取结构化文献卡片并保留证据记录。适合需要审慎整理研究事实、判断和复用洞见时使用。",
            "purpose_slug": purpose.slug,
            "model": "deepseek-v4-flash",
            "prompt_version": "plab-skill-enrichment-v1",
        }

        with patch("apps.skills.services.Path.rglob", return_value=[skill_file]):
            result = _enrich_source(source)

        skill.refresh_from_db()
        self.assertEqual(result, (source, [skill], [], commit))
        self.assertEqual(skill.description, generate_enrichment.return_value["summary"])
        self.assertEqual(skill.ai_generated_description, generate_enrichment.return_value["summary"])
        self.assertEqual(skill.purpose, purpose)
        self.assertEqual(skill.ai_summary_commit, commit)
        self.assertEqual(skill.ai_summary_model, "deepseek-v4-flash")
        self.assertEqual(generate_enrichment.call_args.args[1], document)

        manual_purpose = SkillPurpose.objects.create(name="Manual category", slug="manual-category")
        skill.purpose = manual_purpose
        skill.purpose_is_manual = True
        skill.description = "管理员基于模型初稿修改后的展示描述。"
        skill.description_is_manual = True
        skill.save(update_fields=["purpose", "purpose_is_manual", "description", "description_is_manual", "updated_at"])
        generate_enrichment.return_value = {
            **generate_enrichment.return_value,
            "summary": "这是 DeepSeek 重新生成的第一句摘要。这是 DeepSeek 重新生成的第二句摘要。",
        }
        run_git.side_effect = ["", commit]
        with patch("apps.skills.services.Path.rglob", return_value=[skill_file]):
            _enrich_source(source)

        skill.refresh_from_db()
        self.assertEqual(skill.purpose, manual_purpose)
        self.assertEqual(skill.description, "管理员基于模型初稿修改后的展示描述。")
        self.assertEqual(skill.ai_generated_description, generate_enrichment.return_value["summary"])

    @patch("apps.skills.services._enrich_source")
    @patch("apps.skills.services.get_nas_skill_storage")
    def test_enrichment_flow_never_initializes_archive_storage(self, get_storage, enrich_source):
        source = GitHubSkillSource.objects.create(
            name="Research Skills",
            slug="research-skills",
            repository_url="https://github.com/example/research-skills.git",
        )
        enrich_source.return_value = (source, [], [], "b" * 40)
        job = SkillSyncJob.objects.create(operation=SkillSyncJob.ENRICHMENT)

        enrich_shared_skills(job=job, source_id=source.pk)

        get_storage.assert_not_called()
        enrich_source.assert_called_once_with(source, job=job)

    @patch("apps.skills.services.subprocess.run")
    def test_git_failure_keeps_the_actual_git_error(self, run):
        run.side_effect = subprocess.CalledProcessError(128, ["git"], stderr="connection timed out")

        with self.assertRaisesMessage(SkillSyncError, "connection timed out"):
            _run_git("clone", "https://github.com/example/missing.git", "repository")

    @patch("apps.skills.services._sync_source")
    @patch("apps.skills.services.get_nas_skill_storage")
    def test_sync_continues_after_a_source_failure(self, get_storage, sync_source):
        first = GitHubSkillSource.objects.create(
            name="First source",
            slug="first-source",
            repository_url="https://github.com/example/first.git",
        )
        second = GitHubSkillSource.objects.create(
            name="Second source",
            slug="second-source",
            repository_url="https://github.com/example/second.git",
        )
        sync_source.side_effect = [SkillSyncError("First source: network unavailable"), (second, [], [], "a" * 40)]
        job = SkillSyncJob.objects.create()

        sync_shared_skills(job=job)
        job.refresh_from_db()

        self.assertEqual(job.status, SkillSyncJob.COMPLETED)
        self.assertEqual(job.failed_sources, 1)
        self.assertEqual(job.sources_completed, 1)
        self.assertIn("network unavailable", job.error)
        self.assertEqual(sync_source.call_count, 2)
        get_storage.return_value.ensure_root.assert_called_once_with()

    @patch("apps.skills.services._sync_source")
    @patch("apps.skills.services.get_nas_skill_storage")
    def test_sync_imports_only_selected_source(self, get_storage, sync_source):
        first = GitHubSkillSource.objects.create(
            name="First source", slug="first-source", repository_url="https://github.com/example/first.git"
        )
        second = GitHubSkillSource.objects.create(
            name="Second source", slug="second-source", repository_url="https://github.com/example/second.git"
        )
        sync_source.return_value = (second, [], [], "a" * 40)
        job = SkillSyncJob.objects.create()

        sync_shared_skills(job=job, source_id=second.pk)

        sync_source.assert_called_once_with(second, get_storage.return_value, job=job)
        self.assertNotEqual(first.pk, second.pk)
        job.refresh_from_db()
        self.assertEqual(job.sources_total, 1)


class SkillEnrichmentTests(TestCase):
    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-v4-flash"}, clear=False)
    def test_deepseek_reads_document_and_returns_two_sentence_summary(self):
        purpose = SkillPurpose.objects.create(name="Test Literature Read", slug="test-literature-read")
        calls = []

        def request_func(url, body, api_key, timeout):
            calls.append((url, body, api_key, timeout))
            payload = {
                "summary": "该技能把论文内容整理为带证据的结构化文献卡片。适合需要沉淀可靠研究事实和可复用洞见时使用。",
                "purpose_slug": "test-literature-read",
            }
            return {
                "model": "deepseek-v4-flash",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload, ensure_ascii=False)}}],
            }

        result = generate_skill_enrichment(
            "paper-card-extract",
            "# Complete Skill document",
            [purpose],
            request_func=request_func,
        )

        request_payload = json.loads(calls[0][1]["messages"][1]["content"])
        self.assertEqual(request_payload["document"], "# Complete Skill document")
        self.assertEqual(result["purpose_slug"], "test-literature-read")
        self.assertEqual(result["summary"].count("。"), 2)

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_one_sentence_summary_is_rejected(self):
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"summary": "只有一句中文摘要。", "purpose_slug": ""}, ensure_ascii=False)},
            }],
        }

        with self.assertRaises(SkillEnrichmentError) as context:
            generate_skill_enrichment("demo", "document", [], request_func=lambda *args: response)

        self.assertEqual(context.exception.code, "invalid_summary")


class SkillArchiveMigrationTests(TestCase):
    @patch("apps.skills.management.commands.migrate_skill_archives_to_nas.open_skill_stream")
    @patch("apps.skills.management.commands.migrate_skill_archives_to_nas.get_nas_skill_storage")
    def test_migration_updates_record_only_after_valid_zip_upload(self, get_storage, open_stream):
        source = GitHubSkillSource.objects.create(
            name="Test source", slug="test-source", repository_url="https://github.com/example/test.git"
        )
        skill = SharedSkill.objects.create(
            source=source, slug="demo", name="Demo", description="", source_path="demo"
        )
        payload = BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("demo/SKILL.md", "---\nname: demo\n---\n")
        content = payload.getvalue()
        release = SharedSkillRelease.objects.create(
            skill=skill,
            git_commit="c" * 40,
            repository_id="legacy-repository",
            archive_name="demo.zip",
            archive_remote_path="/legacy/demo.zip",
            archive_size=len(content),
        )
        upstream = MagicMock()
        upstream.iter_chunks.return_value = iter((content,))
        open_stream.return_value = upstream
        get_storage.return_value.upload.return_value = "/public/PLAB_KnowledgeBase/Skills/new.zip"

        call_command("migrate_skill_archives_to_nas")
        release.refresh_from_db()

        self.assertEqual(release.storage_backend, "nas_webdav")
        self.assertEqual(release.repository_id, "")
        self.assertEqual(release.archive_remote_path, "/public/PLAB_KnowledgeBase/Skills/new.zip")


class SkillSyncJobViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="Strong-pass-1234", is_staff=True)
        self.client.force_login(self.user)

    def test_staff_index_shows_independent_enrichment_action(self):
        response = self.client.get("/skills/")

        self.assertContains(response, "重新生成正式 Skill 摘要")
        self.assertContains(response, 'submitter.getAttribute("formaction") || form.action')

    def test_staff_can_edit_generated_description(self):
        source = GitHubSkillSource.objects.create(
            name="PLAB Shared Skills",
            slug="plab-shared-skills",
            repository_url="https://github.com/example/shared.git",
        )
        skill = SharedSkill.objects.create(
            source=source,
            slug="zotero-research-radar",
            name="zotero-research-radar",
            description="DeepSeek 生成的展示描述。",
            ai_generated_description="DeepSeek 生成的展示描述。",
            source_path="skills/zotero-research-radar",
        )

        index_response = self.client.get("/skills/")
        self.assertContains(index_response, "编辑描述")

        edit_response = self.client.get(
            "/skills/plab-shared-skills/zotero-research-radar/description/"
        )

        self.assertContains(edit_response, "DeepSeek 原始摘要")
        self.assertContains(edit_response, "DeepSeek 生成的展示描述。")

        response = self.client.post(
            "/skills/plab-shared-skills/zotero-research-radar/description/",
            {"description": "管理员修改后的第一句话。管理员修改后的第二句话。"},
        )

        self.assertRedirects(response, "/skills/plab-shared-skills/zotero-research-radar/")
        skill.refresh_from_db()
        self.assertEqual(skill.description, "管理员修改后的第一句话。管理员修改后的第二句话。")
        self.assertTrue(skill.description_is_manual)
        self.assertEqual(skill.ai_generated_description, "DeepSeek 生成的展示描述。")

    @patch("apps.skills.views.launch_scan_job")
    def test_sync_starts_background_job_and_returns_immediately(self, launch_scan_job):
        response = self.client.post("/skills/sync/", HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 202)
        job = SkillSyncJob.objects.get()
        self.assertEqual(response.json(), {
            "job_id": job.pk,
            "status": SkillSyncJob.QUEUED,
            "operation": SkillSyncJob.SCAN,
        })
        launch_scan_job.assert_called_once_with(job.pk, source_id=None)

    @patch("apps.skills.views.launch_enrichment_job")
    def test_enrichment_starts_independent_background_job(self, launch_job):
        source = GitHubSkillSource.objects.create(
            name="Selected source",
            slug="selected-enrichment-source",
            repository_url="https://github.com/example/selected.git",
        )

        response = self.client.post(
            "/skills/enrich/",
            {"source_id": source.pk},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 202)
        job = SkillSyncJob.objects.get()
        self.assertEqual(job.operation, SkillSyncJob.ENRICHMENT)
        launch_job.assert_called_once_with(job.pk, source_id=source.pk)

    @patch("apps.skills.views.launch_scan_job")
    def test_sync_passes_selected_source_to_background_job(self, launch_scan_job):
        source = GitHubSkillSource.objects.create(
            name="Selected source",
            slug="selected-source",
            repository_url="https://github.com/example/selected.git",
        )

        response = self.client.post(
            "/skills/sync/",
            {"source_id": source.pk},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 202)
        job = SkillSyncJob.objects.get()
        launch_scan_job.assert_called_once_with(job.pk, source_id=source.pk)

    @patch("apps.skills.views.launch_scan_job")
    def test_sync_rejects_disabled_source(self, launch_scan_job):
        source = GitHubSkillSource.objects.create(
            name="Disabled source",
            slug="disabled-source",
            repository_url="https://github.com/example/disabled.git",
            is_enabled=False,
        )

        response = self.client.post(
            "/skills/sync/",
            {"source_id": source.pk},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SkillSyncJob.objects.exists())
        launch_scan_job.assert_not_called()

    def test_sync_status_returns_current_progress(self):
        job = SkillSyncJob.objects.create(
            requested_by=self.user,
            status=SkillSyncJob.RUNNING,
            current_source="Scientific Agent Skills",
            current_skill="literature-review",
            sources_total=2,
            sources_completed=1,
            skills_total=10,
            skills_processed=4,
            uploaded_count=3,
            skipped_count=1,
        )

        response = self.client.get(f"/skills/sync/{job.pk}/status/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["percent"], 40)
        self.assertEqual(response.json()["current_skill"], "literature-review")
        self.assertEqual(response.json()["operation"], SkillSyncJob.SYNC)


class SkillSyncTaskTests(TestCase):
    @patch("apps.skills.tasks.subprocess.Popen")
    def test_launch_sync_job_passes_selected_source_to_command(self, popen):
        launch_sync_job(7, source_id=23)

        command = popen.call_args.args[0]
        self.assertEqual(command[-3:], ["7", "--source-id", "23"])

    @patch("apps.skills.tasks.subprocess.Popen")
    def test_launch_enrichment_job_uses_independent_command(self, popen):
        launch_enrichment_job(8, source_id=24)

        command = popen.call_args.args[0]
        self.assertIn("enrich_skills_job", command)
        self.assertEqual(command[-3:], ["8", "--source-id", "24"])
