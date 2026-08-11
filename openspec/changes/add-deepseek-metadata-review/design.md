# Design

## Context

`CanonicalDocument` already stores canonical metadata, deterministic evidence, conflicting candidates, metadata status, and publication status. `UploadedDocument` records the uploader and attached PDF. These are sufficient to determine who may review a PDF-backed canonical record, but they do not record an AI request, its input snapshot, its output, or a human decision.

DeepSeek supports an OpenAI-compatible Chat Completions API and JSON Output. JSON validity alone is insufficient: the service can return empty or truncated content, and a valid JSON object can still contain unsupported bibliographic claims. Local schema and evidence validation therefore remain mandatory.

## Goals

- Reduce human review to checking a concise, editable proposal.
- Preserve provenance from PDF pages, Crossref, Zotero, DeepSeek, and the confirming user.
- Never let an API failure regress upload success or alter existing canonical metadata.
- Never let AI generation or uploader confirmation publish a record automatically.

## Evidence and precedence

The proposal builder uses the following precedence when presenting candidates:

1. Exact DOI metadata returned by Crossref.
2. Structured Zotero fields and external-reference identity.
3. Page-labelled text and embedded metadata extracted locally from the PDF.
4. DeepSeek suggestions.

DeepSeek receives only a bounded evidence packet: current canonical fields, deterministic provider results, and page-labelled text snippets needed for title, authors, abstract, journal, year, DOI, and keywords. It does not receive PDF bytes, download URLs, API credentials, uploader identity, or unrelated pages.

Every proposed field contains a value, confidence, source references, and short evidence excerpts. A local validator checks types, DOI syntax, year range, required fields, maximum lengths, and that quoted PDF evidence occurs in the supplied page text. Unsupported fields are retained as warnings and cannot be silently accepted as verified.

## DeepSeek API contract

The client uses `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL` from environment variables. The default production model is configured rather than hard-coded so model retirement does not require a migration. The request uses JSON Output with an explicit JSON example and a versioned prompt.

The client treats empty content, malformed JSON, truncation, content filtering, insufficient capacity, timeout, and schema validation failure as explicit proposal failures. One bounded retry is allowed only for transient or empty-output failures. Raw chain-of-thought is neither requested nor stored.

## Durable proposal and job state

Add a `MetadataProposal` model with:

- canonical document and optional source upload;
- status (`queued`, `running`, `succeeded`, `failed`, `accepted`, `rejected`, `stale`);
- provider, model, prompt version, and input fingerprint;
- bounded evidence snapshot, structured proposal, validation warnings, and error code/message;
- requested-by, reviewed-by, requested/reviewed timestamps;
- canonical `updated_at` snapshot and accepted before/after values for audit.

The proposal record doubles as the small database-backed job. A single worker management command claims queued rows, calls DeepSeek, validates the result, and stores the proposal. The first deployment supports one worker process, which is sufficient for the internal workload and avoids adding a distributed queue dependency. Upload requests only enqueue work after deterministic metadata resolution and never wait for DeepSeek.

Existing incomplete, needs-review, conflict, or pending records can be queued through a staff-only action or bounded management command. Verified records are skipped unless an administrator explicitly requests regeneration.

## Review authorization and workflow

An authenticated user may review a canonical document when they uploaded at least one attached `UploadedDocument`; staff may review any document. Zotero-only records without an uploader remain staff-reviewable.

The review page displays current canonical values, AI proposals, provider/PDF evidence, validation warnings, and editable final values. The reviewer may:

- accept the proposal as shown;
- edit values and confirm the edited result;
- reject the proposal without changing canonical metadata;
- request regeneration when the proposal failed or is rejected.

Acceptance runs in one transaction. It locks the canonical record, checks that its `updated_at` still matches the proposal snapshot, writes the confirmed fields, records before/after values and reviewer identity, and sets metadata status to `verified` only when required fields and conflict checks pass. Otherwise it saves the edits as `needs_review` with visible warnings. `index_status` is never changed by this workflow.

If canonical metadata changed after generation, the proposal becomes `stale`; the reviewer must regenerate or explicitly rebase it rather than overwriting newer data.

## User interface

The library summary gains a “待上传者确认” count. Each eligible row shows proposal state and an action such as “生成中”, “检查 AI 建议”, “重新生成”, or “等待上传者确认”. A dedicated review queue defaults to the signed-in uploader's records; staff can view all.

The comparison form is intentionally field-oriented rather than exposing raw JSON. Evidence excerpts retain page numbers and provider identifiers so confirmation is a verification task, not blind approval.

## Privacy and failure handling

- The feature is disabled when `DEEPSEEK_API_KEY` is absent.
- No secret is stored in the database, logs, proposal payload, or browser.
- Only bounded extracted text leaves the server; unpublished PDFs remain in NJU Box.
- DeepSeek failure leaves current metadata and publication status unchanged.
- Deleting an upload does not delete an accepted audit trail when the canonical record remains.
- Logs use proposal/document IDs and error codes, not API keys or full evidence payloads.

## Verification strategy

All automated tests mock the DeepSeek boundary. Contract tests cover valid JSON, empty output, truncation, malformed output, unsupported evidence, timeout, and retry limits. Permission tests cover uploader, unrelated user, staff, and Zotero-only records. State tests cover upload independence, stale proposals, transactional acceptance, rejection, backfill, and the invariant that no review action publishes literature.
