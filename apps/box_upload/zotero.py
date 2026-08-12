import base64
import hashlib
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, url2pathname, urlopen

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.files import File
from django.db import transaction

from .ingestion import associate_existing_pdf, prepare_pdf, save_pdf_upload
from .metadata import normalize_doi
from .models import CanonicalDocument, ExternalReference
from .storage import store_literature


class ZoteroImportError(Exception):
    pass


def import_zotero_library(
    library_type,
    library_id,
    api_key,
    collection_key="",
    item_keys=None,
    browser_pdfs=None,
    uploader=None,
    request_page=None,
    request_file=None,
    store_file=None,
    local_api_available=None,
    request_local_text=None,
    open_local_file=None,
):
    result = None
    for event in iter_zotero_import_library(
        library_type,
        library_id,
        api_key,
        collection_key=collection_key,
        item_keys=item_keys,
        browser_pdfs=browser_pdfs,
        uploader=uploader,
        request_page=request_page,
        request_file=request_file,
        store_file=store_file,
        local_api_available=local_api_available,
        request_local_text=request_local_text,
        open_local_file=open_local_file,
    ):
        if event.get("done"):
            result = event["result"]
    return result


def iter_zotero_import_library(
    library_type,
    library_id,
    api_key,
    collection_key="",
    item_keys=None,
    browser_pdfs=None,
    uploader=None,
    request_page=None,
    request_file=None,
    store_file=None,
    local_api_available=None,
    request_local_text=None,
    open_local_file=None,
):
    yield {"progress": 5, "message": "正在连接 Zotero"}
    items = []
    for page_number, (payload, headers) in enumerate(_iter_zotero_pages(
        library_type,
        library_id,
        api_key,
        collection_key=collection_key,
        item_keys=item_keys,
        request_page=request_page,
    ), start=1):
        items.extend(payload)
        total = _total_results(headers)
        progress = 5 + round(25 * min(len(items) / total, 1)) if total else min(30, 10 + page_number * 5)
        suffix = f"，共 {total} 条" if total else f"，已获取 {len(items)} 条"
        yield {"progress": progress, "message": f"正在拉取 Zotero 第 {page_number} 页{suffix}"}

    result = {
        "created": 0,
        "reused": 0,
        "skipped": 0,
        "pdf_imported": 0,
        "pdf_reused": 0,
        "pdf_skipped": 0,
        "pdf_failed": 0,
        "pdf_local": 0,
        "pdf_browser": 0,
        "pdf_failures": [],
    }
    if local_api_available is None:
        local_api_available = request_page is None and _zotero_local_api_available()
    total = len(items)
    if total:
        yield {"progress": 35, "message": f"正在整理 {total} 条 Zotero 文献"}
    for index, item in enumerate(items, start=1):
        mapped = map_zotero_item(item)
        if mapped is None:
            result["skipped"] += 1
        else:
            canonical, created = _upsert_zotero_item(library_id, mapped)
            result["created" if created else "reused"] += 1
            if uploader is not None:
                attachment_progress = 35 + round(60 * (index - 1) / total)
                browser_pdf = (browser_pdfs or {}).get(mapped["item_key"])
                if browser_pdf is not None:
                    yield {
                        "progress": attachment_progress,
                        "message": f"正在上传浏览器 PDF：{browser_pdf.name}",
                    }
                    try:
                        outcome = _import_browser_pdf(canonical, uploader, browser_pdf, store_file=store_file)
                    except Exception as exc:
                        failure = _record_pdf_failure(result, browser_pdf.name, exc, api_key)
                        yield {
                            "progress": attachment_progress,
                            "message": f"浏览器 PDF 导入失败：{failure}",
                            "attachment_failure": failure,
                        }
                    else:
                        result[f"pdf_{outcome}"] += 1
                        result["pdf_browser"] += 1
                        yield {
                            "progress": attachment_progress,
                            "message": f"已从浏览器上传：{browser_pdf.name}",
                        }
                    yield {
                        "progress": 35 + round(60 * index / total),
                        "message": f"正在处理第 {index}/{total} 条文献",
                    }
                    continue
                try:
                    children = fetch_zotero_children(
                        library_type,
                        library_id,
                        api_key,
                        mapped["item_key"],
                        request_page=request_page,
                    )
                except Exception as exc:
                    failure = _record_pdf_failure(
                        result, mapped["title"] or mapped["item_key"], exc, api_key
                    )
                    yield {
                        "progress": attachment_progress,
                        "message": f"附件列表读取失败：{failure}",
                        "attachment_failure": failure,
                    }
                else:
                    for child in children:
                        attachment = map_zotero_pdf_attachment(child)
                        if attachment is None:
                            if isinstance(child, dict) and (child.get("data") or {}).get("itemType") == "attachment":
                                result["pdf_skipped"] += 1
                            continue
                        yield {
                            "progress": attachment_progress,
                            "message": f"正在下载 PDF：{attachment['filename']}",
                        }
                        try:
                            outcome = _import_zotero_pdf(
                                canonical,
                                uploader,
                                library_type,
                                library_id,
                                api_key,
                                attachment,
                                request_file=request_file,
                                store_file=store_file,
                                local_api_available=local_api_available,
                                request_local_text=request_local_text,
                                open_local_file=open_local_file,
                            )
                        except Exception as exc:
                            failure = _record_pdf_failure(result, attachment["filename"], exc, api_key)
                            yield {
                                "progress": attachment_progress,
                                "message": f"PDF 导入失败：{failure}",
                                "attachment_failure": failure,
                            }
                        else:
                            result[f"pdf_{outcome}"] += 1
                            source = attachment.get("_pdf_source", "web")
                            if source == "local":
                                result["pdf_local"] += 1
                            yield {
                                "progress": attachment_progress,
                                "message": (
                                    f"已从 Zotero Desktop 读取：{attachment['filename']}"
                                    if source == "local"
                                    else f"已从 Zotero Web 读取：{attachment['filename']}"
                                ),
                            }
        yield {
            "progress": 35 + round(60 * index / total),
            "message": f"正在处理第 {index}/{total} 条文献",
        }
    yield {
        "progress": 100,
        "message": (
            f"导入完成：文献新增 {result['created']}，复用 {result['reused']}，跳过 {result['skipped']}；"
            f"PDF 导入 {result['pdf_imported']}，复用 {result['pdf_reused']}，"
            f"跳过 {result['pdf_skipped']}，失败 {result['pdf_failed']}，其中浏览器上传 {result['pdf_browser']}"
        ),
        "result": result,
        "done": True,
    }


def fetch_zotero_items(
    library_type, library_id, api_key, collection_key="", item_keys=None, request_page=None
):
    items = []
    for payload, _headers in _iter_zotero_pages(
        library_type,
        library_id,
        api_key,
        collection_key=collection_key,
        item_keys=item_keys,
        request_page=request_page,
    ):
        items.extend(payload)
    return items


def fetch_zotero_collections(library_type, library_id, api_key, request_page=None):
    base_url, library_path, base_parts = _zotero_library_context(library_type, library_id, api_key)
    next_url = f"{base_url}{library_path}/collections?format=json&limit=100"
    collections = []
    for payload, _headers in _iter_json_pages(next_url, api_key, request_page, base_parts):
        for item in payload:
            data = item.get("data") or {}
            if item.get("key") and data.get("name"):
                collections.append({"key": str(item["key"]), "name": str(data["name"])})
    return sorted(collections, key=lambda item: item["name"].casefold())


def summarize_zotero_items(items):
    summaries = []
    for item in items:
        mapped = map_zotero_item(item)
        if mapped:
            summaries.append({
                "key": mapped["item_key"],
                "title": mapped["title"] or "（无标题）",
                "year": mapped["publication_year"],
                "authors": [author["name"] for author in mapped["authors"]],
            })
    return summaries


def fetch_zotero_children(library_type, library_id, api_key, parent_key, request_page=None):
    base_url, library_path, base_parts = _zotero_library_context(library_type, library_id, api_key)
    next_url = (
        f"{base_url}{library_path}/items/{quote(str(parent_key), safe='')}/children?format=json&limit=100"
    )
    items = []
    for payload, _headers in _iter_json_pages(next_url, api_key, request_page, base_parts):
        items.extend(payload)
    return items


def _iter_zotero_pages(
    library_type, library_id, api_key, collection_key="", item_keys=None, request_page=None
):
    base_url, library_path, base_parts = _zotero_library_context(library_type, library_id, api_key)
    if item_keys is not None:
        keys = list(dict.fromkeys(str(key).strip().upper() for key in item_keys))
        if not keys or len(keys) > 500 or any(not re.fullmatch(r"[A-Z0-9]{8}", key) for key in keys):
            raise ZoteroImportError("请选择有效的 Zotero 条目。")
        for start in range(0, len(keys), 50):
            query = urlencode({"format": "json", "limit": 100, "itemKey": ",".join(keys[start:start + 50])})
            yield from _iter_json_pages(
                f"{base_url}{library_path}/items?{query}", api_key, request_page, base_parts
            )
        return
    if collection_key.strip():
        item_path = f"/collections/{quote(collection_key.strip(), safe='')}/items/top"
    else:
        item_path = "/items/top"
    next_url = f"{base_url}{library_path}{item_path}?format=json&limit=100"
    yield from _iter_json_pages(next_url, api_key, request_page, base_parts)


def _zotero_library_context(library_type, library_id, api_key):
    if library_type not in {"users", "groups"}:
        raise ZoteroImportError("Zotero library type must be users or groups.")
    if not str(library_id).strip() or not api_key.strip():
        raise ZoteroImportError("Zotero library ID and API key are required.")

    base_url = settings.ZOTERO_API_URL.rstrip("/")
    base_parts = urlsplit(base_url)
    if base_parts.scheme != "https" or not base_parts.netloc:
        raise ZoteroImportError("Zotero API URL must be a valid HTTPS URL.")
    library_path = f"/{library_type}/{quote(str(library_id).strip(), safe='')}"
    return base_url, library_path, base_parts


def encrypt_zotero_api_key(api_key):
    key = base64.urlsafe_b64encode(hashlib.sha256(f"zotero:{settings.SECRET_KEY}".encode()).digest())
    return Fernet(key).encrypt(api_key.encode()).decode()


def decrypt_zotero_api_key(ciphertext):
    key = base64.urlsafe_b64encode(hashlib.sha256(f"zotero:{settings.SECRET_KEY}".encode()).digest())
    try:
        return Fernet(key).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ZoteroImportError("保存的 Zotero API Key 无法读取，请重新连接。") from exc


def _iter_json_pages(next_url, api_key, request_page, base_parts):
    request_page = request_page or _request_page
    while next_url:
        payload, headers = request_page(next_url, api_key)
        if not isinstance(payload, list):
            raise ZoteroImportError("Zotero returned an invalid item list.")
        yield payload, headers
        link_header = next((value for key, value in headers.items() if key.lower() == "link"), "")
        next_url = _next_link(link_header)
        if next_url:
            next_parts = urlsplit(next_url)
            if next_parts.scheme != "https" or next_parts.netloc != base_parts.netloc:
                raise ZoteroImportError("Zotero returned an invalid pagination link.")


def _total_results(headers):
    for key, value in headers.items():
        if key.lower() == "total-results" and str(value).isdigit():
            return int(value)
    return 0


def map_zotero_item(item):
    if not isinstance(item, dict) or not item.get("key"):
        return None
    data = item.get("data") or {}
    if data.get("itemType") in {"attachment", "note", "annotation"}:
        return None

    authors = []
    for creator in data.get("creators") or []:
        if creator.get("creatorType") not in {"author", "bookAuthor"}:
            continue
        name = " ".join(part for part in (creator.get("firstName"), creator.get("lastName")) if part).strip()
        name = name or str(creator.get("name") or "").strip()
        if name:
            authors.append({"name": name})

    doi = normalize_doi(data.get("DOI"))
    date_match = re.search(r"\b(19|20)\d{2}\b", str(data.get("date") or ""))
    tags = [tag.get("tag") for tag in data.get("tags") or [] if isinstance(tag, dict) and tag.get("tag")]
    return {
        "item_key": str(item["key"]),
        "version": item.get("version"),
        "title": str(data.get("title") or "").strip(),
        "authors": authors,
        "abstract": str(data.get("abstractNote") or "").strip(),
        "journal": str(data.get("publicationTitle") or data.get("proceedingsTitle") or "").strip(),
        "doi": doi,
        "publication_year": int(date_match.group(0)) if date_match else None,
        "source_tags": tags,
    }


def map_zotero_pdf_attachment(item):
    if not isinstance(item, dict) or not item.get("key"):
        return None
    data = item.get("data") or {}
    if (
        data.get("itemType") != "attachment"
        or data.get("linkMode") != "imported_file"
        or str(data.get("contentType") or "").lower() != "application/pdf"
    ):
        return None
    filename = str(data.get("filename") or data.get("title") or f"{item['key']}.pdf")
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1] or f"{item['key']}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename[:496]}.pdf"
    filename = filename[:500]
    return {"item_key": str(item["key"]), "filename": filename}


@transaction.atomic
def _upsert_zotero_item(library_id, mapped):
    reference = ExternalReference.objects.select_related("canonical_document").filter(
        provider=ExternalReference.Provider.ZOTERO,
        library_id=str(library_id),
        external_item_id=mapped["item_key"],
    ).first()
    if reference:
        reference.external_version = mapped["version"]
        reference.save(update_fields=("external_version", "updated_at"))
        _merge_zotero_metadata(reference.canonical_document, library_id, mapped)
        return reference.canonical_document, False

    if mapped["doi"]:
        canonical, created = CanonicalDocument.objects.get_or_create(doi=mapped["doi"])
    else:
        canonical, created = CanonicalDocument.objects.create(), True
    _merge_zotero_metadata(canonical, library_id, mapped)
    ExternalReference.objects.create(
        canonical_document=canonical,
        provider=ExternalReference.Provider.ZOTERO,
        library_id=str(library_id),
        external_item_id=mapped["item_key"],
        external_version=mapped["version"],
    )
    return canonical, created


def _import_zotero_pdf(
    canonical,
    uploader,
    library_type,
    library_id,
    api_key,
    attachment,
    request_file=None,
    store_file=None,
    local_api_available=False,
    request_local_text=None,
    open_local_file=None,
):
    association = associate_existing_pdf(canonical, uploader)
    if association:
        attachment["_pdf_source"] = "existing"
        return association

    base_url, library_path, _base_parts = _zotero_library_context(library_type, library_id, api_key)
    file_url = f"{base_url}{library_path}/items/{quote(attachment['item_key'], safe='')}/file"
    request_file = request_file or _request_file
    store_file = store_file or store_literature
    source = "web"

    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as temporary:
        local_stream = None
        if local_api_available:
            try:
                local_stream = _open_local_zotero_file(
                    library_type,
                    library_id,
                    attachment["item_key"],
                    request_local_text=request_local_text,
                    open_local_file=open_local_file,
                )
                prepared = _read_pdf_stream(local_stream, temporary, attachment["filename"])
                source = "local"
            except Exception:
                temporary.seek(0)
                temporary.truncate()
                local_stream = None
        if local_stream is None:
            prepared = _read_pdf_stream(request_file(file_url, api_key), temporary, attachment["filename"])
        document = save_pdf_upload(
            canonical,
            uploader,
            prepared,
            store_file=store_file,
            reuse_existing_pdf=True,
        )
    attachment["_pdf_source"] = source
    return "imported" if document is not None else "reused"


def _import_browser_pdf(canonical, uploader, uploaded_file, store_file=None):
    prepared = prepare_pdf(uploaded_file)
    association = associate_existing_pdf(canonical, uploader)
    if association:
        return association
    document = save_pdf_upload(
        canonical,
        uploader,
        prepared,
        store_file=store_file or store_literature,
        reuse_existing_pdf=True,
    )
    return "imported" if document is not None else "reused"


def _read_pdf_stream(stream, temporary, filename):
    size = 0
    with stream:
        while chunk := stream.read(64 * 1024):
            size += len(chunk)
            if size > settings.MCP_MAX_UPLOAD_BYTES:
                raise ZoteroImportError("PDF 文件超过上传大小上限。")
            temporary.write(chunk)
    temporary.seek(0)
    uploaded_file = File(temporary, name=filename)
    uploaded_file.content_type = "application/pdf"
    return prepare_pdf(uploaded_file)


def _zotero_local_api_available():
    try:
        with urlopen(Request("http://127.0.0.1:23119/api/"), timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def _open_local_zotero_file(
    library_type, library_id, attachment_key, request_local_text=None, open_local_file=None
):
    prefix = "/api/users/0" if library_type == "users" else f"/api/groups/{quote(str(library_id), safe='')}"
    url = f"http://127.0.0.1:23119{prefix}/items/{quote(attachment_key, safe='')}/file/view/url"
    request_local_text = request_local_text or _request_local_text
    file_url = request_local_text(url)
    parts = urlsplit(file_url.strip())
    if parts.scheme != "file" or parts.netloc or parts.query or parts.fragment:
        raise ZoteroImportError("Zotero Desktop 未返回安全的本地文件。")
    path = Path(url2pathname(parts.path))
    if not path.is_absolute():
        raise ZoteroImportError("Zotero Desktop 未返回安全的本地文件。")
    try:
        return (open_local_file or open)(path, "rb")
    except OSError as exc:
        raise ZoteroImportError("Zotero Desktop 中的本地 PDF 无法读取。") from exc


def _request_local_text(url):
    try:
        with urlopen(Request(url, headers={"Zotero-API-Version": "3"}), timeout=1) as response:
            return response.read(4096).decode("utf-8")
    except Exception as exc:
        raise ZoteroImportError("Zotero Desktop 中没有可读的本地 PDF。") from exc


def _record_pdf_failure(result, name, exc, api_key):
    result["pdf_failed"] += 1
    reason = str(exc).strip() or exc.__class__.__name__
    failure = f"{str(name)[:120]}: {reason[:200]}"
    if api_key:
        failure = failure.replace(api_key, "[redacted]")
    if len(result["pdf_failures"]) < 20:
        result["pdf_failures"].append(failure)
    return failure


def _merge_zotero_metadata(canonical, library_id, mapped):
    for field in ("title", "authors", "abstract", "journal", "publication_year", "source_tags"):
        if getattr(canonical, field) in (None, "", []) and mapped[field] not in (None, "", []):
            setattr(canonical, field, mapped[field])
    if not canonical.doi and mapped["doi"]:
        canonical.doi = mapped["doi"]
        canonical.identifiers = {**canonical.identifiers, "doi": mapped["doi"]}
    if canonical.metadata_status in {
        CanonicalDocument.MetadataStatus.PENDING,
        CanonicalDocument.MetadataStatus.INCOMPLETE,
    }:
        canonical.metadata_status = CanonicalDocument.MetadataStatus.NEEDS_REVIEW
        canonical.metadata_source = "zotero"
        canonical.metadata_confidence = 0.800
    canonical.metadata_evidence = {
        **canonical.metadata_evidence,
        "zotero": {
            "library_id": str(library_id),
            "item_key": mapped["item_key"],
            "version": mapped["version"],
            "fields": [
                field for field in ("title", "authors", "abstract", "journal", "doi", "publication_year", "source_tags")
                if mapped[field] not in (None, "", [])
            ],
        },
    }
    canonical.save()


def _request_page(url, api_key):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Zotero-API-Key": api_key,
            "Zotero-API-Version": "3",
            "User-Agent": "PLAB-Literature/1.0",
        },
    )
    try:
        with urlopen(request, timeout=settings.METADATA_HTTP_TIMEOUT) as response:
            return json.load(response), dict(response.headers.items())
    except Exception as exc:
        raise ZoteroImportError("Could not read the Zotero library.") from exc


def _request_file(url, api_key):
    request = Request(
        url,
        headers={
            "Accept": "application/pdf",
            "Zotero-API-Key": api_key,
            "Zotero-API-Version": "3",
            "User-Agent": "PLAB-Literature/1.0",
        },
    )
    try:
        return urlopen(request, timeout=settings.METADATA_HTTP_TIMEOUT)
    except Exception as exc:
        raise ZoteroImportError("无法下载 Zotero PDF。") from exc


def _next_link(link_header):
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return ""
