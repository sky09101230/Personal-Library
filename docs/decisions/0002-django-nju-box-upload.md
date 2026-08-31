# ADR-0002: Django application for NJU Box upload

- Status: Accepted
- Date: 2026-08-05

## Context

The first operational workflow is uploading research files to NJU Box. The architecture assigns NJU Box to file storage and keeps user workflows in the PLAB web application.

## Decision

Use one Django project with a `box_upload` app. `PLAB Literature` is an encrypted NJU Box library, which Seafile WebDAV does not expose. The app therefore uses the NJU Box Web API, unlocks the repository for the current upload, requests an upload link, and uploads the file.

The first version accepts one file and writes it to the configured repository and `PLAB Literature` directory. The user enters a personal Web API Token and the library password for each upload. Neither credential is saved in `.env`, a database, or the browser session.

Each upload is stored as an `UploadedDocument` record with its uploader, original filename, remote path, size, timestamp, and SHA-256. A `CanonicalDocument` has a unique SHA-256; exact duplicates create another upload record but reuse the canonical document. Future indexing operates on canonical documents only.

## Consequences

- Future workflows can be added as Django apps without changing the upload boundary.
- The uploading user's personal NJU Box account needs write access to the target directory.
- Title, DOI, year, possible-duplicate review, and vector indexing are reserved for later ingestion work; this change does not infer them from PDFs.
- `is_staff=True` users manage database metadata through Django Admin. Deleting an `UploadedDocument` only removes its local metadata record; NJU Box files are deliberately not deleted by this operation.
- Per-user attribution and approval workflow will be added only when the business database is introduced.
