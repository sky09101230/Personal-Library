## Purpose

Provide administrators with a secure, inspectable Zotero connection workflow for browsing collections, selecting records, and importing locally available PDFs before using cloud storage.

## ADDED Requirements

### Requirement: Administrator connects a saved Zotero account
The system SHALL validate a Zotero Library ID and API Key before saving the connection, SHALL encrypt the API Key at rest, and SHALL never return the saved key to the browser.

#### Scenario: Valid connection
- **WHEN** an administrator submits credentials that can read the requested Zotero library
- **THEN** the system saves the connection and returns the accessible collections

#### Scenario: Invalid connection
- **WHEN** Zotero rejects the Library ID or API Key
- **THEN** the system reports the connection failure without replacing a previously valid saved connection

### Requirement: Administrator browses collections and items
The system SHALL display every accessible collection using its name and Collection Key and SHALL list the top-level bibliographic items in a selected collection.

#### Scenario: Collection selected
- **WHEN** an administrator selects a returned collection
- **THEN** the system displays its importable bibliographic records with a selectable Item Key

### Requirement: Administrator imports selected records
The system SHALL import only the explicitly selected bibliographic Item Keys and SHALL retain the existing metadata deduplication, PDF filtering, progress, and partial-failure semantics.

#### Scenario: Subset selected
- **WHEN** an administrator selects some records in a collection and starts import
- **THEN** only those records are passed to the import pipeline

### Requirement: Local Zotero PDF is preferred
For an eligible `imported_file` PDF attachment, the system SHALL attempt to read the matching file through the Zotero Desktop local API before requesting the Web API file and SHALL validate and store either source identically.

#### Scenario: Local file available
- **WHEN** Zotero Desktop is reachable on the Django host and returns the attachment's local file
- **THEN** the system reads that local PDF and does not request its Web file

#### Scenario: Local file unavailable
- **WHEN** Zotero Desktop is unavailable or cannot provide the eligible attachment file
- **THEN** the system falls back to the Zotero Web file endpoint and retains the existing per-attachment failure reporting

#### Scenario: Linked local file
- **WHEN** an attachment has `linkMode=linked_file`
- **THEN** the system skips it even if Zotero Desktop can resolve its path

### Requirement: Local file paths remain private
The system SHALL accept local attachment paths only from the fixed loopback Zotero API and SHALL not expose the resulting path in UI results, logs, or stored upload metadata.

#### Scenario: Local read fails
- **WHEN** a local file cannot be opened or validated
- **THEN** the progress result reports a controlled source failure without the filesystem path
