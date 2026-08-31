## Context

The Zotero page already fetches server-validated collection items and posts selected Item Keys through one multipart request. The importer upserts metadata before processing automatic PDF attachments and already supports progress counters, isolated failure reporting, SHA-256 deduplication, remote storage cleanup, and `UploadedDocument` creation.

## Goals / Non-Goals

**Goals:**

- Transfer a PDF from browser B to server A through the existing authenticated multipart import request.
- Make the item-to-file relationship explicit and tamper-checked.
- Reuse the current PDF validation, storage, deduplication, and progress semantics.

**Non-Goals:**

- Read B's filesystem automatically, scan Zotero storage folders, or infer a match from filename/title.
- Upload a PDF back into Zotero or support multiple browser PDFs per bibliographic item.
- Change automatic attachment eligibility for Zotero snapshots, URLs, or linked files.

## Decisions

### One file input per Zotero Item Key

The client names each input `pdf_<itemKey>` and automatically checks its item when a file is chosen. The server accepts a file only when the suffix is a validated selected Item Key. This is smaller and safer than filename matching or a separate temporary-upload table.

### Pass browser files into the existing iterator

The view builds an Item Key to uploaded-file mapping from selected keys only. After metadata upsert, the iterator validates and stores that file first. A successful browser upload skips automatic attachment discovery for that item; a failed browser upload is reported and automatic sources are not silently substituted, so a wrong user-selected file remains visible.

### Share one storage helper

Extract the existing stream/hash/signature/storage/row-creation portion into one helper used by Web, server-local, and browser streams. The browser file keeps only its sanitized basename as `original_name`; client paths are never available to or stored by the server.

## Risks / Trade-offs

- [Large browser uploads consume request bandwidth before progress begins] → use native multipart streaming and existing Django upload handlers; add asynchronous direct uploads only if measured limits require them.
- [Administrator chooses the wrong PDF] → explicit per-record placement and filename display make the mapping inspectable; content-to-metadata verification remains manual.
- [A browser file fails but Web has a valid copy] → report the explicit choice rather than hiding it with fallback; the administrator can retry without that file to use automatic sources.

## Migration Plan

No schema migration or dependency is required. Deploy template, view, importer, and tests; rollback restores automatic sources only without affecting already imported PDFs.
