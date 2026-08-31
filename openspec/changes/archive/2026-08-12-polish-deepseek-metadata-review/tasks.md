## 1. Risk-aware review behavior

- [x] 1.1 Add one shared bulk-safety predicate and expose safe/individual-review state and counts in the pending queue.
- [x] 1.2 Enforce the bulk-safety predicate in the bulk accept endpoint while preserving authorization, stale checks, audit, and unpublished status.

## 2. Uploader experience

- [x] 2.1 Preselect safe current-page proposals, label risk items as detail-only, and keep an explicit final confirmation with selected count.
- [x] 2.2 Preserve remaining-count context when the individual confirmation form is invalid.

## 3. Decision and verification

- [x] 3.1 Record the pypdf production decision and rejected Docling integration boundary without adding dependencies.
- [x] 3.2 Add focused queue and crafted-POST tests, then run focused tests, the full suite, compile checks, and strict OpenSpec validation.
