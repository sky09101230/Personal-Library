## Context

`UploadedDocument` stores the original filename and an NJU Box remote path. The existing download view calls `get_download_link()` and redirects the browser to a temporary Seafile/NJU Box URL. That is suitable for saving a file, but it cannot control `Content-Disposition`, exposes the temporary URL to the client, and interrupts metadata review.

Browser-native PDF viewers request byte ranges for seeking and incremental loading. The application therefore needs a streaming response rather than reading the entire PDF into memory or returning an HTML iframe around an attachment response.

## Goals / Non-Goals

**Goals:**

- Open an uploaded PDF in a new browser tab with the native PDF viewer.
- Keep NJU Box credentials and generated download links on the server.
- Forward one valid byte range and the relevant response headers without buffering the whole file.
- Close upstream connections when streaming completes or the client disconnects.
- Preserve the existing authenticated download flow.

**Non-Goals:**

- Build a custom PDF.js interface, annotations, search indexing, or page citations.
- Cache or persist PDF bytes on the application server.
- Change which authenticated users can see the existing literature library.
- Support multipart byte ranges in the first version.

## Decisions

1. Add a dedicated authenticated `view-document` endpoint that returns `application/pdf` with `Content-Disposition: inline`. A redirect cannot reliably override the remote server's attachment header.
2. Reuse `get_download_link()` server-side, then open that HTTPS URL with `http.client`. This matches the existing standard-library NJU Box implementation and adds no dependency.
3. Represent the live upstream response with a small closable stream object. Its iterator reads bounded chunks and always closes both the HTTP response and connection in `finally`.
4. Accept only a single syntactically valid `Range: bytes=...` request. Forward it upstream and propagate status 206, `Content-Range`, `Content-Length`, `Accept-Ranges`, `ETag`, and `Last-Modified` when present. Invalid or multipart ranges return 416 without contacting Box.
5. Force `application/pdf`, use an encoded inline filename, set `X-Content-Type-Options: nosniff`, and use private no-store caching because literature may be unpublished.
6. Display the link in the library, recent uploads, upload history, and AI review detail. Review detail uses the proposal source upload or the first available uploaded attachment.

## Risks / Trade-offs

- [Application bandwidth increases because PDF bytes pass through Django] → Stream bounded chunks and preserve range requests; avoid buffering and caching.
- [A remote connection can remain open after a client disconnect] → Close response and connection in the iterator `finally` block.
- [NJU Box does not honor a range request] → Accept a normal 200 response and let the browser continue; tests cover both 200 and 206 application behavior.
- [Temporary Box failures break viewing] → Return a controlled 502 response without exposing credentials or the temporary URL; downloads remain separately available.
- [Unpublished PDFs could be cached by shared intermediaries] → Send `Cache-Control: private, no-store`.
