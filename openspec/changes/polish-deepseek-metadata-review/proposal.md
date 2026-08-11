## Why

The DeepSeek review queue already supports bulk confirmation, but uploaders still have to decide and select every candidate manually. The final workflow should make low-risk proposals fast to confirm while preventing warning-bearing or incomplete proposals from being bulk-approved by mistake.

## What Changes

- Classify succeeded proposals as safe for bulk confirmation only when their core fields are complete and local validation produced no warnings.
- Preselect safe proposals on the current queue page and show clear safe-versus-needs-review counts.
- Require proposals with warnings or incomplete core fields to be opened and confirmed individually.
- Enforce the same safety rule on the server so crafted bulk requests cannot bypass the UI.
- Keep the current pypdf evidence pipeline; do not add Docling to dependencies or production review paths.

## Capabilities

### New Capabilities
- `safe-metadata-bulk-review`: Risk-aware queue presentation and server-enforced bulk confirmation for DeepSeek metadata proposals.

### Modified Capabilities

None.

## Impact

- Affects the metadata review queue/detail views, queue template, review tests, and the metadata-review decision record.
- Does not change the database schema, DeepSeek API contract, canonical metadata rules, or publication authorization.
- Adds no PDF parser or runtime dependency.
