## ADDED Requirements

### Requirement: DOI selection distinguishes publications from related datasets
When multiple PDF DOI candidates have matching titles, the system SHALL prefer a candidate whose resolved metadata identifies a journal or conference publication over a same-title candidate without a publication container.

#### Scenario: Article and dataset share a title
- **WHEN** a PDF contains a journal article DOI and a research dataset DOI whose resolved titles both match the PDF title
- **THEN** the system selects the journal article DOI
- **AND** records the compared candidates and publication-container evidence

### Requirement: Generated PDF titles are not metadata evidence
The system SHALL treat known generated PDF title placeholders as missing metadata rather than authoritative title evidence.

#### Scenario: Placeholder can be replaced from the first page
- **WHEN** the embedded PDF title is `untitled` or another recognized generated placeholder and a title can be extracted from the first page
- **THEN** the extracted first-page title is used for DOI selection and title validation

#### Scenario: Placeholder cannot be replaced
- **WHEN** the embedded PDF title is a recognized generated placeholder and no usable first-page title can be extracted
- **THEN** the PDF title evidence remains empty
- **AND** the placeholder does not trigger a title conflict or populate canonical metadata
