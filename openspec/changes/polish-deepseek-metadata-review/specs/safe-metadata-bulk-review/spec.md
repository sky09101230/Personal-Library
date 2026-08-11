## ADDED Requirements

### Requirement: Only locally low-risk proposals are bulk-confirmable
The system SHALL classify a succeeded metadata proposal as bulk-safe only when its core fields are complete and it has no local validation warnings.

#### Scenario: Complete warning-free proposal
- **WHEN** a succeeded proposal contains a title, at least one named author, a publication year, either a DOI or journal, and no validation warnings
- **THEN** the review queue marks it as safe for bulk confirmation

#### Scenario: Warning-bearing or incomplete proposal
- **WHEN** a succeeded proposal has any validation warning or lacks a required core field
- **THEN** the review queue requires individual detail review and does not offer a bulk-selection control for it

### Requirement: Safe queue items are convenient to confirm
The system SHALL preselect bulk-safe proposals on the current pending page and SHALL show the number selected before submission.

#### Scenario: Uploader opens a mixed pending queue
- **WHEN** the page contains both bulk-safe and individual-review proposals
- **THEN** only the bulk-safe proposals are selected by default
- **AND** the uploader can uncheck any selected proposal before confirming

### Requirement: Bulk safety is enforced by the server
The system MUST reject or skip any proposal that is not bulk-safe even when its ID is submitted directly to the bulk endpoint.

#### Scenario: Crafted bulk request includes a risky proposal
- **WHEN** an authorized uploader submits a succeeded proposal with warnings or incomplete core fields to the bulk endpoint
- **THEN** the system leaves its canonical metadata and proposal status unchanged
- **AND** reports that the proposal requires individual review

### Requirement: Bulk confirmation never publishes literature
The system SHALL preserve the existing separation between metadata confirmation and Agent publication for every bulk-confirmed proposal.

#### Scenario: Safe proposal is bulk confirmed
- **WHEN** an authorized uploader bulk confirms a safe proposal
- **THEN** the confirmed metadata is applied with the existing audit and stale-version checks
- **AND** the canonical document index status remains pending
