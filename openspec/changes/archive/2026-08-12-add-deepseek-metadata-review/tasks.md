# Tasks

- [x] 1. Add preparation notes for DeepSeek configuration/data exposure and a decision record for AI proposals, uploader review, and publication separation.
- [x] 2. Add the `MetadataProposal` model, statuses, audit fields, constraints, admin visibility, and migration.
- [x] 3. Build bounded page-labelled evidence packets and local proposal schema/evidence validators.
- [x] 4. Add the environment-configured DeepSeek JSON Output client with prompt versioning, explicit error mapping, and bounded retry behavior.
- [x] 5. Add the single-worker database queue management command and safe proposal claiming/state transitions.
- [x] 6. Enqueue eligible new uploads after deterministic resolution and add staff-only bounded backfill/regeneration actions.
- [x] 7. Add uploader/staff authorization helpers, review queue/detail routes, editable confirmation form, rejection, and regeneration endpoints.
- [x] 8. Apply accepted proposals transactionally with stale-version protection, before/after audit, metadata validation, and no publication change.
- [x] 9. Add library proposal counts, per-record review states/actions, and clear disabled/failure guidance.
- [x] 10. Add mocked API, permission, state-transition, upload-independence, stale-proposal, backfill, and MCP-publication-invariant tests; run full verification without real API calls.
