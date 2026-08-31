## Why

The current Zotero page requires users to know a Collection Key and starts importing immediately, so it cannot confirm the account, browse collections, or select individual records. Web-only file reads also miss PDFs that exist in Zotero Desktop but were not uploaded to Zotero File Storage.

## What Changes

- Save one encrypted Zotero Web API connection per administrator and validate it before browsing.
- Show accessible collections with their names and keys, then show selectable top-level items for a chosen collection.
- Import only the selected records while retaining the existing progress and partial-failure behavior.
- Prefer the matching `imported_file` PDF from the local Zotero Desktop API, with the existing Web file endpoint as fallback.
- Keep snapshots, URL attachments, `linked_file`, and non-PDF attachments excluded.

## Capabilities

### New Capabilities

- `zotero-connected-import`: Covers saved secure connection configuration, collection/item browsing, selected import, and local-first PDF retrieval.

### Modified Capabilities

None.

## Impact

This affects the Zotero form, view, importer, template, tests, and database schema. It declares the already-installed `cryptography` package as a runtime dependency. The local-first path requires Zotero Desktop on the Django host with its local API enabled; remote deployments retain Web fallback.
