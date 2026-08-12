# literature-ingestion Specification

## Purpose
将规范文献、PDF 附件和外部来源分开建模，使去重、metadata 证据、发布状态及 MCP 可见性能够独立且可追溯地管理。
## Requirements
### Requirement: Canonical literature is distinct from files and external sources

The system SHALL represent one canonical literature record independently from zero or more uploaded files and zero or more provider references.

#### Scenario: Zotero item without a PDF

- **WHEN** a valid Zotero top-level item is imported without an attachment
- **THEN** the system creates or reuses a canonical literature record without requiring a checksum-backed file
- **AND** stores a Zotero external reference for the item

#### Scenario: Exact duplicate PDF

- **WHEN** a PDF with an existing SHA-256 is uploaded
- **THEN** a new upload record references the existing canonical literature record
- **AND** existing canonical metadata is not overwritten

### Requirement: PDF metadata is evidence-based

The system SHALL distinguish extracted evidence from verified canonical metadata and SHALL NOT treat a generated guess as authoritative.

#### Scenario: Exact DOI resolves through Crossref

- **WHEN** a DOI is extracted from the PDF and the exact Crossref work is returned
- **THEN** the system stores the mapped canonical metadata, Crossref provenance, and a verified status
- **AND** keeps the extracted PDF evidence

#### Scenario: DOI is absent or resolution fails

- **WHEN** no DOI is extracted, or Crossref cannot resolve it
- **THEN** the file upload still succeeds
- **AND** the literature record is marked incomplete or needs review rather than verified

#### Scenario: Strong title disagreement

- **WHEN** PDF title evidence strongly disagrees with the exact-DOI Crossref title
- **THEN** the record is marked conflict and retains both values as candidates

### Requirement: Zotero import is one-way and credential-minimal

The system SHALL import Zotero Web API v3 metadata through an administrator connection whose API key is encrypted at rest and never returned to the browser or stored with imported literature.

#### Scenario: New Zotero item

- **WHEN** an administrator imports a selected top-level bibliographic item
- **THEN** Zotero fields are mapped to canonical metadata
- **AND** the item key, library ID, and provider version are stored in an external reference
- **AND** the metadata status is needs review

#### Scenario: Reimported Zotero item

- **WHEN** an item with the same provider, library, and item key is imported again
- **THEN** the existing external reference and literature record are reused
- **AND** no duplicate canonical literature record is created

### Requirement: Only published literature enters Agent context

The system SHALL expose only explicitly published canonical literature through MCP read and download tools.

#### Scenario: Metadata-only import

- **WHEN** a Zotero record is imported without a successfully stored PDF and remains pending
- **THEN** it may appear in the authenticated review library
- **AND** it does not appear in MCP list/get/download results

#### Scenario: Successful PDF ingestion

- **WHEN** a valid PDF is successfully stored and registered through an ingestion entry point
- **THEN** MCP read tools may expose its metadata
- **AND** the download tool succeeds only when an uploaded PDF is attached
