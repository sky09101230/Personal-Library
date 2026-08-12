import json
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from .github_search import GitHubSearchError, search_github_skills


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
        urlopen.return_value = _Response({
            "total_count": 1,
            "incomplete_results": False,
            "items": [{
                "path": "skills/paper/SKILL.md",
                "html_url": "https://github.com/example/research/blob/main/skills/paper/SKILL.md",
                "repository": {
                    "full_name": "example/research",
                    "html_url": "https://github.com/example/research",
                    "private": False,
                },
            }],
        })

        first = search_github_skills("paper review")
        second = search_github_skills("paper   review")

        self.assertEqual(first, second)
        self.assertEqual(first["items"][0]["path"], "skills/paper/SKILL.md")
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query["q"], ["paper review in:file filename:SKILL.md"])
        self.assertEqual(query["per_page"], ["20"])
        self.assertEqual(request.get_header("Authorization"), "Bearer server-only-token")

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
                "full_name": "example/research",
                "repository_url": "https://github.com/example/research",
                "path": "skills/paper/SKILL.md",
                "html_url": "https://github.com/example/research/blob/main/skills/paper/SKILL.md",
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
        search.assert_called_once_with("literature", page=1)
