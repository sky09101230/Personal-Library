## 1. Secure streaming

- [x] 1.1 Add a closable NJU Box streaming service that reuses temporary download links, forwards one optional byte range, and never buffers the full PDF.
- [x] 1.2 Add the authenticated inline PDF endpoint with range validation, controlled gateway errors, inline filename, and private security headers.

## 2. Review workflow links

- [x] 2.1 Add the online-open action to the literature library, recent uploads, and upload history while preserving downloads.
- [x] 2.2 Add the online-open action to metadata review detail using the proposal source upload or an available canonical attachment.

## 3. Decision and verification

- [x] 3.1 Record the server-side streaming and confidentiality decision without adding dependencies or migrations.
- [x] 3.2 Add mocked service/view, range, authentication, failure, and rendered-link tests; run focused/full tests, compile checks, migration checks, and strict OpenSpec validation.
