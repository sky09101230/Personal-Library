from dataclasses import asdict

from django.db import transaction

from apps.box_upload.storage import get_literature_storage

from .artifacts import store_parse_artifact, store_raw_parse_artifact
from .chunking import chunk_document
from .models import DocumentParse, LiteratureChunk
from .parsers import ParserOutput, STRUCTURED_PARSE_SCHEMA_VERSION
from .structure_chunking import STRUCTURE_CHUNKER_VERSION, chunk_structured_document


def persist_parsed_document(
    job,
    parsed_document,
    *,
    artifact_writer=store_parse_artifact,
    raw_artifact_writer=store_raw_parse_artifact,
    chunker=chunk_document,
):
    existing = DocumentParse.objects.filter(job=job).first()
    if existing is not None:
        return existing
    if isinstance(parsed_document, ParserOutput):
        parser_output = parsed_document
        parsed_document = parser_output.document
    else:
        parser_output = ParserOutput(document=parsed_document)

    raw_artifact = None
    try:
        if parser_output.raw_artifact is not None:
            raw_artifact = raw_artifact_writer(
                job.uploaded_document,
                job,
                parser_output.raw_artifact,
            )
        artifact = artifact_writer(job.uploaded_document, job, parsed_document)
        if (
            job.chunker_version == STRUCTURE_CHUNKER_VERSION
            and parsed_document.schema_version == STRUCTURED_PARSE_SCHEMA_VERSION
        ):
            chunks = chunk_structured_document(parsed_document)
        else:
            chunks = chunker(parsed_document)
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
                runtime_info=dict(parsed_document.runtime_info),
                raw_artifact_storage_backend=(raw_artifact.storage_backend if raw_artifact else ""),
                raw_artifact_path=(raw_artifact.path if raw_artifact else ""),
                raw_artifact_sha256=(raw_artifact.sha256 if raw_artifact else ""),
                raw_artifact_content_type=(raw_artifact.content_type if raw_artifact else ""),
                raw_artifact_size=(raw_artifact.size if raw_artifact else None),
            )
            LiteratureChunk.objects.bulk_create(
                LiteratureChunk(document_parse=document_parse, **asdict(chunk))
                for chunk in chunks
            )
    except Exception:
        if "artifact" in locals():
            _delete_artifact_safely(artifact)
        if raw_artifact is not None:
            _delete_artifact_safely(raw_artifact)
        raise
    return document_parse


def _delete_artifact_safely(artifact):
    try:
        get_literature_storage(artifact.storage_backend).delete(artifact.path)
    except Exception:
        pass
