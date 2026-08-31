## 1. Contract And Persistence

- [x] 1.1 Record the staged-upload identity and formal-database boundary in a decision document
- [x] 1.2 Add upload review batch/item models and migration without changing existing records

## 2. Server Workflow

- [x] 2.1 Add uploader-owned batch creation and per-file staging with PDF validation, NAS storage and metadata preview
- [x] 2.2 Add title editing and DOI reparse behavior that updates only the pending item
- [x] 2.3 Add atomic batch confirmation, existing-document association and cancellation cleanup

## 3. Upload Experience

- [x] 3.1 Add four bounded upload workers with stable per-channel progress display
- [x] 3.2 Render the batch metadata table with red missing-title rows, yellow missing-journal rows and correction controls
- [x] 3.3 Gate confirmation on title completeness and show failed-confirmation/cancellation outcomes in place
- [x] 3.4 Compact the channel and review layout, scroll to review after parsing and redirect successful confirmation to Library

## 4. Verification

- [x] 4.1 Add focused model, permission, staging, reparse, confirmation, rollback and cancellation tests
- [x] 4.2 Run focused and full SQLite tests, Django migration checks, strict OpenSpec validation and diff checks
- [ ] 4.3 Verify the upload and review workflow in the local browser at desktop and mobile widths
- [x] 4.4 Create a scoped Git commit without including unrelated worktree changes

## 5. MCP Shared Review Flow

- [ ] 5.1 Extract thin request-independent staging, confirmation and cancellation services used by the Browser views
- [ ] 5.2 Route MCP PDF uploads through uploader-owned review batches and return pending review details plus the existing webpage URL
- [ ] 5.3 Restore an uploader-owned pending batch on the existing upload page while preserving 404 isolation for other users
- [ ] 5.4 Add non-blocking yellow warnings when DOI/BibTeX and PDF-extracted titles clearly disagree

## 6. MCP Review Verification

- [ ] 6.1 Add focused tests for MCP staging isolation, uploader ownership, browser access, confirmation publication, duplicate reuse and title warnings
- [ ] 6.2 Run focused and full tests, migration checks, strict OpenSpec validation and diff checks
- [ ] 6.3 Create scoped Git commits without including unrelated worktree changes
