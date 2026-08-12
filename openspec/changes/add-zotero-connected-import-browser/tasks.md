## 1. Saved connection

- [x] 1.1 Add the encrypted per-user Zotero connection model, migration, and declared encryption dependency.
- [x] 1.2 Validate and save credentials only after a successful Web API collection request.

## 2. Collection and item browser

- [x] 2.1 Add paginated collection discovery and selected Item Key retrieval.
- [x] 2.2 Replace the single-step page with connect, collection, item selection, and selected import actions.

## 3. Local-first PDFs

- [x] 3.1 Probe the fixed Zotero Desktop loopback API once and safely resolve eligible local attachment files.
- [x] 3.2 Route local and Web streams through the existing validation/storage path and expose the active source in progress.

## 4. Verification

- [x] 4.1 Test encrypted connection persistence, collection/item browsing, selected import, local preference, Web fallback, and linked-file exclusion.
- [x] 4.2 Run Django checks, migration drift check, full tests, and strict OpenSpec validation.
