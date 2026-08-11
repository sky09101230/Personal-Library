# Change: Upgrade literature ingestion

## Why

The current literature area treats an uploaded file as the primary record. It only stores a title, DOI, year, and a checksum-backed upload, so it cannot represent Zotero-only literature, distinguish authoritative metadata from extracted guesses, or keep unpublished records out of Agent context.

## What Changes

- Evolve `CanonicalDocument` into the canonical literature record while retaining its database identity for compatibility.
- Add metadata status, source, confidence, evidence, candidates, authors, journal, abstract, identifiers, and source-separated tags.
- Resolve PDF metadata conservatively: extract deterministic evidence, use an exact DOI with Crossref, and send uncertain or conflicting results to review.
- Add a one-way Zotero Web API v3 metadata importer and stable external references without storing API keys.
- Make the library list canonical literature rather than upload rows.
- Expose only explicitly published literature through the MCP Agent tools.

## Non-goals

- Claiming that PDF metadata can be fully correct without review.
- DeepSeek-based generation or reranking in this slice.
- GROBID deployment, OCR, Zotero OAuth, attachment download, incremental sync, or bidirectional sync.
- Automatic publication after metadata resolution.

## Impact

- A database migration adds literature metadata and external-reference fields.
- Upload handling gains best-effort local PDF extraction and Crossref resolution.
- MCP literature IDs become canonical literature IDs; downloads select an attached uploaded PDF.
- The Zotero API key is request-scoped and is never persisted.
