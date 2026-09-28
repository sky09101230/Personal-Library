"""Bounded reads of parser assets; handles never expose storage paths."""

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from apps.box_upload.storage import get_literature_storage

from .evidence import EvidenceError


MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}


def read_figure_asset(document_parse, evidence):
    handle = evidence.asset_handle or {}
    if evidence.kind != "figure" or not handle.get("asset_path"):
        raise EvidenceError("asset_unavailable", "Figure asset is unavailable.")
    try:
        storage = get_literature_storage(document_parse.raw_artifact_storage_backend)
        stream = storage.open_stream(document_parse.raw_artifact_path)
        raw = b"".join(stream.iter_chunks())
        stream.close()
        if len(raw) > MAX_BUNDLE_BYTES:
            raise EvidenceError("resource_limit", "Parser asset bundle is too large.")
        with ZipFile(BytesIO(raw)) as bundle:
            segment_name = f"segments/part-{int(handle.get('segment_index', 0)) + 1:03d}.zip"
            segment = bundle.read(segment_name)
        with ZipFile(BytesIO(segment)) as archive:
            names = _safe_names(archive)
            target = _resolve_member(names, handle["asset_path"])
            info = archive.getinfo(target)
            if info.file_size > MAX_IMAGE_BYTES:
                raise EvidenceError("resource_limit", "Figure image is too large.")
            data = archive.read(target)
        mime = _mime_for(target, data)
        return mime, data
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise EvidenceError("asset_unavailable", "Figure asset is unavailable.") from exc


def _safe_names(archive):
    names = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or info.is_dir():
            raise EvidenceError("unsafe_asset", "Parser asset path is unsafe.")
        names.append(info.filename)
    if len(names) != len(set(names)):
        raise EvidenceError("unsafe_asset", "Parser asset paths are ambiguous.")
    return tuple(names)


def _resolve_member(names, asset_path):
    path = PurePosixPath(str(asset_path).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise EvidenceError("unsafe_asset", "Parser asset path is unsafe.")
    candidates = [name for name in names if PurePosixPath(name).as_posix() == path.as_posix()]
    if len(candidates) != 1:
        raise EvidenceError("asset_unavailable", "Figure asset could not be uniquely resolved.")
    return candidates[0]


def _mime_for(name, data):
    lower = name.lower()
    if lower.endswith(".png") and data.startswith(ALLOWED_MIME["image/png"]):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")) and data.startswith(ALLOWED_MIME["image/jpeg"]):
        return "image/jpeg"
    if lower.endswith(".webp") and data.startswith(ALLOWED_MIME["image/webp"]):
        return "image/webp"
    raise EvidenceError("unsafe_asset", "Figure asset type is not allowed.")
