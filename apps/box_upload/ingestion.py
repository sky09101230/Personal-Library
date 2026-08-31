import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from .models import CanonicalDocument, UploadedDocument
from .services import LiteratureStorageError
from .storage import get_literature_storage, store_literature


class PdfValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedPdf:
    uploaded_file: object
    filename: str
    size: int
    sha256: str


def prepare_pdf(uploaded_file):
    filename = str(getattr(uploaded_file, "name", "")).replace("\\", "/").rsplit("/", 1)[-1][:500]
    if not filename or not filename.lower().endswith(".pdf"):
        raise PdfValidationError("仅允许上传 PDF 文件。")

    digest = hashlib.sha256()
    header = bytearray()
    size = 0
    uploaded_file.seek(0)
    try:
        for chunk in uploaded_file.chunks():
            size += len(chunk)
            if size > settings.MCP_MAX_UPLOAD_BYTES:
                raise PdfValidationError("PDF 文件超过上传大小上限。")
            digest.update(chunk)
            if len(header) < 1024:
                header.extend(chunk[: 1024 - len(header)])
    finally:
        uploaded_file.seek(0)

    if b"%PDF-" not in header:
        raise PdfValidationError("文件内容不是有效 PDF。")

    uploaded_file.name = filename
    uploaded_file.content_type = "application/pdf"
    return PreparedPdf(uploaded_file, filename, size, digest.hexdigest())


def associate_existing_pdf(canonical, uploader):
    with transaction.atomic():
        canonical = CanonicalDocument.objects.select_for_update().get(pk=canonical.pk)
        if not canonical.uploads.filter(
            status=UploadedDocument.Status.UPLOADED,
            file_role=UploadedDocument.FileRole.PRIMARY,
        ).exists():
            return None
        already_associated = canonical.uploaders.filter(pk=uploader.pk).exists()
        canonical.uploaders.add(uploader)
        if canonical.index_status != CanonicalDocument.IndexStatus.PUBLISHED:
            canonical.index_status = CanonicalDocument.IndexStatus.PUBLISHED
            canonical.save(update_fields=("index_status", "updated_at"))
    return "skipped" if already_associated else "reused"


def save_pdf_upload(
    canonical,
    uploader,
    prepared,
    store_file=None,
    reuse_existing_pdf=False,
    file_role=UploadedDocument.FileRole.PRIMARY,
    relationship_evidence=None,
):
    caller_canonical = canonical
    store_file = store_file or store_literature
    stored = store_file(prepared.uploaded_file)
    prepared.uploaded_file.seek(0)
    try:
        with transaction.atomic():
            canonical = CanonicalDocument.objects.select_for_update().get(pk=canonical.pk)
            existing_upload = canonical.uploads.filter(
                status=UploadedDocument.Status.UPLOADED,
                sha256=prepared.sha256,
                file_role=file_role,
            ).first()
            if existing_upload is None and reuse_existing_pdf and file_role == UploadedDocument.FileRole.PRIMARY:
                existing_upload = canonical.uploads.filter(
                    status=UploadedDocument.Status.UPLOADED,
                    file_role=UploadedDocument.FileRole.PRIMARY,
                ).first()
            duplicate_type = (
                UploadedDocument.DuplicateType.EXACT
                if UploadedDocument.objects.filter(sha256=prepared.sha256).exists()
                else UploadedDocument.DuplicateType.NEW
            )
            document = None if existing_upload else UploadedDocument.objects.create(
                    canonical_document=canonical,
                    uploader=uploader,
                    original_name=prepared.filename,
                    remote_path=stored.remote_path,
                    storage_backend=stored.backend,
                    sha256=prepared.sha256,
                    size=prepared.size,
                    content_type="application/pdf",
                    file_role=file_role,
                    relationship_evidence=relationship_evidence or {},
                    duplicate_type=duplicate_type,
                )
            if existing_upload:
                canonical.uploaders.add(uploader)

            update_fields = []
            if (
                file_role == UploadedDocument.FileRole.PRIMARY
                and
                not canonical.sha256
                and not CanonicalDocument.objects.exclude(pk=canonical.pk).filter(sha256=prepared.sha256).exists()
            ):
                canonical.sha256 = prepared.sha256
                update_fields.append("sha256")
            if (
                file_role == UploadedDocument.FileRole.PRIMARY
                and canonical.index_status != CanonicalDocument.IndexStatus.PUBLISHED
            ):
                canonical.index_status = CanonicalDocument.IndexStatus.PUBLISHED
                update_fields.append("index_status")
            if update_fields:
                canonical.save(update_fields=(*update_fields, "updated_at"))
    except Exception:
        try:
            get_literature_storage(stored.backend).delete(stored.remote_path)
        except LiteratureStorageError:
            pass
        raise
    if document is None:
        get_literature_storage(stored.backend).delete(stored.remote_path)
    if file_role == UploadedDocument.FileRole.PRIMARY:
        caller_canonical.sha256 = canonical.sha256
        caller_canonical.index_status = canonical.index_status
    return document
