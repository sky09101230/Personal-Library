## Context

The existing importer reads top-level Zotero items synchronously, maps metadata into `CanonicalDocument`, and emits NDJSON progress events. PDF storage already accepts Django file objects and returns the backend and remote path used by `UploadedDocument`. See `proposal.md` and `specs/zotero-pdf-attachments/spec.md` for scope.

## Goals / Non-Goals

**Goals:**

- Preserve one request-scoped import and its observable progress.
- Stream remote file bytes into a spooled temporary file rather than holding arbitrary PDFs entirely in memory.
- Reuse the existing literature storage, upload model, preview, download, and deletion paths.
- Keep each attachment failure independent from metadata and later attachments.

**Non-Goals:**

- Download `imported_url`, `linked_url`, `linked_file`, snapshots, notes, annotations, or non-PDF files.
- Synchronize changed Zotero files incrementally or delete local PDFs when Zotero attachments disappear.
- Automatically publish Zotero-imported records to Agent context.
- Add a background job, new dependency, or attachment-identity database field.

## Decisions

### Read children then use the item file endpoint

For each mapped top-level item, request `/items/<parentKey>/children`, keep only `itemType=attachment`, `linkMode=imported_file`, and `contentType=application/pdf`, then GET `/items/<attachmentKey>/file` with the same API key. This matches Zotero Web API v3 and excludes local linked files before any file request.

### Spool, hash, validate, then store

Download in chunks into `SpooledTemporaryFile`, compute SHA-256 during transfer, and require a `%PDF-` header before storage. A Django `File` wrapper lets the existing NAS uploader stream chunks without a new storage abstraction.

### Deduplicate by canonical record and content hash

After download, reuse an existing `UploadedDocument` with the same canonical record and SHA-256. This avoids duplicate NAS writes without adding a migration. Tracking changed files by Zotero attachment key is deferred because the requested contract only requires identical-content reuse.

### Keep storage and database creation paired

After storage succeeds, create the upload row in a database transaction. If database creation fails, delete the newly written storage object. The importing staff user becomes the uploader; the canonical publication state remains unchanged.

### Report bounded failure details

Progress events include the current parent/attachment action. The final result adds imported, reused, skipped, failed, and short failure descriptions without API keys or response bodies. Metadata upsert happens before attachment work, so attachment failures cannot undo it.

## Risks / Trade-offs

- [A very large PDF can consume temporary disk space] → spool to disk after a small memory threshold and stream to NAS.
- [The Zotero file endpoint can redirect to hosted object storage] → start only from the validated HTTPS Zotero API origin and let the standard HTTPS client follow the provider redirect.
- [Reimport still downloads before SHA-256 deduplication] → accept the extra read; avoiding it requires persisted attachment identity and version state.
- [A proxy may buffer progress] → retain `X-Accel-Buffering: no`; attachment failures still appear in the final result even if intermediate events are buffered.

## Migration Plan

No schema migration is required. Deploy code and tests; rollback restores metadata-only behavior without altering already imported PDF records.
