import json
import shutil
import zipfile
from email.message import Message
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from .candidate_services import _scan_source
from .github_search import (
    GitHubSearchError,
    _repository_metadata,
    inspect_github_skill_for_import,
    search_github_skills,
    upsert_github_skill_source,
)
from .models import GitHubSkillSource, SharedSkill, SkillCandidate, SkillSyncJob
from .services import SkillSyncError
from .tasks import launch_scan_job


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class GitHubSearchTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.skills.github_search.urlopen")
    @patch.dict("os.environ", {"GITHUB_API_TOKEN": "server-only-token"})
    def test_search_is_fixed_to_public_skill_files_and_cached(self, urlopen):
        urlopen.side_effect = [_Response({
            "total_count": 1,
            "incomplete_results": False,
            "items": [{
                "sha": "a" * 40,
                "path": "skills/paper/SKILL.md",
                "html_url": "https://github.com/example/research/blob/main/skills/paper/SKILL.md",
                "repository": {
                    "full_name": "example/research",
                    "html_url": "https://github.com/example/research",
                    "private": False,
                },
            }],
        }), _Response({
            "stargazers_count": 123,
            "pushed_at": "2026-08-01T12:00:00Z",
            "archived": False,
        })]

        first = search_github_skills("paper review")
        second = search_github_skills("paper   review")

        self.assertEqual(first, second)
        self.assertEqual(first["items"][0]["path"], "skills/paper/SKILL.md")
        self.assertEqual(first["items"][0]["stars"], 123)
        self.assertEqual(urlopen.call_count, 2)
        request = urlopen.call_args_list[0].args[0]
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query["q"], ["paper review in:file filename:SKILL.md"])
        self.assertEqual(query["per_page"], ["20"])
        self.assertEqual(request.get_header("Authorization"), "Bearer server-only-token")

    @patch("apps.skills.github_search._repository_metadata")
    @patch("apps.skills.github_search._request_json")
    def test_search_sorts_current_page_by_stars(self, request_json, repository_metadata):
        request_json.return_value = {
            "total_count": 2,
            "items": [
                {"sha": "a" * 40, "path": "SKILL.md", "html_url": "https://github.com/low/repo/blob/main/SKILL.md", "repository": {"full_name": "low/repo", "html_url": "https://github.com/low/repo", "private": False}},
                {"sha": "b" * 40, "path": "tools/SKILL.md", "html_url": "https://github.com/high/repo/blob/main/tools/SKILL.md", "repository": {"full_name": "high/repo", "html_url": "https://github.com/high/repo", "private": False}},
            ],
        }
        repository_metadata.side_effect = lambda full_name: {
            "low/repo": {"stars": 2, "pushed_at": "2026-08-01T00:00:00Z"},
            "high/repo": {"stars": 200, "pushed_at": "2026-07-01T00:00:00Z"},
        }[full_name]

        result = search_github_skills("academic")

        self.assertEqual([item["full_name"] for item in result["items"]], ["high/repo", "low/repo"])

    @patch("apps.skills.github_search._repository_metadata")
    @patch("apps.skills.github_search._request_json")
    def test_repository_metadata_failure_keeps_search_results(self, request_json, repository_metadata):
        request_json.return_value = {
            "total_count": 2,
            "items": [
                {"sha": "a" * 40, "path": "SKILL.md", "repository": {"full_name": "ok/repo", "private": False}},
                {"sha": "b" * 40, "path": "SKILL.md", "repository": {"full_name": "down/repo", "private": False}},
            ],
        }

        def load_metadata(full_name):
            if full_name == "down/repo":
                raise GitHubSearchError("GitHub 暂时无法完成搜索，请稍后再试。")
            return {"stars": 8, "pushed_at": "2026-08-01T00:00:00Z"}

        repository_metadata.side_effect = load_metadata

        result = search_github_skills("research")

        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["full_name"], "ok/repo")
        self.assertIsNone(result["items"][1]["stars"])

    @patch("apps.skills.github_search._request_json")
    def test_repository_metadata_has_separate_cache(self, request_json):
        request_json.return_value = {"stargazers_count": 42, "pushed_at": "2026-08-01T00:00:00Z"}

        first = _repository_metadata("example/research")
        second = _repository_metadata("example/research")

        self.assertEqual(first, second)
        request_json.assert_called_once()

    @patch("apps.skills.github_search.urlopen")
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_token_fails_before_request(self, urlopen):
        with self.assertRaisesMessage(GitHubSearchError, "GITHUB_API_TOKEN"):
            search_github_skills("literature")
        urlopen.assert_not_called()

    @patch("apps.skills.github_search.urlopen")
    @patch.dict("os.environ", {"GITHUB_API_TOKEN": "token"})
    def test_rate_limit_error_is_safe_and_actionable(self, urlopen):
        headers = Message()
        headers["Retry-After"] = "30"
        urlopen.side_effect = HTTPError("https://api.github.com/search/code", 429, "limited", headers, BytesIO())

        with self.assertRaisesMessage(GitHubSearchError, "30 秒后再试"):
            search_github_skills("literature")

    @patch("apps.skills.github_search._request_json")
    def test_import_rechecks_public_repository_file_commit_and_license(self, request_json):
        request_json.side_effect = [
            {"private": False, "default_branch": "main", "full_name": "example/research"},
            {"sha": "a" * 40},
            {"type": "file", "path": "skills/paper/SKILL.md"},
            {"path": "LICENSE", "license": {"spdx_id": "MIT"}},
        ]

        result = inspect_github_skill_for_import("example", "research", "skills/paper/SKILL.md")

        self.assertEqual(result["commit"], "a" * 40)
        self.assertEqual(result["source_path"], "skills/paper")
        self.assertEqual(result["license_spdx"], "MIT")
        self.assertEqual(request_json.call_count, 4)
        self.assertEqual(request_json.call_args_list[2].args[1], {"ref": "a" * 40})

    @patch("apps.skills.github_search._request_json")
    def test_import_rejects_untrusted_path_before_github_request(self, request_json):
        with self.assertRaisesMessage(GitHubSearchError, "路径无效"):
            inspect_github_skill_for_import("example", "research", "../SKILL.md")
        with self.assertRaisesMessage(GitHubSearchError, "仓库名称无效"):
            inspect_github_skill_for_import("..", "research", "SKILL.md")
        request_json.assert_not_called()

    def test_import_reuses_existing_default_branch_source(self):
        existing = GitHubSkillSource.objects.create(
            name="Existing",
            slug="existing",
            repository_url="https://github.com/example/research",
        )
        selection = {
            "full_name": "example/research",
            "repository_url": "https://github.com/example/research.git",
            "default_branch": "main",
        }

        source = upsert_github_skill_source(selection)

        self.assertEqual(source.pk, existing.pk)
        self.assertEqual(GitHubSkillSource.objects.count(), 1)
        self.assertEqual(source.branch, "main")


class GitHubSearchPageTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="password")
        self.staff = User.objects.create_user(username="staff", password="password", is_staff=True)

    @patch("apps.skills.views.search_github_skills")
    def test_non_staff_is_refused_without_github_request(self, search):
        self.client.force_login(self.member)
        response = self.client.get("/skills/discover/github/?q=literature")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        search.assert_not_called()

    @patch("apps.skills.views.inspect_github_skill_for_import")
    def test_non_staff_cannot_submit_import(self, inspect):
        self.client.force_login(self.member)

        response = self.client.post("/skills/discover/github/import/", {
            "owner": "example", "repository": "research", "path": "skills/paper/SKILL.md",
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        inspect.assert_not_called()

    @patch("apps.skills.views.search_github_skills")
    def test_blank_or_short_keyword_never_searches(self, search):
        self.client.force_login(self.staff)

        self.assertEqual(self.client.get("/skills/discover/github/").status_code, 200)
        response = self.client.get("/skills/discover/github/?q=a")

        self.assertContains(response, "关键词至少需要 2 个字符")
        search.assert_not_called()

    @patch("apps.skills.views.search_github_skills")
    def test_staff_sees_search_results(self, search):
        search.return_value = {
            "items": [{
                "owner": "example",
                "repository": "research",
                "full_name": "example/research",
                "repository_url": "https://github.com/example/research",
                "path": "skills/paper/SKILL.md",
                "html_url": "https://github.com/example/research/blob/main/skills/paper/SKILL.md",
                "stars": 321,
                "pushed_at": "2026-08-01T12:00:00Z",
            }],
            "total_count": 1,
            "incomplete_results": False,
            "page": 1,
            "pages": 1,
        }
        self.client.force_login(self.staff)

        response = self.client.get("/skills/discover/github/?q=literature")

        self.assertContains(response, "example/research")
        self.assertContains(response, "skills/paper/SKILL.md")
        self.assertContains(response, "321")
        self.assertContains(response, "2026-08-01")
        self.assertContains(response, "本页内按 Star")
        self.assertContains(response, "检查许可证并加入候选池")
        search.assert_called_once_with("literature", page=1)

    @patch("apps.skills.views.launch_scan_job")
    @patch("apps.skills.views.inspect_github_skill_for_import")
    def test_valid_import_launches_one_selected_candidate_scan_only(self, inspect, launch):
        inspect.return_value = {
            "owner": "example",
            "repository": "research",
            "full_name": "example/research",
            "repository_url": "https://github.com/example/research.git",
            "default_branch": "main",
            "commit": "a" * 40,
            "skill_path": "skills/paper/SKILL.md",
            "source_path": "skills/paper",
            "license_path": "LICENSE",
            "license_spdx": "MIT",
        }
        self.client.force_login(self.staff)

        response = self.client.post("/skills/discover/github/import/", {
            "owner": "example",
            "repository": "research",
            "path": "skills/paper/SKILL.md",
            "q": "literature",
        })

        self.assertRedirects(response, "/skills/")
        source = GitHubSkillSource.objects.get()
        job = SkillSyncJob.objects.get()
        launch.assert_called_once_with(
            job.pk,
            source_id=source.pk,
            source_path="skills/paper",
            expected_commit="a" * 40,
            license_path="LICENSE",
            license_spdx="MIT",
        )
        self.assertEqual(SkillCandidate.objects.count(), 0)
        self.assertEqual(SharedSkill.objects.count(), 0)

    @patch("apps.skills.views.launch_scan_job")
    @patch("apps.skills.views.inspect_github_skill_for_import")
    def test_missing_license_creates_nothing(self, inspect, launch):
        inspect.side_effect = GitHubSearchError("该仓库没有 GitHub 可识别的许可证，只能查看，不能导入候选池。")
        self.client.force_login(self.staff)

        response = self.client.post("/skills/discover/github/import/", {
            "owner": "example", "repository": "research", "path": "skills/paper/SKILL.md", "q": "paper",
        }, follow=True)

        self.assertContains(response, "只能查看，不能导入候选池")
        self.assertEqual(GitHubSkillSource.objects.count(), 0)
        self.assertEqual(SkillSyncJob.objects.count(), 0)
        launch.assert_not_called()


class GitHubSelectedScanTests(TestCase):
    def test_selected_scan_archives_only_one_skill_with_repository_license(self):
        source = GitHubSkillSource.objects.create(
            name="example/research",
            slug="example-research",
            repository_url="https://github.com/example/research.git",
            branch="main",
        )
        commit = "b" * 40
        captured_names = []
        storage = MagicMock()

        def capture_upload(archive):
            archive.seek(0)
            with zipfile.ZipFile(archive) as zipped:
                captured_names.extend(zipped.namelist())
            return "/private/selected.zip"

        storage.upload.side_effect = capture_upload
        with TemporaryDirectory(prefix="github-selected-scan-test-") as temporary:
            fixture = Path(temporary) / "fixture"
            (fixture / "skills" / "paper").mkdir(parents=True)
            (fixture / "skills" / "other").mkdir(parents=True)
            (fixture / "skills" / "paper" / "SKILL.md").write_text(
                "---\nname: paper\ndescription: Paper helper\n---\n# Paper", encoding="utf-8"
            )
            (fixture / "skills" / "other" / "SKILL.md").write_text("# Other", encoding="utf-8")
            (fixture / "LICENSE").write_text("MIT license", encoding="utf-8")

            def run_git(*arguments):
                if arguments[0] == "clone":
                    shutil.copytree(fixture, arguments[-1])
                    return ""
                return commit

            with (
                patch("apps.skills.candidate_services._run_git", side_effect=run_git),
                patch("apps.skills.candidate_services.enrich_candidate", side_effect=lambda candidate, _document: candidate),
            ):
                _scan_source(
                    source,
                    storage,
                    source_path="skills/paper",
                    expected_commit=commit,
                    license_path="LICENSE",
                    license_spdx="MIT",
                )

        candidate = SkillCandidate.objects.get()
        self.assertEqual(candidate.source_path, "skills/paper")
        self.assertEqual(candidate.status, SkillCandidate.Status.PENDING)
        self.assertIn("paper/SKILL.md", captured_names)
        self.assertIn("paper/_repository_license/LICENSE", captured_names)
        self.assertNotIn("other/SKILL.md", captured_names)
        self.assertIn("MIT", " ".join(candidate.validation_warnings))
        self.assertEqual(SharedSkill.objects.count(), 0)

    @patch("apps.skills.candidate_services._run_git", side_effect=["", "b" * 40])
    def test_selected_scan_stops_when_commit_has_changed(self, _run_git):
        source = GitHubSkillSource.objects.create(
            name="example/research", slug="example-research", repository_url="https://github.com/example/research.git"
        )

        with self.assertRaisesMessage(SkillSyncError, "重新搜索"):
            _scan_source(source, MagicMock(), source_path="skills/paper", expected_commit="a" * 40)
        self.assertEqual(SkillCandidate.objects.count(), 0)


class GitHubImportTaskTests(TestCase):
    @patch("apps.skills.tasks.subprocess.Popen")
    def test_launcher_passes_selected_scan_arguments(self, popen):
        launch_scan_job(
            8,
            source_id=24,
            source_path="skills/paper",
            expected_commit="a" * 40,
            license_path="LICENSE",
            license_spdx="MIT",
        )

        command = popen.call_args.args[0]
        self.assertEqual(command[-6:], [
            "--source-id", "24",
            "--source-path=skills/paper",
            f"--expected-commit={'a' * 40}",
            "--license-path=LICENSE",
            "--license-spdx=MIT",
        ])

    @patch("apps.skills.management.commands.scan_skill_candidates_job.scan_github_candidates")
    def test_management_command_forwards_selected_scan_arguments(self, scan):
        job = SkillSyncJob.objects.create()

        call_command(
            "scan_skill_candidates_job",
            job.pk,
            source_id=24,
            source_path="skills/paper",
            expected_commit="a" * 40,
            license_path="LICENSE",
            license_spdx="MIT",
        )

        scan.assert_called_once_with(
            job=job,
            source_id=24,
            source_path="skills/paper",
            expected_commit="a" * 40,
            license_path="LICENSE",
            license_spdx="MIT",
        )
