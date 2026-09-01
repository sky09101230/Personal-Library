from io import BytesIO
import json
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from .client import MinerUError
from .types import MinerURawResult, MinerUStructuredSegment


RAW_BUNDLE_CONTENT_TYPE = "application/vnd.plab.mineru-result+zip"
MAX_STRUCTURED_JSON_BYTES = 128 * 1024 * 1024


class MinerUArtifactError(MinerUError):
    code = "mineru_artifact"


def read_structured_segments(raw_result: MinerURawResult):
    return tuple(_read_segment(segment) for segment in raw_result.segments)


def serialize_raw_bundle(raw_result: MinerURawResult):
    manifest = {
        "schema_version": "plab.mineru-raw-bundle.v1",
        "provider": "mineru",
        "batch_id": raw_result.batch_id,
        "model_version": raw_result.model_version,
        "page_count": raw_result.page_count,
        "segments": [
            {
                "index": segment.index,
                "page_range": segment.page_range.expression,
                "data_id": segment.data_id,
                "archive_path": f"segments/part-{segment.index + 1:03d}.zip",
            }
            for segment in raw_result.segments
        ],
    }
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        for segment in raw_result.segments:
            bundle.writestr(
                f"segments/part-{segment.index + 1:03d}.zip",
                segment.archive_bytes,
            )
    return target.getvalue()


def _read_segment(segment):
    try:
        with ZipFile(BytesIO(segment.archive_bytes)) as archive:
            names = _safe_names(archive)
            legacy = sorted(
                name
                for name in names
                if name.lower().endswith("_content_list.json")
                and not name.lower().endswith("_content_list_v2.json")
            )
            v2 = sorted(name for name in names if name.lower().endswith("_content_list_v2.json"))
            if legacy:
                source_name = legacy[0]
                source_format = "content_list"
            elif v2:
                source_name = v2[0]
                source_format = "content_list_v2"
            else:
                raise MinerUArtifactError("MinerU archive has no structured content list.")
            info = archive.getinfo(source_name)
            if info.file_size > MAX_STRUCTURED_JSON_BYTES:
                raise MinerUArtifactError("MinerU structured JSON exceeds the size limit.")
            try:
                payload = json.loads(archive.read(source_name))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MinerUArtifactError("MinerU structured JSON is invalid.") from exc
    except BadZipFile as exc:
        raise MinerUArtifactError("MinerU result is not a valid ZIP archive.") from exc
    return MinerUStructuredSegment(
        index=segment.index,
        page_range=segment.page_range,
        data_id=segment.data_id,
        source_format=source_format,
        source_name=source_name,
        payload=payload,
    )


def _safe_names(archive):
    names = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise MinerUArtifactError("MinerU archive contains an unsafe path.")
        names.append(info.filename)
    return tuple(names)
