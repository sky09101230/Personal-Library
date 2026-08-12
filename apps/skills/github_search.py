import hashlib
import json
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.cache import cache


GITHUB_API_URL = "https://api.github.com"
SEARCH_PAGE_SIZE = 20
SEARCH_CACHE_SECONDS = 180


class GitHubSearchError(Exception):
    pass


def _request_json(path, parameters=None):
    token = os.environ.get("GITHUB_API_TOKEN", "").strip()
    if not token:
        raise GitHubSearchError("服务器尚未配置 GITHUB_API_TOKEN，暂时不能搜索 GitHub。")
    url = f"{GITHUB_API_URL}{path}"
    if parameters:
        url = f"{url}?{urlencode(parameters)}"
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "AgentSys-GitHub-Skill-Discovery",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            message = "GitHub 令牌无效，请管理员检查服务器配置。"
        elif exc.code in (403, 429):
            retry_after = exc.headers.get("Retry-After")
            reset_at = exc.headers.get("X-RateLimit-Reset")
            if retry_after:
                suffix = f"，约 {retry_after} 秒后再试"
            elif reset_at and reset_at.isdecimal():
                suffix = f"，预计 {datetime.fromtimestamp(int(reset_at)).strftime('%H:%M')} 后恢复"
            else:
                suffix = "，请稍后再试"
            message = f"GitHub 搜索请求已达到限额{suffix}。"
        else:
            message = "GitHub 暂时无法完成搜索，请稍后再试。"
        raise GitHubSearchError(message) from exc
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GitHubSearchError("暂时无法连接 GitHub，请稍后再试。") from exc


def search_github_skills(keyword, page=1):
    keyword = " ".join(str(keyword).split())
    if not 2 <= len(keyword) <= 80:
        raise ValueError("关键词长度必须为 2 至 80 个字符。")
    page = min(50, max(1, int(page)))
    digest = hashlib.sha256(f"{keyword.casefold()}:{page}".encode()).hexdigest()
    cache_key = f"github-skill-search:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    payload = _request_json("/search/code", {
        "q": f"{keyword} in:file filename:SKILL.md",
        "per_page": SEARCH_PAGE_SIZE,
        "page": page,
    })
    items = []
    for item in payload.get("items", []):
        repository = item.get("repository") or {}
        full_name = repository.get("full_name", "")
        path = item.get("path", "")
        if repository.get("private") or "/" not in full_name or not path:
            continue
        owner, repository_name = full_name.split("/", 1)
        items.append({
            "owner": owner,
            "repository": repository_name,
            "full_name": full_name,
            "path": path,
            "html_url": item.get("html_url", ""),
            "repository_url": repository.get("html_url", ""),
        })
    total_count = min(int(payload.get("total_count", 0)), 1000)
    result = {
        "items": items,
        "total_count": total_count,
        "incomplete_results": bool(payload.get("incomplete_results")),
        "page": page,
        "pages": (total_count + SEARCH_PAGE_SIZE - 1) // SEARCH_PAGE_SIZE,
    }
    cache.set(cache_key, result, SEARCH_CACHE_SECONDS)
    return result
