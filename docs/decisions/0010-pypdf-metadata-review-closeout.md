# 0010: Keep pypdf for metadata review and make bulk confirmation risk-aware

## Status

Accepted

## Context

The DeepSeek metadata flow needs page-labelled text and stable verbatim evidence more than full document reconstruction. A read-only A/B test compared the current pypdf packet with Docling output on three representative digital PDFs: a normal paper, a paper with prior title/abstract evidence warnings, and the twenty-second review record with no abstract.

Both paths produced the same titles, authors, DOIs, and abstracts; Docling did not recover the missing abstract. Across the three files, pypdf parsing took 1.32 seconds and produced one live evidence warning, while Docling took 52.76 seconds and produced six warnings. Docling also increased the bounded model input from about 55,000 to 188,000 characters because layout normalization changed text used by exact quote validation.

The remaining uploader cost is therefore review triage, not PDF parsing quality: warning-free complete proposals and warning-bearing or incomplete proposals currently share the same bulk surface.

## Decision

- Keep pypdf as the production PDF text source for DeepSeek metadata proposals.
- Do not add Docling as a dependency, production parser, or implicit fallback in this workflow.
- Define a bulk-safe proposal as succeeded, locally warning-free, and complete for title, named author, publication year, and either DOI or journal.
- Preselect bulk-safe proposals on the current queue page, but require an explicit uploader submission and confirmation.
- Require all other proposals to be reviewed and edited individually.
- Enforce bulk safety on the server as well as in the template.
- Keep metadata confirmation independent from Agent publication.

## Consequences

The common review path becomes a single page-level confirmation without weakening provenance or publication controls. Risky proposals remain available instead of being discarded, but cannot bypass evidence review through a crafted bulk request. Scanned or text-empty PDFs are outside this decision and require a separate benchmark before any OCR fallback is introduced.
