# 0011: Proxy unpublished PDFs for authenticated inline viewing

## Status

Accepted

## Context

Uploaded PDFs are stored in an encrypted NJU Box repository. The existing download action generates a temporary Box link and redirects the browser, which is appropriate for saving files but cannot reliably open them inline and exposes the temporary URL to the client. Metadata reviewers need to inspect the PDF without leaving the web workflow.

Browser PDF viewers use byte ranges for incremental loading and seeking. Reading a complete paper into Django memory for every preview would be slow and wasteful, while a custom PDF.js interface is unnecessary for the current requirement.

## Decision

- Add a login-protected application endpoint that streams an uploaded PDF with `Content-Disposition: inline`.
- Generate and consume the temporary NJU Box download link only on the server.
- Forward one validated `bytes` range and propagate partial-content headers needed by native browser PDF viewers.
- Stream fixed-size chunks and close the upstream response and connection when iteration ends or the client disconnects.
- Reject malformed or multipart ranges before contacting NJU Box.
- Force `application/pdf`, disable MIME sniffing, and use private no-store caching because literature may be unpublished.
- Keep the existing download endpoint and do not persist or cache PDF bytes locally.
- Use Python's existing `http.client` implementation and add no dependency or database migration.

## Consequences

Authenticated users can open PDFs from the library and metadata review pages without seeing Box credentials or temporary URLs. Application bandwidth now carries preview traffic, but range-aware streaming avoids whole-file buffering. A future high-volume deployment may move this proxy to an authorization-aware object gateway, but it must preserve the same unpublished-content boundary.
