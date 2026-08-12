# Design

## Context

`CanonicalDocument` already provides checksum deduplication and is referenced by upload and MCP code. A rename would add migration risk without improving the user-visible contract, so this change keeps the model name and changes its semantics to "canonical literature". `UploadedDocument` remains the file/upload record.

## Data model

`CanonicalDocument` stores canonical metadata and its review/publication state. Its checksum becomes nullable so Zotero metadata can exist before a PDF is attached. JSON fields retain structured authors, identifiers, three tag sources, evidence, and conflicting candidates without prematurely normalizing single-use tables.

`ExternalReference` maps a canonical record to `(provider, library_id, external_item_id)` and stores the provider version. This is the future incremental-sync anchor, but no recurring sync is implemented now.

## PDF resolution

1. Compute SHA-256 and upload the original PDF unchanged.
2. Extract embedded PDF metadata and text from at most the first two pages with pypdf; also scan bytes/text for a DOI.
3. If no DOI is found, preserve evidence and mark the record `incomplete`.
4. If a DOI is found, fetch that exact Crossref work. Crossref failure leaves the record `needs_review` and never fails the file upload.
5. If Crossref returns the DOI, map its canonical fields. A strong title disagreement becomes `conflict`; otherwise the result is `verified`.
6. Publication remains an explicit admin action through `index_status=published`.

The resolver fills an empty canonical record but does not overwrite existing metadata for an exact duplicate upload.

## Zotero import

The user supplies library type, library ID, optional collection key, and a request-scoped API key. The importer reads top-level items from Zotero Web API v3, ignores notes and attachments, maps Zotero fields into the canonical schema, deduplicates first by external reference and then normalized DOI, and stores the Zotero item version. Imported metadata is `needs_review` because Zotero content is structured but not authoritative validation.

Existing non-empty canonical fields are not silently overwritten. Provider values and provenance remain available in `metadata_evidence`.

## Visibility

The authenticated web library is the review workspace and can show pending records. MCP list/get/download queries require both an uploaded file status where relevant and canonical `index_status=published`. This enforces the repository rule that unpublished content must not enter Agent context.

## Failure handling

- PDF parsing and Crossref failures never roll back a successful NJU Box upload.
- Zotero network or schema failures abort the import request and show a user-facing error; API keys are not logged or stored.
- Exact duplicate files reuse their existing canonical record and metadata.
