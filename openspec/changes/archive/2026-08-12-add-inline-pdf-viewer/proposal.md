## Why

Reviewers currently have to download a PDF before checking metadata evidence, which interrupts the browser-based review flow. Authenticated users should be able to open an attached PDF in a new browser tab without exposing NJU Box credentials or temporary download URLs.

## What Changes

- Add a login-protected inline PDF endpoint for uploaded literature.
- Stream PDF bytes through the application with `Content-Disposition: inline` and browser-compatible byte-range support.
- Add “在线打开” links to the library, review detail, home, and upload-history surfaces while preserving the existing download action.
- Keep NJU Box credentials and temporary links server-side and return a controlled error when the remote file cannot be opened.

## Capabilities

### New Capabilities
- `inline-pdf-viewing`: Authenticated, range-aware browser viewing of PDF attachments stored in NJU Box.

### Modified Capabilities

None.

## Impact

- Affects NJU Box streaming services, literature views and URLs, four existing templates, tests, and one decision record.
- Does not change database models, publication status, metadata state, or the existing download endpoint.
- Adds no third-party dependency and does not persist PDF bytes locally.
