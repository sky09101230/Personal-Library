import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from .models import GitHubSkillSource


GITHUB_API_URL = "https://api.github.com"
SEARCH_PAGE_SIZE = 20
SEARCH_CACHE_SECONDS = 180
REPOSITORY_CACHE_SECONDS = 1800
REPOSITORY_METADATA_WORKERS = 4
REPOSITORY_PART_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


class GitHubSearchError(Exception):
    pass


def _request_json(path, parameters=None, not_found_message=""):
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
        "X-GitHub-Api-Version": "2026-03-10",
    })
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404 and not_found_message:
            message = not_found_message
        elif exc.code == 401:
            message = "GitHub 令牌无效，请管理员检查服务器配置。"
        elif exc.code in (403, 429):
            headers = exc.headers or {}
            retry_after = headers.get("Retry-After")
            reset_at = headers.get("X-RateLimit-Reset")
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
        blob_sha = str(item.get("sha") or "").lower()
        if (
            repository.get("private")
            or "/" not in full_name
            or PurePosixPath(path).name != "SKILL.md"
            or re.fullmatch(r"[0-9a-f]{40,64}", blob_sha) is None
        ):
            continue
        owner, repository_name = full_name.split("/", 1)
        items.append({
            "owner": owner,
            "repository": repository_name,
            "full_name": full_name,
            "path": path,
            "blob_sha": blob_sha,
            "html_url": item.get("html_url", ""),
            "repository_url": repository.get("html_url", ""),
        })
    metadata = _repository_metadata_for_items(items)
    for item in items:
        item.update(metadata.get(item["full_name"], {"stars": None, "pushed_at": ""}))
    items.sort(key=lambda item: (
        item["stars"] is not None,
        item["stars"] if item["stars"] is not None else -1,
        item["pushed_at"],
    ), reverse=True)
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


def _repository_metadata_for_items(items):
    full_names = list(dict.fromkeys(item["full_name"] for item in items))
    if not full_names:
        return {}
    results = {}
    with ThreadPoolExecutor(max_workers=min(REPOSITORY_METADATA_WORKERS, len(full_names))) as executor:
        futures = {executor.submit(_repository_metadata, full_name): full_name for full_name in full_names}
        for future in as_completed(futures):
            try:
                results[futures[future]] = future.result()
            except GitHubSearchError:
                continue
    return results


def _repository_metadata(full_name):
    digest = hashlib.sha256(full_name.casefold().encode()).hexdigest()
    cache_key = f"github-repository-metadata:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    owner, repository = full_name.split("/", 1)
    payload = _request_json(f"/repos/{quote(owner, safe='')}/{quote(repository, safe='')}")
    try:
        stars = max(0, int(payload.get("stargazers_count", 0)))
    except (TypeError, ValueError):
        stars = 0
    pushed_at = str(payload.get("pushed_at") or "")
    if pushed_at and parse_datetime(pushed_at) is None:
        pushed_at = ""
    result = {"stars": stars, "pushed_at": pushed_at, "archived": bool(payload.get("archived"))}
    cache.set(cache_key, result, REPOSITORY_CACHE_SECONDS)
    return result


def inspect_github_skill_for_import(owner, repository, skill_path):
    if not _valid_repository_part(owner) or not _valid_repository_part(repository):
        raise GitHubSearchError("仓库名称无效，请重新搜索后再试。")
    skill_path = _safe_github_path(skill_path, require_skill_file=True)
    encoded_owner = quote(owner, safe="")
    encoded_repository = quote(repository, safe="")
    repository_path = f"/repos/{encoded_owner}/{encoded_repository}"

    repository_data = _request_json(repository_path, not_found_message="该 GitHub 仓库已不存在或不可访问。")
    if repository_data.get("private") is not False:
        raise GitHubSearchError("私有仓库不能通过此入口导入。")
    canonical_name = str(repository_data.get("full_name") or "")
    canonical_parts = canonical_name.split("/")
    if len(canonical_parts) != 2 or not all(_valid_repository_part(part) for part in canonical_parts):
        raise GitHubSearchError("GitHub 没有返回有效仓库信息，请重新搜索后再试。")
    owner, repository = canonical_parts
    repository_path = f"/repos/{quote(owner, safe='')}/{quote(repository, safe='')}"
    default_branch = str(repository_data.get("default_branch") or "").strip()
    if not default_branch:
        raise GitHubSearchError("该仓库没有可读取的默认分支。")
    commit_data = _request_json(
        f"{repository_path}/commits/{quote(default_branch, safe='')}",
        not_found_message="无法读取仓库默认分支，请重新搜索后再试。",
    )
    commit = str(commit_data.get("sha") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        raise GitHubSearchError("GitHub 没有返回有效提交，请重新搜索后再试。")
    contents = _request_json(
        f"{repository_path}/contents/{quote(skill_path, safe='/')}",
        {"ref": commit},
        not_found_message="所选 SKILL.md 已不存在，请重新搜索后再试。",
    )
    if contents.get("type") != "file" or contents.get("path") != skill_path:
        raise GitHubSearchError("所选路径不是可读取的 SKILL.md，请重新搜索后再试。")
    license_data = _request_json(
        f"{repository_path}/license",
        {"ref": commit},
        not_found_message="该仓库没有 GitHub 可识别的许可证，只能查看，不能导入候选池。",
    )
    license_info = license_data.get("license") or {}
    license_spdx = str(license_info.get("spdx_id") or "").strip()
    if not license_spdx or license_spdx.upper() == "NOASSERTION":
        raise GitHubSearchError("该仓库的许可证不明确，只能查看，不能导入候选池。")
    license_path = _safe_github_path(license_data.get("path", ""))
    full_name = f"{owner}/{repository}"
    return {
        "owner": owner,
        "repository": repository,
        "full_name": full_name,
        "repository_url": f"https://github.com/{full_name}.git",
        "default_branch": default_branch,
        "commit": commit.lower(),
        "skill_path": skill_path,
        "source_path": PurePosixPath(skill_path).parent.as_posix(),
        "license_path": license_path,
        "license_spdx": license_spdx,
    }


def upsert_github_skill_source(selection):
    suffix = hashlib.sha256(selection["full_name"].casefold().encode()).hexdigest()[:8]
    base = slugify(selection["full_name"].replace("/", "-")) or "github-source"
    slug = f"{base[:91]}-{suffix}"
    repository_url = selection["repository_url"]
    source = (
        GitHubSkillSource.objects.filter(
            Q(repository_url__iexact=repository_url)
            | Q(repository_url__iexact=repository_url.removesuffix(".git"))
        )
        .filter(Q(branch="") | Q(branch=selection["default_branch"]))
        .first()
    )
    if source is None:
        source, _ = GitHubSkillSource.objects.get_or_create(slug=slug, defaults={
            "name": selection["full_name"],
            "repository_url": repository_url,
            "branch": selection["default_branch"],
        })
    changed = []
    for field, value in (
        ("name", selection["full_name"]),
        ("repository_url", selection["repository_url"]),
        ("branch", selection["default_branch"]),
        ("is_enabled", True),
    ):
        if getattr(source, field) != value:
            setattr(source, field, value)
            changed.append(field)
    if changed:
        source.save(update_fields=[*changed, "updated_at"])
    return source


def _safe_github_path(value, require_skill_file=False):
    value = str(value or "")
    if not value or len(value) > 500 or "\\" in value or "\0" in value:
        raise GitHubSearchError("GitHub 文件路径无效，请重新搜索后再试。")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise GitHubSearchError("GitHub 文件路径无效，请重新搜索后再试。")
    normalized = path.as_posix()
    if require_skill_file and path.name != "SKILL.md":
        raise GitHubSearchError("只能导入名为 SKILL.md 的文件。")
    return normalized


def _valid_repository_part(value):
    return bool(REPOSITORY_PART_PATTERN.fullmatch(value or "")) and value not in {".", ".."}
