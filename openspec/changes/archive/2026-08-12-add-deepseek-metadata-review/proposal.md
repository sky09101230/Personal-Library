# Change: Add DeepSeek-assisted metadata review

## Why

The current ingestion flow can extract deterministic PDF evidence and resolve exact DOI records through Crossref, but incomplete, conflicting, and uncertain literature still requires field-by-field administrator editing. This does not scale for uploaders and turns metadata review into a central bottleneck.

The desired workflow is for DeepSeek to prepare an evidence-linked metadata proposal, while the uploader performs a short human confirmation. An AI proposal must not become verified metadata or enter Agent context without that confirmation.

## What Changes

- Generate structured DeepSeek metadata proposals from bounded, page-labelled PDF evidence and existing deterministic provider evidence.
- Validate every proposal against a strict local schema and retain per-field evidence, confidence, provider/model, prompt version, and failure details.
- Add a durable proposal/job record so API work can run outside the upload request and can be retried without changing canonical metadata.
- Add an uploader-facing review queue and comparison form for accepting, editing, or rejecting a proposal.
- Allow staff to review any record; allow an uploader to review only canonical literature attached to one of their uploads.
- Add a bounded backfill path for existing records that still need metadata review.
- Keep human confirmation and publication separate: acceptance may set metadata status to `verified`, but never sets `index_status=published`.

## Non-goals

- Treating DeepSeek output as an authoritative bibliographic source.
- Sending original PDF files, NJU Box URLs, credentials, or user identity to DeepSeek.
- Automatically publishing literature after AI generation or uploader confirmation.
- Replacing exact DOI resolution through Crossref or structured Zotero metadata.
- Adding PDF chunk indexing, retrieval, or Agent question answering in this change.

## Impact

- A migration adds durable metadata proposal, job, reviewer, and audit fields.
- A DeepSeek-compatible API client reads its key and model configuration only from environment variables.
- A small worker/management command processes queued proposals without making PDF upload success depend on the API.
- Authenticated library pages gain uploader-scoped review actions and proposal status.
- Deployment gains one worker process and DeepSeek configuration; the feature remains disabled when no API key is configured.
