## ADDED Requirements

### Requirement: Web upload does not infer supplementary material automatically
The system SHALL register newly submitted PDFs from the web upload entry point as primary PDFs without inferring a supplementary role from filenames, embedded titles, or page text.

#### Scenario: PDF contains supplementary wording
- **WHEN** a newly submitted PDF contains `Supplementary Information`, `Supporting Information`, or similar wording
- **THEN** the web upload path processes it as a primary PDF
- **AND** no supplementary relationship is created automatically

#### Scenario: Historical supplementary attachment is read
- **WHEN** an existing upload record is already marked as supplementary material
- **THEN** its stored role and relationship remain unchanged
- **AND** the default literature download continues to prefer a primary PDF
