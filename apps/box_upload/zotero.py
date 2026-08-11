import hashlib
import json
import re
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files import File
from django.db import transaction

from .metadata import normalize_doi
from .models import CanonicalDocument, ExternalReference, UploadedDocument
from .storage import get_literature_storage, store_literature


class ZoteroImportError(Exception):
    pass


def import_zotero_library(
    library_type,
    library_id,
    api_key,
    collection_key="",
    uploader=None,
    request_page=None,
    request_file=None,
    store_file=None,
):
    result = None
    for event in iter_zotero_import_library(
        library_type,
        library_id,
        api_key,
        collection_key=collection_key,
        uploader=uploader,
        request_page=request_page,
        request_file=request_file,
        store_file=store_file,
    ):
        if event.get("done"):
            result = event["result"]
    return result


def iter_zotero_import_library(
    library_type,
    library_id,
    api_key,
    collection_key="",
    uploader=None,
    request_page=None,
    request_file=None,
    store_file=None,
):
    yield {"progress": 5, "message": "正在连接 Zotero"}
    items = []
    for page_number, (payload, headers) in enumerate(_iter_zotero_pages(
        library_type, library_id, api_key, collection_key=collection_key, request_page=request_page
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
        "pdf_failures": [],
    }
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
        yield {
            "progress": 35 + round(60 * index / total),
            "message": f"正在处理第 {index}/{total} 条文献",
        }
    yield {
        "progress": 100,
        "message": (
            f"导入完成：文献新增 {result['created']}，复用 {result['reused']}，跳过 {result['skipped']}；"
            f"PDF 导入 {result['pdf_imported']}，复用 {result['pdf_reused']}，"
            f"跳过 {result['pdf_skipped']}，失败 {result['pdf_failed']}"
        ),
        "result": result,
        "done": True,
    }


def fetch_zotero_items(library_type, library_id, api_key, collection_key="", request_page=None):
    items = []
    for payload, _headers in _iter_zotero_pages(
        library_type, library_id, api_key, collection_key=collection_key, request_page=request_page
    ):
        items.extend(payload)
    return items


def fetch_zotero_children(library_type, library_id, api_key, parent_key, request_page=None):
    base_url, library_path, base_parts = _zotero_library_context(library_type, library_id, api_key)
    next_url = (
        f"{base_url}{library_path}/items/{quote(str(parent_key), safe='')}/children?format=json&limit=100"
    )
    items = []
    for payload, _headers in _iter_json_pages(next_url, api_key, request_page, base_parts):
        items.extend(payload)
    return items


def _iter_zotero_pages(library_type, library_id, api_key, collection_key="", request_page=None):
    base_url, library_path, base_parts = _zotero_library_context(library_type, library_id, api_key)
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

    canonical = None
    if mapped["doi"]:
        canonical = CanonicalDocument.objects.filter(doi__iexact=mapped["doi"]).first()
    created = canonical is None
    canonical = canonical or CanonicalDocument.objects.create()
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
):
    base_url, library_path, _base_parts = _zotero_library_context(library_type, library_id, api_key)
    file_url = f"{base_url}{library_path}/items/{quote(attachment['item_key'], safe='')}/file"
    request_file = request_file or _request_file
    store_file = store_file or store_literature
    digest = hashlib.sha256()

    with request_file(file_url, api_key) as response, tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as temporary:
        size = 0
        while chunk := response.read(64 * 1024):
            temporary.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        temporary.seek(0)
        if b"%PDF-" not in temporary.read(1024):
            raise ZoteroImportError("下载内容不是有效 PDF。")
        sha256 = digest.hexdigest()
        if canonical.uploads.filter(sha256=sha256).exists():
            return "reused"

        temporary.seek(0)
        uploaded_file = File(temporary, name=attachment["filename"])
        uploaded_file.content_type = "application/pdf"
        stored = store_file(uploaded_file)
        try:
            with transaction.atomic():
                duplicate_type = (
                    UploadedDocument.DuplicateType.EXACT
                    if UploadedDocument.objects.filter(sha256=sha256).exists()
                    else UploadedDocument.DuplicateType.NEW
                )
                UploadedDocument.objects.create(
                    canonical_document=canonical,
                    uploader=uploader,
                    original_name=attachment["filename"],
                    remote_path=stored.remote_path,
                    storage_backend=stored.backend,
                    sha256=sha256,
                    size=size,
                    content_type="application/pdf",
                    duplicate_type=duplicate_type,
                )
        except Exception:
            try:
                get_literature_storage(stored.backend).delete(stored.remote_path)
            except Exception:
                pass
            raise
    return "imported"


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
