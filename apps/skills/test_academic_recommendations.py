from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .github_search import GitHubSearchError
from .models import (
    AcademicSkillRecommendation,
    GitHubSkillSource,
    SharedSkill,
    SharedSkillRelease,
    SkillCandidate,
    SkillSyncJob,
)
from .recommendations import AcademicRecommendationError, refresh_academic_recommendations, run_academic_recommendation_job
from .tasks import launch_academic_recommendations_job


class AcademicRecommendationServiceTests(TestCase):
    def setUp(self):
        AcademicSkillRecommendation.objects.create(
            full_name="old/repository",
            skill_path="SKILL.md",
            recommendation="旧推荐第一句。旧推荐第二句。",
            stars=1,
            blob_sha="f" * 40,
            ai_model="old-model",
            ai_prompt_version="old-v1",
            refreshed_at=timezone.now(),
        )

    def test_success_replaces_snapshot_and_creates_no_publication_objects(self):
        items = [
            self._item("research/high", "skills/research/SKILL.md", "a" * 40, 500, "2026-08-10T00:00:00Z"),
            self._item("tools/middle", "SKILL.md", "b" * 40, 200, "2026-08-09T00:00:00Z"),
            self._item("general/low", "agents/SKILL.md", "c" * 40, 10, "2026-08-08T00:00:00Z"),
        ]
        search = self._search(items)

        def summarize(ranked):
            for item in ranked:
                item.update({
                    "summary": f"它处理 {item['full_name']} 的研究资料。它适合用于学术工作流程。",
                    "academic_recommended": item["full_name"] != "general/low",
                    "summary_model": "deepseek-test",
                    "summary_prompt_version": "discovery-v1",
                })
            return ""

        rows = refresh_academic_recommendations(search_func=search, summarize_func=summarize)

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            list(AcademicSkillRecommendation.objects.values_list("full_name", flat=True)),
            ["research/high", "tools/middle"],
        )
        recommendation = AcademicSkillRecommendation.objects.get(full_name="research/high")
        self.assertEqual(recommendation.skill_path, "skills/research/SKILL.md")
        self.assertEqual(recommendation.blob_sha, "a" * 40)
        self.assertEqual(recommendation.ai_model, "deepseek-test")
        self.assertEqual(search.call_count, 3)
        self.assertEqual(GitHubSkillSource.objects.count(), 0)
        self.assertEqual(SkillCandidate.objects.count(), 0)
        self.assertEqual(SharedSkill.objects.count(), 0)
        self.assertEqual(SharedSkillRelease.objects.count(), 0)

    def test_github_failure_preserves_previous_snapshot(self):
        def failed_search(*_args, **_kwargs):
            raise GitHubSearchError("GitHub 暂时不可用")

        with self.assertRaises(GitHubSearchError):
            refresh_academic_recommendations(search_func=failed_search)

        self.assertTrue(AcademicSkillRecommendation.objects.filter(full_name="old/repository").exists())

    def test_incomplete_ai_assessment_preserves_previous_snapshot(self):
        search = self._search([self._item("research/repo", "SKILL.md", "a" * 40, 5, "")])

        with self.assertRaises(AcademicRecommendationError):
            refresh_academic_recommendations(search_func=search, summarize_func=lambda _items: "AI 暂不可用")

        self.assertTrue(AcademicSkillRecommendation.objects.filter(full_name="old/repository").exists())

    @patch("apps.skills.recommendations.search_github_skills")
    def test_background_failure_marks_job_failed_and_keeps_snapshot(self, search):
        search.side_effect = GitHubSearchError("GitHub 请求达到限额")
        job = SkillSyncJob.objects.create(operation=SkillSyncJob.RECOMMENDATION, heartbeat_at=timezone.now())

        run_academic_recommendation_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, SkillSyncJob.FAILED)
        self.assertIn("达到限额", job.error)
        self.assertTrue(AcademicSkillRecommendation.objects.filter(full_name="old/repository").exists())

    @staticmethod
    def _search(items):
        from unittest.mock import MagicMock

        search = MagicMock()
        search.return_value = {"items": [dict(item) for item in items]}
        return search

    @staticmethod
    def _item(full_name, path, blob_sha, stars, pushed_at):
        owner, repository = full_name.split("/", 1)
        return {
            "owner": owner,
            "repository": repository,
            "full_name": full_name,
            "repository_url": f"https://github.com/{full_name}",
            "html_url": f"https://github.com/{full_name}/blob/main/{path}",
            "path": path,
            "blob_sha": blob_sha,
            "stars": stars,
            "pushed_at": pushed_at,
            "archived": False,
        }


class AcademicRecommendationPageTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="password")
        self.staff = User.objects.create_user(username="staff", password="password", is_staff=True)
        AcademicSkillRecommendation.objects.create(
            full_name="example/research",
            skill_path="skills/paper/SKILL.md",
            recommendation="它整理论文与引用资料。它适合用于学术文献工作。",
            stars=321,
            repository_pushed_at=timezone.now(),
            blob_sha="a" * 40,
            ai_model="deepseek-test",
            ai_prompt_version="discovery-v1",
            refreshed_at=timezone.now(),
        )

    @patch("apps.skills.views.launch_academic_recommendations_job")
    def test_non_staff_cannot_view_or_refresh(self, launch):
        self.client.force_login(self.member)

        get_response = self.client.get("/skills/discover/academic/")
        post_response = self.client.post("/skills/discover/academic/refresh/")

        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(post_response.status_code, 302)
        self.assertFalse(SkillSyncJob.objects.exists())
        launch.assert_not_called()

    def test_staff_page_shows_reason_stars_dates_and_import_action(self):
        self.client.force_login(self.staff)

        response = self.client.get("/skills/discover/academic/")

        self.assertContains(response, "AI 推荐的学术 Skills 仓库")
        self.assertContains(response, 'class="content content-wide"')
        self.assertContains(response, "example/research")
        self.assertContains(response, "它整理论文与引用资料")
        self.assertContains(response, "321")
        self.assertContains(response, "最近代码更新")
        self.assertContains(response, "AI 评估时间")
        self.assertContains(response, "检查许可证并加入候选池")
        self.assertContains(response, "不代表 GitHub 全量排行")

    @patch("apps.skills.views.launch_academic_recommendations_job")
    def test_staff_refresh_starts_background_job(self, launch):
        self.client.force_login(self.staff)

        response = self.client.post("/skills/discover/academic/refresh/")

        self.assertRedirects(response, "/skills/discover/academic/")
        job = SkillSyncJob.objects.get()
        self.assertEqual(job.operation, SkillSyncJob.RECOMMENDATION)
        launch.assert_called_once_with(job.pk)


class AcademicRecommendationTaskTests(TestCase):
    @patch("apps.skills.tasks.subprocess.Popen")
    def test_launcher_uses_independent_management_command(self, popen):
        launch_academic_recommendations_job(12)

        command = popen.call_args.args[0]
        self.assertIn("refresh_academic_skill_recommendations_job", command)
        self.assertEqual(command[-1], "12")
