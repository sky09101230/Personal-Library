from dataclasses import dataclass, field
import json
import os
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .types import MinerURawResult, MinerUSegmentResult, segment_page_ranges


DEFAULT_BASE_URL = "https://mineru.net/api/v4"
_WAITING_STATES = {"waiting-file", "pending", "running", "converting"}


class MinerUError(RuntimeError):
    code = "mineru_failed"

    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class MinerUConfigurationError(MinerUError):
    code = "mineru_configuration"


class MinerUAPIError(MinerUError):
    code = "mineru_api"


class MinerUTimeoutError(MinerUError):
    code = "mineru_timeout"


@dataclass(frozen=True, slots=True)
class MinerUConfig:
    base_url: str
    token: str = field(repr=False)
    model_version: str
    request_timeout: int
    poll_interval: float
    poll_timeout: float
    segment_pages: int
    result_max_bytes: int

    @classmethod
    def from_environment(cls):
        token = os.environ.get("MINERU_API_TOKEN", "").strip()
        if not token:
            raise MinerUConfigurationError("MINERU_API_TOKEN is not configured.")
        base_url = os.environ.get("MINERU_API_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.netloc:
            raise MinerUConfigurationError("MINERU_API_BASE_URL must use HTTPS.")
        model_version = os.environ.get("MINERU_MODEL_VERSION", "vlm").strip() or "vlm"
        if model_version not in {"vlm", "pipeline"}:
            raise MinerUConfigurationError("MINERU_MODEL_VERSION must be vlm or pipeline.")
        try:
            return cls(
                base_url=base_url,
                token=token,
                model_version=model_version,
                request_timeout=max(1, int(os.environ.get("MINERU_REQUEST_TIMEOUT", "120"))),
                poll_interval=max(0, float(os.environ.get("MINERU_POLL_INTERVAL", "5"))),
                poll_timeout=max(1, float(os.environ.get("MINERU_POLL_TIMEOUT", "3600"))),
                segment_pages=int(os.environ.get("MINERU_SEGMENT_PAGES", "200")),
                result_max_bytes=max(
                    1,
                    int(os.environ.get("MINERU_RESULT_MAX_BYTES", str(512 * 1024 * 1024))),
                ),
            )
        except ValueError as exc:
            raise MinerUConfigurationError("MinerU numeric configuration is invalid.") from exc

    def __post_init__(self):
        if not 1 <= self.segment_pages <= 200:
            raise MinerUConfigurationError("MINERU_SEGMENT_PAGES must be between 1 and 200.")


class MinerUClient:
    def __init__(
        self,
        config=None,
        *,
        request_json=None,
        put_bytes=None,
        request_bytes=None,
        sleep_func=sleep,
        monotonic_func=monotonic,
    ):
        self.config = config or MinerUConfig.from_environment()
        self._request_json = request_json or _request_json
        self._put_bytes = put_bytes or _put_bytes
        self._request_bytes = request_bytes or _request_bytes
        self._sleep = sleep_func
        self._monotonic = monotonic_func

    def parse_pdf(self, file_obj, *, page_count, data_id):
        started_at = self._monotonic()
        page_ranges = segment_page_ranges(
            page_count,
            segment_pages=self.config.segment_pages,
        )
        source_bytes = _read_source(file_obj)
        file_specs = [
            {
                "name": f"plab-{data_id}-part-{index + 1:03d}.pdf",
                "data_id": f"{data_id}-part-{index + 1:03d}",
                "is_ocr": False,
                "page_ranges": page_range.expression,
            }
            for index, page_range in enumerate(page_ranges)
        ]
        allocation = self._api_json(
            "POST",
            f"{self.config.base_url}/file-urls/batch",
            body={
                "files": file_specs,
                "model_version": self.config.model_version,
                "enable_formula": True,
                "enable_table": True,
            },
        )
        batch_id = _require_text(allocation.get("batch_id"), "batch_id")
        upload_urls = allocation.get("file_urls")
        if not isinstance(upload_urls, list) or len(upload_urls) != len(file_specs):
            raise MinerUAPIError("MinerU returned an invalid upload URL list.")
        for upload_url in upload_urls:
            self._retry(
                lambda: self._put_bytes(
                    _require_https_url(upload_url, "upload URL"),
                    source_bytes,
                    self.config.request_timeout,
                )
            )

        results = self._poll_batch(batch_id, file_specs)
        segments = []
        total_result_bytes = 0
        for index, (page_range, file_spec) in enumerate(zip(page_ranges, file_specs, strict=True)):
            item = results[file_spec["data_id"]]
            result_url = _require_https_url(item.get("full_zip_url"), "result URL")
            archive_bytes = self._retry(
                lambda: self._request_bytes(
                    result_url,
                    self.config.request_timeout,
                    self.config.result_max_bytes,
                )
            )
            total_result_bytes += len(archive_bytes)
            if total_result_bytes > self.config.result_max_bytes:
                raise MinerUAPIError("MinerU result archive exceeds the configured size limit.")
            segments.append(
                MinerUSegmentResult(
                    index=index,
                    page_range=page_range,
                    data_id=file_spec["data_id"],
                    archive_bytes=archive_bytes,
                    result_url=result_url,
                )
            )
        return MinerURawResult(
            batch_id=batch_id,
            model_version=self.config.model_version,
            page_count=int(page_count),
            segments=tuple(segments),
            runtime_info={
                "provider": "mineru",
                "batch_id": batch_id,
                "segment_count": len(segments),
                "page_ranges": [item.expression for item in page_ranges],
                "duration_ms": round((self._monotonic() - started_at) * 1000),
            },
        )

    def _poll_batch(self, batch_id, file_specs):
        deadline = self._monotonic() + self.config.poll_timeout
        expected_ids = {item["data_id"] for item in file_specs}
        while True:
            payload = self._api_json(
                "GET",
                f"{self.config.base_url}/extract-results/batch/{batch_id}",
            )
            items = payload.get("extract_result", [])
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                raise MinerUAPIError("MinerU returned an invalid batch result.")
            by_id = {
                item.get("data_id"): item
                for item in items
                if isinstance(item, dict) and item.get("data_id") in expected_ids
            }
            failed = next((item for item in by_id.values() if item.get("state") == "failed"), None)
            if failed is not None:
                raise MinerUAPIError("MinerU failed to parse one document segment.")
            if expected_ids == set(by_id) and all(item.get("state") == "done" for item in by_id.values()):
                return by_id
            unknown_states = {
                item.get("state")
                for item in by_id.values()
                if item.get("state") not in _WAITING_STATES | {"done"}
            }
            if unknown_states:
                raise MinerUAPIError("MinerU returned an unsupported task state.")
            if self._monotonic() >= deadline:
                raise MinerUTimeoutError("MinerU batch polling timed out.")
            self._sleep(self.config.poll_interval)

    def _api_json(self, method, url, *, body=None):
        payload = self._retry(
            lambda: self._request_json(
                method,
                url,
                {
                    "Authorization": f"Bearer {self.config.token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                body,
                self.config.request_timeout,
            )
        )
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise MinerUAPIError("MinerU API returned an unsuccessful response.")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MinerUAPIError("MinerU API response is missing data.")
        return data

    def _retry(self, operation):
        last_error = None
        for attempt in range(2):
            try:
                return operation()
            except MinerUError as exc:
                last_error = exc
                if not exc.retryable or attempt == 1:
                    raise
        raise last_error


def _read_source(file_obj):
    file_obj.seek(0)
    content = file_obj.read()
    file_obj.seek(0)
    if not isinstance(content, bytes) or not content:
        raise MinerUAPIError("Source PDF is empty or unreadable.")
    return content


def _require_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise MinerUAPIError(f"MinerU response is missing {field_name}.")
    return value


def _require_https_url(value, field_name):
    value = _require_text(value, field_name)
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc:
        raise MinerUAPIError(f"MinerU {field_name} must use HTTPS.")
    return value


def _request_json(method, url, headers, body, timeout):
    request = Request(
        url,
        data=(json.dumps(body).encode("utf-8") if body is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise MinerUAPIError(
            "MinerU API HTTP request failed.",
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise MinerUAPIError("MinerU API transport failed.", retryable=True) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MinerUAPIError("MinerU API returned invalid JSON.") from exc


def _put_bytes(url, content, timeout):
    request = Request(url, data=content, method="PUT")
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise MinerUAPIError(
                    "MinerU pre-signed upload failed.",
                    retryable=response.status == 429 or response.status >= 500,
                )
    except HTTPError as exc:
        raise MinerUAPIError(
            "MinerU pre-signed upload failed.",
            retryable=exc.code == 429 or exc.code >= 500,
        ) from None
    except (TimeoutError, URLError, OSError) as exc:
        raise MinerUAPIError("MinerU upload transport failed.", retryable=True) from None


def _request_bytes(url, timeout, max_bytes):
    request = Request(url, headers={"Accept": "application/zip"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise MinerUAPIError(
            "MinerU result download failed.",
            retryable=exc.code == 429 or exc.code >= 500,
        ) from None
    except (TimeoutError, URLError, OSError) as exc:
        raise MinerUAPIError("MinerU result transport failed.", retryable=True) from None
    if len(content) > max_bytes:
        raise MinerUAPIError("MinerU result archive exceeds the configured size limit.")
    return content
