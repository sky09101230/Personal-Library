## Purpose

让一次 Zotero 导入在保留现有 metadata 语义的同时，安全地获取 Zotero File Storage 中真正托管的 PDF，并将每个附件结果明确反馈给用户。

## ADDED Requirements

### Requirement: Only Zotero-hosted PDF files are eligible
The system SHALL inspect child attachments for each imported bibliographic item and SHALL download only attachments whose link mode is `imported_file` and content type is `application/pdf`.

#### Scenario: Hosted PDF attachment
- **WHEN** a child attachment is an `imported_file` with `application/pdf` content type
- **THEN** the system attempts to download its file from the Zotero item file endpoint

#### Scenario: Unsupported attachment
- **WHEN** a child is a web snapshot, URL attachment, non-PDF attachment, `linked_file`, note, or annotation
- **THEN** the system does not download or store that child

### Requirement: Imported PDFs attach to the canonical literature record
The system SHALL store each successfully downloaded PDF through the configured literature storage and create an uploaded-document record associated with the same canonical literature record and the importing administrator.

#### Scenario: Successful PDF import
- **WHEN** an eligible Zotero PDF passes PDF signature validation and storage succeeds
- **THEN** the library shows the PDF on the canonical literature record and permits the normal preview and download operations

#### Scenario: Multiple hosted PDFs
- **WHEN** a Zotero item contains multiple eligible hosted PDF attachments
- **THEN** the system attempts each attachment and associates every successful distinct PDF with the same canonical literature record

### Requirement: Attachment failure does not roll back metadata
The system SHALL isolate attachment-list, download, validation, and storage failures from metadata import and SHALL continue processing later items and attachments.

#### Scenario: One PDF fails
- **WHEN** one eligible PDF cannot be downloaded, validated, or stored
- **THEN** the canonical metadata remains imported, later work continues, and the progress stream and final result report the failure

### Requirement: Reimport does not duplicate identical PDF storage
The system SHALL compare the downloaded PDF SHA-256 with existing uploads on the same canonical literature record before writing a new storage object.

#### Scenario: Identical PDF already attached
- **WHEN** a reimport downloads a PDF whose SHA-256 already exists on the canonical literature record
- **THEN** the system reuses the existing uploaded document and does not write another storage object

### Requirement: Zotero credentials remain request-scoped
The system SHALL use the submitted Zotero API key for child-item and file GET requests without persisting it in metadata, upload records, logs, or configuration.

#### Scenario: Attachment import completes
- **WHEN** hosted PDFs are imported or fail
- **THEN** no Zotero API key is stored with the resulting records or failure report
