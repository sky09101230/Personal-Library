## ADDED Requirements

### Requirement: DOI selection is evidence ordered
The system SHALL search DOI candidates from extracted PDF page text before raw PDF bytes and SHALL prefer page 1, then page 2, then other scanned pages.

#### Scenario: Title-page DOI wins over a reference DOI
- **WHEN** page 1 contains a DOI and a later scanned location contains another DOI
- **THEN** the page 1 DOI is selected and its page source is recorded

#### Scenario: Raw bytes are only a fallback
- **WHEN** scanned page text contains no DOI but raw PDF bytes contain one
- **THEN** the raw-byte DOI may be selected and its source is recorded as a fallback

### Requirement: DOI resolver returns the primary BibTeX record
For a selected normalized DOI, the system SHALL request BibTeX over HTTPS content negotiation and SHALL parse the returned entry without executing its content.

#### Scenario: Valid BibTeX is parsed
- **WHEN** the DOI resolver returns a valid `application/x-bibtex` record whose DOI matches the selected DOI
- **THEN** the system maps its title, authors, journal or book title, year, DOI, keywords, and abstract into structured metadata

#### Scenario: BibTeX DOI conflicts
- **WHEN** the parsed BibTeX DOI differs from the selected PDF DOI
- **THEN** the document is marked as a metadata conflict and is not automatically verified

### Requirement: Missing BibTeX fields are enriched from the same DOI
The system SHALL use the Crossref work for the same DOI only to fill missing BibTeX metadata fields and to corroborate identifiers and titles.

#### Scenario: Crossref supplies a missing abstract
- **WHEN** valid BibTeX has no abstract and the same Crossref work has a deposited abstract
- **THEN** the canonical abstract is populated from Crossref and the evidence records `crossref` as the abstract source

#### Scenario: BibTeX field is not overwritten
- **WHEN** both BibTeX and Crossref provide a non-empty metadata field
- **THEN** the canonical field uses the BibTeX value unless identifier or title validation identifies a conflict

### Requirement: Provider evidence remains traceable and bounded
The system SHALL store bounded BibTeX and Crossref evidence with field provenance in existing evidence storage and SHALL NOT publish a document as a side effect of metadata resolution.

#### Scenario: Enriched BibTeX is retained
- **WHEN** Crossref fills a missing BibTeX abstract
- **THEN** evidence contains the original BibTeX, an enriched BibTeX representation, and the abstract source without changing publication status

### Requirement: External metadata failures do not fail file upload
The system SHALL treat DOI resolver and Crossref failures as recoverable metadata resolution failures and SHALL retain exact-DOI Crossref-only compatibility when BibTeX is unavailable.

#### Scenario: Resolver fails but Crossref succeeds
- **WHEN** BibTeX retrieval or parsing fails and Crossref returns a matching work
- **THEN** the existing Crossref-only metadata path is used and the failure is recorded in evidence

#### Scenario: Both providers fail
- **WHEN** neither BibTeX nor Crossref returns usable matching metadata
- **THEN** the PDF upload remains stored and the document remains pending review rather than raising the provider error to the upload transaction
