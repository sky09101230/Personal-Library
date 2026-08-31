import base64
import binascii
import os
from pathlib import Path
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.urls import reverse
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from apps.box_upload.models import CanonicalDocument, UploadedDocument
from apps.box_upload.downloads import build_literature_download_url
from apps.box_upload.upload_review import (
    create_review_batch,
    serialize_review_item,
    stage_pdf_for_review,
)
from apps.box_upload.services import LiteratureStorageError
from apps.skills.downloads import build_skill_download_url
from apps.skills.models import SharedSkill, SharedSkillRelease

from .auth import DatabaseTokenVerifier


def _require_scope(scope):
    access_token = get_access_token()
    if access_token is None or scope not in access_token.scopes:
        raise PermissionError(f"当前访问令牌没有 {scope} 权限。")
    return access_token


def _document_text(document):
    return "\n".join((
        f"文献 ID: {document['id']}",
        f"文件名: {document['filename'] or '无 PDF 附件'}",
        f"标题: {document['title'] or '未提供'}",
        f"作者: {', '.join(document['authors']) or '未提供'}",
        f"期刊: {document['journal'] or '未提供'}",
        f"DOI: {document['doi'] or '未提供'}",
        f"发表年份: {document['publication_year'] or '未提供'}",
        f"元数据状态: {document['metadata_status']}",
        f"文件大小: {str(document['size']) + ' 字节' if document['size'] is not None else '无附件'}",
    ))


def _review_upload_text(review):
    item = review["item"]
    metadata = item["metadata"]
    authors = []
    for author in metadata.get("authors") or []:
        name = author.get("name", "") if isinstance(author, dict) else str(author)
        if name:
            authors.append(name)
    warnings = []
    for warning in item["warnings"]:
        message = warning["message"]
        if warning["code"] == "doi_title_mismatch":
            message += f"（PDF：{warning['pdf_title']}；DOI/BibTeX：{warning['doi_title']}）"
        warnings.append(f"- {message}")
    return "\n".join((
        "状态: pending_review",
        f"Batch ID: {review['batch_id']}",
        f"文件名: {item['filename']}",
        f"标题: {metadata.get('title') or '未提供'}",
        f"作者: {', '.join(authors) or '未提供'}",
        f"期刊: {metadata.get('journal') or '未提供'}",
        f"DOI: {metadata.get('doi') or '未提供'}",
        f"发表年份: {metadata.get('publication_year') or '未提供'}",
        "Warnings:\n" + ("\n".join(warnings) if warnings else "无"),
        f"网页审核地址: {review['review_url']}",
    ))


def _skill_text(skill):
    return "\n".join((
        f"Skill ID: {skill['id']}",
        f"名称: {skill['name']}",
        f"用途分类: {skill['category']} / {skill['purpose']}",
        f"来源: {skill['source']}",
        f"说明: {skill['description'].replace(chr(10), ' ')}",
        f"发布包: {skill['archive_name'] or '尚无'}",
    ))


def _page(number, size):
    if number < 1:
        raise ValueError("page 必须大于或等于 1。")
    if not 1 <= size <= 50:
        raise ValueError("page_size 必须在 1 到 50 之间。")
    return number, size


def _document_data(canonical):
    document = next(
        (upload for upload in canonical.uploads.all() if upload.status == UploadedDocument.Status.UPLOADED),
        None,
    )
    return {
        "id": canonical.id,
        "filename": document.original_name if document else "",
        "title": canonical.title,
        "authors": [author.get("name", "") for author in canonical.authors if isinstance(author, dict)],
        "journal": canonical.journal,
        "doi": canonical.doi,
        "publication_year": canonical.publication_year,
        "metadata_status": canonical.metadata_status,
        "sha256": canonical.sha256 or "",
        "size": document.size if document else None,
        "content_type": document.content_type if document else "",
        "uploaded_at": document.uploaded_at.isoformat() if document else None,
    }


def _skill_data(skill):
    release = skill.releases.filter(storage_backend="nas_webdav").first()
    release = release or skill.releases.first()
    return {
        "id": skill.id,
        "name": skill.name,
        "slug": skill.slug,
        "description": skill.description,
        "purpose": skill.purpose.name if skill.purpose else "未分类",
        "category": skill.purpose.parent.name if skill.purpose and skill.purpose.parent else "未分类",
        "source": skill.source.name if skill.source else "未知来源",
        "release_id": release.id if release else None,
        "archive_name": release.archive_name if release else None,
        "updated_at": skill.updated_at.isoformat(),
    }


@sync_to_async(thread_sensitive=True)
def _list_literature(query, page, page_size):
    records = CanonicalDocument.objects.filter(
        index_status=CanonicalDocument.IndexStatus.PUBLISHED
    ).prefetch_related("uploads")
    if query:
        records = records.filter(
            Q(uploads__original_name__icontains=query)
            | Q(sha256__icontains=query)
            | Q(title__icontains=query)
            | Q(doi__icontains=query)
            | Q(journal__icontains=query)
        ).distinct()
    total = records.count()
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size, "items": [_document_data(item) for item in records[start:start + page_size]]}


@sync_to_async(thread_sensitive=True)
def _get_document(document_id):
    canonical = CanonicalDocument.objects.filter(
        id=document_id,
        index_status=CanonicalDocument.IndexStatus.PUBLISHED,
    ).prefetch_related("uploads").first()
    return _document_data(canonical) if canonical else None


@sync_to_async(thread_sensitive=True)
def _get_download_document(document_id):
    return UploadedDocument.objects.filter(
        canonical_document_id=document_id,
        canonical_document__index_status=CanonicalDocument.IndexStatus.PUBLISHED,
        status=UploadedDocument.Status.UPLOADED,
        file_role=UploadedDocument.FileRole.PRIMARY,
    ).first()


@sync_to_async(thread_sensitive=True)
def _list_skills(query, purpose, page, page_size):
    skills = SharedSkill.objects.select_related("source", "purpose", "purpose__parent").prefetch_related("releases")
    if query:
        skills = skills.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(slug__icontains=query))
    if purpose:
        skills = skills.filter(Q(purpose__slug=purpose) | Q(purpose__parent__slug=purpose))
    total = skills.count()
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size, "items": [_skill_data(item) for item in skills[start:start + page_size]]}


@sync_to_async(thread_sensitive=True)
def _get_skill_data(skill_id):
    skill = SharedSkill.objects.filter(id=skill_id).select_related(
        "source", "purpose", "purpose__parent"
    ).prefetch_related("releases").first()
    return _skill_data(skill) if skill else None


@sync_to_async(thread_sensitive=True)
def _get_skill_release(skill_id):
    release_query = SharedSkillRelease.objects.filter(skill_id=skill_id)
    return release_query.filter(storage_backend="nas_webdav").first() or release_query.first()


@sync_to_async(thread_sensitive=True)
def _stage_upload(filename, content, content_type, uploader_id):
    uploaded_file = SimpleUploadedFile(filename, content, content_type=content_type)
    uploader = User.objects.get(pk=uploader_id)
    batch = create_review_batch(uploader)
    try:
        item = stage_pdf_for_review(batch, uploaded_file)
    except Exception:
        batch.delete()
        raise
    return {
        "batch_id": batch.pk,
        "item": serialize_review_item(item),
        "review_url": f"{settings.MCP_PUBLIC_BASE_URL}{reverse('box-upload')}?batch={batch.pk}",
    }


public_base_url = settings.MCP_PUBLIC_BASE_URL
public_host = urlsplit(public_base_url).netloc
mcp = FastMCP(
    "PLAB 科研资料库",
    instructions="用于浏览、下载和上传科研文献，以及浏览和下载科研 Skills。下载工具返回临时下载链接。",
    token_verifier=DatabaseTokenVerifier(),
    auth=AuthSettings(
        issuer_url=public_base_url,
        resource_server_url=None,
    ),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=[public_host]),
)


@mcp.tool()
async def list_literature(query: str = "", page: int = 1, page_size: int = 20):
    """按文件名、标题、DOI 或 SHA-256 浏览已上传文献，返回稳定的文献 ID。"""
    _require_scope("literature:read")
    page, page_size = _page(page, page_size)
    result = await _list_literature(query.strip(), page, page_size)
    records = "\n\n".join(_document_text(item) for item in result["items"]) or "没有匹配的文献。"
    return f"文献检索结果：共 {result['total']} 条，第 {result['page']} 页，每页 {result['page_size']} 条。\n\n{records}"


@mcp.tool()
async def get_literature(document_id: int):
    """查看一篇文献的元数据；先用 list_literature 取得 document_id。"""
    _require_scope("literature:read")
    document = await _get_document(document_id)
    if document is None:
        raise ValueError("找不到该文献。")
    return _document_text(document)


@mcp.tool()
async def get_literature_download_link(document_id: int):
    """获取一篇已发布文献的短期 PLAB 下载链接。"""
    _require_scope("literature:read")
    document = await _get_download_document(document_id)
    if document is None:
        raise ValueError("找不到已发布且带 PDF 附件的文献。")
    url = await sync_to_async(build_literature_download_url, thread_sensitive=True)(document)
    return f"文献 ID: {document.id}\n文件名: {document.original_name}\n下载链接: {url}"


@mcp.tool()
async def upload_literature(filename: str, content_base64: str, content_type: str = "application/pdf"):
    """上传 PDF 到待审核批次。content_base64 必须是标准 Base64 内容，最大 20 MiB。"""
    access_token = _require_scope("literature:write")
    filename = Path(filename).name
    if not filename or not filename.lower().endswith(".pdf"):
        raise ValueError("仅允许上传 PDF 文件。")
    if content_type != "application/pdf":
        raise ValueError("content_type 必须为 application/pdf。")
    if len(content_base64) > ((settings.MCP_MAX_UPLOAD_BYTES + 2) // 3 * 4):
        raise ValueError("文件超过 MCP 上传大小限制。")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("content_base64 不是有效的标准 Base64 内容。") from exc
    if len(content) > settings.MCP_MAX_UPLOAD_BYTES:
        raise ValueError("上传内容必须是未超过大小限制的有效 PDF。")
    uploader_id = int(access_token.client_id.removeprefix("user:"))
    try:
        review = await _stage_upload(filename, content, content_type, uploader_id)
    except LiteratureStorageError as exc:
        raise RuntimeError(f"上传到文献存储失败：{exc}") from exc
    return _review_upload_text(review)


@mcp.tool()
async def list_skills(query: str = "", purpose: str = "", page: int = 1, page_size: int = 20):
    """按名称、描述或用途标签浏览 Skills，返回稳定的 Skill ID。"""
    _require_scope("skills:read")
    page, page_size = _page(page, page_size)
    result = await _list_skills(query.strip(), purpose.strip(), page, page_size)
    skills = "\n\n".join(_skill_text(item) for item in result["items"]) or "没有匹配的 Skill。"
    return f"Skill 检索结果：共 {result['total']} 条，第 {result['page']} 页，每页 {result['page_size']} 条。\n\n{skills}"


@mcp.tool()
async def get_skill(skill_id: int):
    """查看一个 Skill 的详情和可下载发布包。"""
    _require_scope("skills:read")
    skill_data = await _get_skill_data(skill_id)
    if skill_data is None:
        raise ValueError("找不到该 Skill。")
    return _skill_text(skill_data)


@mcp.tool()
async def get_skill_download_link(skill_id: int):
    """获取指定 Skill 当前发布包的短期 PLAB 下载链接。"""
    _require_scope("skills:read")
    release = await _get_skill_release(skill_id)
    if release is None:
        if await _get_skill_data(skill_id) is None:
            raise ValueError("找不到该 Skill。")
        raise ValueError("该 Skill 尚无可下载的发布包。")
    url = await sync_to_async(build_skill_download_url, thread_sensitive=True)(release)
    return f"Skill ID: {skill_id}\n发布包: {release.archive_name}\n下载链接: {url}"


application = mcp.streamable_http_app()
