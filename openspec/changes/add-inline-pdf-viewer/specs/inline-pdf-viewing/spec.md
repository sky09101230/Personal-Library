## ADDED Requirements

### Requirement: Authenticated users can open PDF attachments inline
The system SHALL provide an authenticated URL that returns an uploaded literature attachment as inline `application/pdf` content.

#### Scenario: User opens an available PDF
- **WHEN** an authenticated user selects “在线打开” for an uploaded PDF
- **THEN** the browser opens the PDF in a new tab using its native PDF viewer
- **AND** the existing download action remains available

#### Scenario: Unauthenticated request
- **WHEN** an unauthenticated client requests the inline PDF URL
- **THEN** the system redirects the client to login without requesting the remote file

### Requirement: Inline viewing keeps NJU Box access server-side
The system SHALL obtain and consume the temporary NJU Box link on the server and SHALL NOT expose credentials or the temporary link in rendered HTML or redirect responses.

#### Scenario: Remote PDF is streamed
- **WHEN** the inline endpoint successfully opens an NJU Box attachment
- **THEN** PDF bytes are streamed through the application response
- **AND** the response uses private no-store caching and MIME-sniffing protection

#### Scenario: Remote PDF cannot be opened
- **WHEN** NJU Box is unavailable or rejects the file request
- **THEN** the system returns a controlled gateway error
- **AND** does not expose credentials or the temporary link

### Requirement: Browser byte ranges are supported safely
The system SHALL forward one valid PDF byte range and propagate the headers required for browser seeking without loading the whole PDF into memory.

#### Scenario: Valid byte range
- **WHEN** the browser requests a single valid `bytes` range and NJU Box returns partial content
- **THEN** the system returns status 206 with the upstream content range and length

#### Scenario: Invalid or multipart range
- **WHEN** the client supplies a malformed or multipart range
- **THEN** the system returns status 416 without contacting NJU Box

### Requirement: Review surfaces expose the inline viewer
The system SHALL show an “在线打开” action for available PDF attachments in the literature library, AI metadata review detail, recent uploads, and upload history.

#### Scenario: Reviewer checks metadata evidence
- **WHEN** a review proposal has an available source upload or canonical PDF attachment
- **THEN** the review detail provides a new-tab inline PDF action
