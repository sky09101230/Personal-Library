## Purpose

Allow an administrator on a remote browser to attach a PDF stored on that browser's computer to the exact Zotero record selected for import.

## ADDED Requirements

### Requirement: Browser PDF is explicitly bound to one Zotero item
The system SHALL present an optional PDF picker for each browsed Zotero item and SHALL bind the chosen file to that item's server-validated Item Key.

#### Scenario: Administrator chooses a local PDF
- **WHEN** an administrator selects a PDF beside a Zotero item
- **THEN** the item is selected for import and the PDF is submitted for that Item Key

### Requirement: Browser PDF has highest source priority
The system SHALL process a submitted browser PDF before attempting a server-local Zotero Desktop file or Zotero Web file for the same bibliographic item.

#### Scenario: Browser PDF succeeds
- **WHEN** the submitted browser file is a valid PDF and storage succeeds
- **THEN** the PDF is attached to the imported canonical record and no automatic attachment source is needed for that record

#### Scenario: No browser PDF selected
- **WHEN** the selected Zotero item has no submitted browser PDF
- **THEN** the existing server-local and Zotero Web attachment workflow remains available

### Requirement: Browser PDF failure preserves metadata
The system SHALL validate browser files as PDFs, isolate each validation or storage failure, preserve imported metadata, continue later items, and report the failure in progress and final results.

#### Scenario: Invalid browser file
- **WHEN** a submitted file does not have a PDF filename and PDF signature
- **THEN** the metadata remains imported, the file is not stored, and the result reports that item-level PDF failure

### Requirement: Unselected files are rejected
The system SHALL ignore or reject uploaded files whose field does not correspond to an explicitly selected, valid Zotero Item Key.

#### Scenario: Forged file binding
- **WHEN** a request submits a PDF for an Item Key that is not selected
- **THEN** the system does not attach that file to any literature record
