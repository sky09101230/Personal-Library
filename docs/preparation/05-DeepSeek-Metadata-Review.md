# DeepSeek metadata review preparation

## Purpose

DeepSeek prepares structured bibliographic candidates so an uploader reviews a comparison form instead of manually entering every field. The API is not an authoritative metadata source and cannot verify or publish a record by itself.

## Required environment

```text
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT=30
```

`DEEPSEEK_API_KEY` is read only by the server worker. It must not be submitted through a browser form, stored in the database, logged, or committed.

## Data sent to DeepSeek

The worker sends a bounded JSON evidence packet containing:

- current canonical fields;
- deterministic Crossref/Zotero/PDF evidence already stored for the record;
- at most the first two and last two extracted PDF pages, with page numbers and per-page text limits.

The packet excludes PDF bytes, NJU Box URLs and paths, credentials, uploader identity, and unrelated full text. The database stores the bounded packet and a fingerprint so a proposal can be audited without exposing secrets.

## Runtime

Upload requests enqueue work and never wait for DeepSeek. Run one worker process for the internal deployment:

```powershell
python manage.py run_metadata_worker
```

For a bounded one-shot run during local testing:

```powershell
python manage.py run_metadata_worker --once --max-jobs 10
```

All automated tests mock the API. A real API call is an explicit deployment smoke test and requires a configured account and approval to send the bounded evidence packet.

## Failure boundary

Empty, truncated, malformed, filtered, timed-out, or schema-invalid responses are stored as failed proposals. Existing canonical metadata, upload status, and `index_status` remain unchanged. One retry is allowed only for transient transport or empty-output failures.
