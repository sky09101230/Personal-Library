from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from apps.box_upload.models import UploadedDocument
from apps.box_upload.storage import (
    NAS_WEBDAV,
    ORIGINALS_NAMESPACE,
    PARSE_ARTIFACT_NAMESPACE,
    get_literature_storage,
)

from .models import DocumentParse


@dataclass(frozen=True, slots=True)
class LayoutRecord:
    record_type: str
    record_id: int
    model: type
    path_field: str
    backend: str
    source_path: str
    destination_path: str
    planning_error: str = ""


@dataclass(frozen=True, slots=True)
class LayoutAction:
    record_type: str
    record_id: int
    status: str
    source_path: str
    destination_path: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class LayoutMigrationResult:
    actions: tuple[LayoutAction, ...]
    dry_run: bool

    @property
    def counts(self):
        return dict(Counter(action.status for action in self.actions))

    @property
    def has_failures(self):
        return any(action.status in ("conflict", "error") for action in self.actions)


def migrate_literature_layout(*, dry_run=False, storage_factory=get_literature_storage):
    storages = {}
    records = _layout_records(storage_factory=storage_factory, storages=storages)
    duplicate_destinations = _duplicate_destinations(records)
    actions = []
    for record in records:
        if record.planning_error:
            actions.append(_action(record, "error", record.planning_error))
            continue
        destination_key = (record.backend, record.destination_path)
        if destination_key in duplicate_destinations:
            actions.append(
                _action(
                    record,
                    "conflict",
                    "Multiple source paths resolve to the same destination.",
                )
            )
            continue
        storage = storages[record.backend]
        actions.append(_migrate_record(record, storage, dry_run=dry_run))
    return LayoutMigrationResult(actions=tuple(actions), dry_run=dry_run)


def _layout_records(*, storage_factory, storages):
    records = []
    for uploaded_document in UploadedDocument.objects.filter(
        storage_backend=NAS_WEBDAV,
    ).order_by("pk"):
        records.append(
            _layout_record(
                record_type="upload",
                record=uploaded_document,
                path_field="remote_path",
                backend=uploaded_document.storage_backend,
                namespace=ORIGINALS_NAMESPACE,
                storage_factory=storage_factory,
                storages=storages,
            )
        )
    for document_parse in DocumentParse.objects.filter(
        artifact_storage_backend=NAS_WEBDAV,
    ).order_by("pk"):
        records.append(
            _layout_record(
                record_type="parse",
                record=document_parse,
                path_field="artifact_path",
                backend=document_parse.artifact_storage_backend,
                namespace=PARSE_ARTIFACT_NAMESPACE,
                storage_factory=storage_factory,
                storages=storages,
            )
        )
    return tuple(records)


def _layout_record(
    *,
    record_type,
    record,
    path_field,
    backend,
    namespace,
    storage_factory,
    storages,
):
    if backend not in storages:
        storages[backend] = storage_factory(backend)
    storage = storages[backend]
    source_path = getattr(record, path_field)
    planning_error = ""
    try:
        basename = PurePosixPath(source_path).name
        destination_path = storage.path_for(namespace, basename)
    except Exception as exc:
        destination_path = ""
        planning_error = str(exc)
    return LayoutRecord(
        record_type=record_type,
        record_id=record.pk,
        model=type(record),
        path_field=path_field,
        backend=backend,
        source_path=source_path,
        destination_path=destination_path,
        planning_error=planning_error,
    )


def _duplicate_destinations(records):
    sources_by_destination = {}
    for record in records:
        if record.planning_error:
            continue
        key = (record.backend, record.destination_path)
        sources_by_destination.setdefault(key, set()).add(record.source_path)
    return {
        key
        for key, source_paths in sources_by_destination.items()
        if len(source_paths) > 1
    }


def _migrate_record(record, storage, *, dry_run):
    try:
        if record.source_path == record.destination_path:
            if storage.exists(record.destination_path):
                return _action(record, "already")
            return _action(record, "conflict", "Database uses destination path, but the object is missing.")

        source_exists = storage.exists(record.source_path)
        destination_exists = storage.exists(record.destination_path)
        if source_exists and destination_exists:
            return _action(record, "conflict", "Source and destination both exist.")
        if not source_exists and not destination_exists:
            return _action(record, "conflict", "Source and destination are both missing.")
        if source_exists:
            if dry_run:
                return _action(record, "would_move")
            storage.move(record.source_path, record.destination_path)
            _update_database_path(record)
            return _action(record, "moved")
        if dry_run:
            return _action(record, "would_recover")
        _update_database_path(record)
        return _action(record, "recovered")
    except Exception as exc:
        return _action(record, "error", str(exc))


def _update_database_path(record):
    updated = record.model.objects.filter(
        pk=record.record_id,
        **{record.path_field: record.source_path},
    ).update(**{record.path_field: record.destination_path})
    if updated:
        return
    current_path = record.model.objects.filter(pk=record.record_id).values_list(
        record.path_field,
        flat=True,
    ).first()
    if current_path != record.destination_path:
        raise RuntimeError("Database path changed concurrently; rerun migration after review.")


def _action(record, status, message=""):
    return LayoutAction(
        record_type=record.record_type,
        record_id=record.record_id,
        status=status,
        source_path=record.source_path,
        destination_path=record.destination_path,
        message=message,
    )
