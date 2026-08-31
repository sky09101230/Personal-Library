## 1. Candidate data and taxonomy

- [x] 1.1 Add the candidate model, review states, provenance fields, validation fields, and admin registration.
- [x] 1.2 Add migrations for the candidate table and six-part research-task taxonomy while preserving existing literature purpose rows.

## 2. Shared candidate services

- [x] 2.1 Implement bounded ZIP inspection, forbidden-content checks, metadata normalization, content hashing, and private candidate storage.
- [x] 2.2 Implement candidate enrichment that reuses the existing DeepSeek summary/classification flow and preserves manual category choices.
- [x] 2.3 Implement atomic candidate publication and rejection cleanup by reusing the formal NAS release path.

## 3. Ingestion paths

- [x] 3.1 Add the logged-in single-ZIP submission form, candidate creation flow, and user-scoped “My submissions” view.
- [x] 3.2 Add GitHub source scanning as a background job that refreshes per-Skill candidates without directly publishing them.

## 4. Review interface

- [x] 4.1 Add staff candidate filters, detail editing, rejection, and single or batch approval actions.
- [x] 4.2 Replace the staff GitHub sync action with source scanning and link the Skills page to submission and review workflows.

## 5. Verification and documentation

- [x] 5.1 Add focused tests for ZIP boundary validation, role isolation, scan state preservation, manual classification, approval rollback, and formal publication.
- [x] 5.2 Record the candidate-boundary decision, run Django tests and migration checks, and pass strict OpenSpec validation.
