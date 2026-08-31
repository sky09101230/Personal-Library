## 1. Zotero attachment ingestion

- [x] 1.1 Add paginated child-item discovery and strict hosted-PDF eligibility filtering.
- [x] 1.2 Stream eligible file downloads into a temporary Django file with SHA-256 and PDF signature validation.
- [x] 1.3 Store distinct PDFs, create `UploadedDocument` rows for the importing staff user, and clean remote storage on database failure.

## 2. Progress and failure reporting

- [x] 2.1 Extend import progress events and final counters for imported, reused, skipped, and failed PDFs.
- [x] 2.2 Show per-attachment failures without immediately redirecting away from the final report.

## 3. Verification

- [x] 3.1 Test hosted-PDF import, unsupported attachment skipping, identical-content reuse, and isolated attachment failure.
- [x] 3.2 Run Django checks, migration drift check, full tests, and strict OpenSpec validation.
