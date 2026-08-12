## Why

When Django runs on server A and an administrator uses browser B, server A cannot access B's Zotero Desktop loopback API or local filesystem. A browser-mediated PDF upload is therefore required for Zotero records whose PDF exists only on B.

## What Changes

- Show an optional local PDF picker beside each Zotero item in the selected collection.
- Bind each browser-selected PDF to its Zotero Item Key instead of guessing from filenames.
- Import browser PDFs before server-local Zotero Desktop or Zotero Web attachment sources.
- Preserve metadata and continue when one browser PDF is invalid or fails storage, reporting the failure in progress results.
- Keep snapshots, URL attachments, Zotero `linked_file`, and non-PDF files excluded from automatic attachment retrieval.

## Capabilities

### New Capabilities

- `browser-zotero-pdf-upload`: Covers securely uploading a browser-local PDF for an explicitly selected Zotero item and integrating it into the existing import result.

### Modified Capabilities

None.

## Impact

This affects the Zotero import template, request parsing, importer, progress counters, and tests. It reuses the existing upload storage and `UploadedDocument` model without new dependencies or migrations.
