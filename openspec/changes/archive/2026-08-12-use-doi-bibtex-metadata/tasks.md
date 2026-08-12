## 1. Preparation and configuration

- [x] 1.1 Document the DOI resolver, BibTeX parser dependency, Crossref enrichment boundary, and configuration before implementation
- [x] 1.2 Add the direct BibTeX parser dependency and DOI resolver setting/example

## 2. Metadata resolution

- [x] 2.1 Select DOI candidates in page-evidence order and record the selected source
- [x] 2.2 Fetch and parse bounded BibTeX through DOI HTTPS content negotiation
- [x] 2.3 Merge missing BibTeX fields from matching Crossref metadata while retaining provenance and Crossref-only fallback
- [x] 2.4 Persist bounded original/enriched BibTeX evidence without changing publication status

## 3. Verification

- [x] 3.1 Add tests for DOI ordering, BibTeX parsing, abstract enrichment, conflicts, and provider fallback
- [x] 3.2 Run focused and full Django tests, then perform a read-only live smoke test with a public DOI
- [x] 3.3 Validate the OpenSpec change and document verified and unverified outcomes
