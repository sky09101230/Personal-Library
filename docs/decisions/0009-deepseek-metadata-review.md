# 0009: DeepSeek proposes metadata; uploaders confirm; administrators publish

## Status

Accepted

## Context

Deterministic PDF extraction, Crossref, and Zotero leave some literature incomplete or in conflict. Requiring administrators to enter every field does not scale, but allowing an LLM to overwrite canonical records would remove provenance and could publish fabricated metadata.

## Decision

- Store every DeepSeek result in a separate durable proposal/job record.
- Send only bounded page-labelled evidence and current structured metadata; never send original PDF bytes, Box locations, secrets, or user identity.
- Validate JSON structure, field types, DOI/year rules, and quoted page evidence locally.
- Allow an uploader to review only literature attached to one of their uploads; staff may review all records.
- Apply accepted values transactionally and record reviewer, timestamps, and before/after values.
- Reject stale proposals rather than overwriting a canonical record changed after generation.
- Keep `metadata_status` and `index_status` independent. Human confirmation may set metadata to `verified`; only an administrator may later publish it.
- Use one database-backed worker process for the current internal workload instead of adding a distributed queue dependency.

## Consequences

Review becomes a short evidence check, while AI output remains reversible and auditable. Upload success no longer depends on DeepSeek latency or availability. Deployment must configure a worker and explicitly accept that bounded unpublished text is sent to an external provider. A future multi-worker deployment will require stronger queue-claim semantics on PostgreSQL.
