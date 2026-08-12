## Context

The existing staff-only page posts request-scoped Web API credentials directly into one streaming import. The importer already pages top-level items, filters hosted PDF attachments, spools and hashes bytes, stores them, and isolates attachment failures. Zotero Desktop exposes a read-only Web API-compatible service on fixed loopback port 23119 and returns attachment paths as `file://` URLs.

## Goals / Non-Goals

**Goals:**

- Reuse the current importer and progress stream after an explicit connection/browse step.
- Persist one credential set per administrator without storing plaintext API keys.
- Keep local and Web PDF bytes on the same validation, deduplication, storage, and cleanup path.

**Non-Goals:**

- Read arbitrary browser files, remote users' desktops, snapshots, URL attachments, or `linked_file`.
- Synchronize changes continuously, add background jobs, or write back to Zotero.
- Import nested child collection contents recursively.

## Decisions

### Encrypt one per-user connection with the Django secret

Add a one-to-one connection row containing library type, ID, and a Fernet-encrypted API key. Derive the Fernet key from `SECRET_KEY`; successful validation precedes replacement. Browser storage and plaintext database fields were rejected because either JavaScript or a database read would expose the key.

### Use the existing route as a small action endpoint

The page posts `connect`, `items`, or `import` actions to the existing staff-only route. Connect and items return JSON; import returns the existing NDJSON stream. This avoids new API routing while keeping each response explicit.

### Fetch selected keys through the Web API

Collection browsing uses the saved Web connection. Import posts selected Item Keys, validates and batches them, then feeds their full records into the existing mapper. The server does not trust metadata copied from the browser.

### Probe Zotero Desktop once and prefer its file URL

At import start, make one short loopback probe. For each Web-eligible attachment, request the same attachment key's local `file/view/url`, accept only an absolute local `file://` URL, open it read-only, and pass it through the current spool/hash/PDF validation. Any local failure falls back to Web without including the path in user-visible errors.

## Risks / Trade-offs

- [Changing `SECRET_KEY` makes saved API keys unreadable] → require the administrator to reconnect; do not silently overwrite the row.
- [Django runs on a different host from Zotero Desktop] → the loopback probe fails quickly and Web fallback remains unchanged.
- [A local library is stale relative to Web metadata] → match only the same eligible attachment Item Key and validate PDF content.
- [A large collection produces many checkboxes] → return all top-level items now; add search/pagination only if measured use requires it.

## Migration Plan

Add the connection table and declared encryption dependency, deploy, then connect once per administrator. Rollback removes the browser workflow and local preference; existing imported literature and PDFs remain valid.
