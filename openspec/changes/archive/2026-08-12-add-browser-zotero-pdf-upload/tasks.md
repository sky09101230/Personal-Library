## 1. Browser item binding

- [x] 1.1 Add an optional PDF picker beside each Zotero item and bind it to the Item Key.
- [x] 1.2 Parse only files whose keys are present in the validated selected-item list.

## 2. Import pipeline

- [x] 2.1 Reuse one PDF validation/storage helper for browser, server-local, and Web streams.
- [x] 2.2 Process browser PDFs first and report imported, reused, skipped, or failed browser results in progress.

## 3. Verification

- [x] 3.1 Test successful browser upload, forged binding rejection, invalid PDF isolation, and automatic-source behavior without a browser file.
- [x] 3.2 Run targeted tests, Django checks, migration drift check, full tests, and strict OpenSpec validation.
