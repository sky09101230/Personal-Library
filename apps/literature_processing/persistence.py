from dataclasses import asdict

from django.db import transaction

from apps.box_upload.storage import get_literature_storage

from .artifacts import store_parse_artifact
from .chunking import chunk_document
from .models import DocumentParse, LiteratureChunk


def persist_parsed_document(
    job,
    parsed_document,
    *,
    artifact_writer=store_parse_artifact,
    chunker=chunk_document,
):
    existing = DocumentParse.objects.filter(job=job).first()
    if existing is not None:
        return existing
    if job.parser_version != parsed_document.parser_version:
        raise ValueError("Job parser version does not match parsed document.")

    artifact = artifact_writer(job.uploaded_document, job, parsed_document)
    chunks = chunker(parsed_document)
    try:
        with transaction.atomic():
            document_parse = DocumentParse.objects.create(
                job=job,
                parser_name=parsed_document.parser_name,
                parser_version=parsed_document.parser_version,
                schema_version=parsed_document.schema_version,
                page_count=len(parsed_document.pages),
                artifact_storage_backend=artifact.storage_backend,
                artifact_path=artifact.path,
                artifact_sha256=artifact.sha256,
                artifact_content_type=artifact.content_type,
                artifact_size=artifact.size,
                warnings=list(parsed_document.warnings),
            )
            LiteratureChunk.objects.bulk_create(
                LiteratureChunk(document_parse=document_parse, **asdict(chunk))
                for chunk in chunks
            )
    except Exception:
        _delete_artifact_safely(artifact)
        raise
    return document_parse


def _delete_artifact_safely(artifact):
    try:
        get_literature_storage(artifact.storage_backend).delete(artifact.path)
    except Exception:
        pass
