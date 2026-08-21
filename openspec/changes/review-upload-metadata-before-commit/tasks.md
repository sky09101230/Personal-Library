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
