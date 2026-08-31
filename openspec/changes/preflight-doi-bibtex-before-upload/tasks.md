## 1. Contract Records

- [x] 1.1 Record the upload-blocking decision and preparation contract in project documentation

## 2. Upload Preflight

- [x] 2.1 Preflight each unique new DOI-bearing PDF before any NAS write and reuse the fetched BibTeX
- [x] 2.2 Return a distinct AJAX failure and show a blocking browser alert with retry enabled

## 3. Verification

- [x] 3.1 Add regression tests proving failure causes zero storage and database writes while success and no-DOI paths continue
- [x] 3.2 Run focused and full tests plus strict OpenSpec validation
- [ ] 3.3 Run local browser acceptance checks for the alert, retry state, and no redirect
