# AI metadata review specification

## ADDED Requirements

### Requirement: DeepSeek produces proposals rather than canonical truth

The system SHALL store DeepSeek output as a separate metadata proposal and SHALL NOT directly overwrite canonical metadata.

#### Scenario: Valid proposal

- **WHEN** DeepSeek returns valid structured metadata for a queued record
- **THEN** the system stores the provider, model, prompt version, evidence snapshot, proposal, and validation result
- **AND** the canonical metadata and publication status remain unchanged

#### Scenario: Unsupported claim

- **WHEN** a proposed field has no matching provider or page-labelled evidence
- **THEN** the system marks that field with a validation warning
- **AND** does not silently treat the claim as verified

### Requirement: Upload success is independent from DeepSeek

The system SHALL enqueue AI proposal work outside the PDF upload request.

#### Scenario: DeepSeek is unavailable

- **WHEN** a PDF upload succeeds but DeepSeek is disabled, times out, or fails
- **THEN** the uploaded file and deterministic metadata remain available
- **AND** canonical metadata and publication status are not changed by the failure
- **AND** the proposal shows a retryable or disabled state

### Requirement: Evidence sent to DeepSeek is bounded

The system SHALL send only the minimum page-labelled text and structured evidence required for metadata extraction.

#### Scenario: Proposal request is built

- **WHEN** a queued proposal is sent to DeepSeek
- **THEN** the request excludes PDF bytes, NJU Box paths or URLs, credentials, and uploader identity
- **AND** records an input fingerprint and prompt version for audit

### Requirement: Uploaders confirm their own literature

The system SHALL allow an uploader to review a canonical record only when one of their uploaded files is attached to it, while staff may review any record.

#### Scenario: Uploader reviews a proposal

- **WHEN** the uploader opens an eligible succeeded proposal
- **THEN** the system displays current values, proposed values, page/provider evidence, and validation warnings
- **AND** allows the uploader to accept, edit and confirm, reject, or request regeneration

#### Scenario: Unrelated user attempts review

- **WHEN** an authenticated user who is neither an uploader nor staff requests the proposal or decision endpoint
- **THEN** the system denies access without exposing proposal evidence

#### Scenario: Zotero-only record

- **WHEN** a canonical record has no uploaded PDF and only an external reference
- **THEN** only staff may review its proposal

### Requirement: Human confirmation is atomic and auditable

The system SHALL apply confirmed values transactionally and retain reviewer identity, timestamps, and before/after values.

#### Scenario: Confirmed complete proposal

- **WHEN** an authorized reviewer confirms a complete, conflict-free proposal
- **THEN** the system writes the confirmed canonical fields and sets metadata status to verified
- **AND** records the reviewer and accepted before/after values
- **AND** leaves publication status unchanged

#### Scenario: Canonical metadata changed after generation

- **WHEN** the reviewer submits a proposal generated from an older canonical version
- **THEN** the system marks the proposal stale
- **AND** does not overwrite the newer canonical metadata

#### Scenario: Proposal is rejected

- **WHEN** an authorized reviewer rejects a proposal
- **THEN** the system records the rejection and reviewer
- **AND** leaves canonical metadata and publication status unchanged

### Requirement: Existing review records can be backfilled safely

The system SHALL provide a staff-only bounded operation to queue existing records that require metadata review.

#### Scenario: Backfill is requested

- **WHEN** staff queues existing pending, incomplete, needs-review, or conflict records
- **THEN** the system creates at most one active proposal per canonical record
- **AND** skips verified records unless explicit regeneration is requested

### Requirement: AI review never publishes literature

The system SHALL keep metadata confirmation and Agent publication as separate authorization steps.

#### Scenario: Uploader accepts a proposal

- **WHEN** uploader confirmation changes metadata status to verified
- **THEN** index status remains pending
- **AND** the literature remains unavailable through MCP until an administrator explicitly publishes it
