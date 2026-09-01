from dataclasses import dataclass
import hashlib
import json

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.box_upload.storage import PARSE_ARTIFACT_NAMESPACE, get_literature_storage


PARSE_ARTIFACT_CONTENT_TYPE = "application/vnd.plab.parsed-document+json"


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    storage_backend: str
    path: str
    sha256: str
    content_type: str
    size: int


def serialize_parse_artifact(parsed_document):
    return json.dumps(
        parsed_document.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def store_parse_artifact(uploaded_document, job, parsed_document, *, storage_factory=get_literature_storage):
    content = serialize_parse_artifact(parsed_document)
    filename = f"parse-{uploaded_document.pk}-{job.run_id}-{parsed_document.schema_version}.json"
    artifact_file = SimpleUploadedFile(filename, content, content_type=PARSE_ARTIFACT_CONTENT_TYPE)
    storage = storage_factory(uploaded_document.storage_backend)
    path = storage.upload(artifact_file, namespace=PARSE_ARTIFACT_NAMESPACE)
    return ArtifactReference(
        storage_backend=storage.name,
        path=path,
        sha256=hashlib.sha256(content).hexdigest(),
        content_type=PARSE_ARTIFACT_CONTENT_TYPE,
        size=len(content),
    )
