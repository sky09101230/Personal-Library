"""Small OpenAI-compatible client for paper intelligence.

The client owns transport and configuration only.  Callers validate their own
JSON payloads and evidence claims.
"""

from dataclasses import dataclass
import json
import os
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RETRYABLE_STATUS = {408, 409, 425, 429}


class LLMError(RuntimeError):
    def __init__(self, code, message, *, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class LLMResult:
    content: str
    provider: str
    profile: str
    requested_model: str
    returned_model: str
    finish_reason: str
    usage: dict | None
    attempt_count: int


@dataclass(frozen=True, slots=True)
class LLMConfig:
    base_url: str
    api_key: str
    chat_model: str
    overview_model: str
    vision_model: str = ""
    timeout: float = 30.0
    max_retries: int = 1
    json_mode: bool = True
    vision_enabled: bool = False
    streaming_enabled: bool = False
    profile: str = "paper"


def load_config(*, environ=None):
    environ = os.environ if environ is None else environ
    paper_values = [environ.get(name, "").strip() for name in (
        "PAPER_LLM_BASE_URL", "PAPER_CHAT_MODEL", "PAPER_OVERVIEW_MODEL",
    )]
    paper_configured = any(paper_values) or bool(environ.get("PAPER_LLM_API_KEY", "").strip())
    if paper_configured:
        missing = [name for name, value in zip(
            ("PAPER_LLM_BASE_URL", "PAPER_CHAT_MODEL", "PAPER_OVERVIEW_MODEL"), paper_values
        ) if not value]
        if missing:
            raise LLMError("invalid_configuration", "Paper LLM configuration is incomplete.")
        return _build_config(
            base_url=paper_values[0],
            api_key=environ.get("PAPER_LLM_API_KEY", "").strip(),
            chat_model=paper_values[1],
            overview_model=paper_values[2],
            vision_model=environ.get("PAPER_VISION_MODEL", "").strip(),
            prefix="PAPER_",
            profile="paper",
            environ=environ,
        )
    base = environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    return _build_config(
        base_url=base,
        api_key=environ.get("DEEPSEEK_API_KEY", "").strip(),
        chat_model=environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
        overview_model=environ.get("DEEPSEEK_OVERVIEW_MODEL", "").strip()
        or environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
        prefix="DEEPSEEK_",
        profile="deepseek-legacy",
        environ=environ,
    )


def complete(role, messages, *, output_mode="text", images=None, config=None, request_func=None):
    config = config or load_config()
    model = {"chat": config.chat_model, "overview": config.overview_model, "vision": config.vision_model}.get(role)
    if not model:
        raise LLMError("capability_unavailable", f"LLM role {role} is not configured.")
    if images and (not config.vision_enabled or role != "vision"):
        raise LLMError("capability_unavailable", "Vision capability is not enabled.")
    if output_mode not in {"text", "json"}:
        raise LLMError("invalid_configuration", "Unsupported LLM output mode.")
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 8192}
    if output_mode == "json" and config.json_mode:
        body["response_format"] = {"type": "json_object"}
    if images:
        body["messages"] = _attach_images(messages, images)
    request_func = request_func or _post_json
    last_error = None
    for attempt in range(config.max_retries + 1):
        try:
            payload = request_func(_completion_url(config.base_url), body, config, config.timeout)
            content, finish_reason, returned_model, usage = _read_completion(payload)
            if finish_reason != "stop":
                raise LLMError("truncated" if finish_reason == "length" else "invalid_completion",
                               "LLM did not complete the response.")
            if not content.strip():
                raise LLMError("empty_output", "LLM returned an empty response.", retryable=True)
            if output_mode == "json":
                try:
                    json.loads(content)
                except json.JSONDecodeError as exc:
                    raise LLMError("invalid_json", "LLM returned malformed JSON.") from exc
            return LLMResult(content, config.profile, config.profile, model, returned_model or model,
                             finish_reason, usage, attempt + 1)
        except LLMError as exc:
            last_error = exc
            if not exc.retryable or attempt >= config.max_retries:
                raise
    raise last_error


def _build_config(*, base_url, api_key, chat_model, overview_model, vision_model="", prefix, profile, environ):
    try:
        timeout = max(1.0, float(environ.get(prefix + "LLM_TIMEOUT", environ.get("DEEPSEEK_TIMEOUT", "30"))))
        retries = max(0, min(1, int(environ.get(prefix + "LLM_RETRIES", "1"))))
    except ValueError as exc:
        raise LLMError("invalid_configuration", "LLM timeout or retries is invalid.") from exc
    return LLMConfig(
        base_url=_validate_base_url(base_url), api_key=api_key, chat_model=chat_model,
        overview_model=overview_model, vision_model=vision_model, timeout=timeout,
        max_retries=retries, json_mode=environ.get(prefix + "LLM_JSON_MODE", "true").lower() == "true",
        vision_enabled=bool(vision_model and environ.get(prefix + "LLM_VISION_ENABLED", "true").lower() == "true"),
        streaming_enabled=environ.get(prefix + "LLM_STREAMING_ENABLED", "false").lower() == "true",
        profile=profile,
    )


def _validate_base_url(value):
    parts = urlsplit(value.rstrip("/"))
    if parts.username or parts.password or parts.query or parts.fragment or not parts.netloc:
        raise LLMError("invalid_configuration", "LLM endpoint URL is invalid.")
    if parts.scheme == "https":
        return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    if parts.scheme != "http" or parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise LLMError("invalid_configuration", "LLM endpoint must use HTTPS or loopback HTTP.")
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 80, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise LLMError("invalid_configuration", "LLM loopback endpoint cannot be resolved.") from exc
    if not addresses or any(address[4][0] not in {"127.0.0.1", "::1"} for address in addresses):
        raise LLMError("invalid_configuration", "LLM endpoint is not loopback.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _completion_url(base_url):
    return base_url.rstrip("/") + "/chat/completions"


def _attach_images(messages, images):
    if not images or len(images) > 4:
        raise LLMError("resource_limit", "Too many images for one request.")
    converted = [dict(message) for message in messages]
    last = dict(converted[-1])
    content = list(last.get("content") or []) if isinstance(last.get("content"), list) else [{"type": "text", "text": str(last.get("content", ""))}]
    for image in images:
        if not isinstance(image, dict) or image.get("mime") not in {"image/png", "image/jpeg", "image/webp"}:
            raise LLMError("resource_limit", "Unsupported image input.")
        data = image.get("data", b"")
        if not isinstance(data, bytes) or len(data) > 10 * 1024 * 1024:
            raise LLMError("resource_limit", "Image input exceeds the size limit.")
        import base64
        content.append({"type": "image_url", "image_url": {"url": f"data:{image['mime']};base64,{base64.b64encode(data).decode('ascii')}"}})
    last["content"] = content
    converted[-1] = last
    return converted


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        return None


def _post_json(url, body, config, timeout):
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={
        "Content-Type": "application/json", "Accept": "application/json",
        **({"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}),
    }, method="POST")
    opener = build_opener(ProxyHandler({}) if urlsplit(url).scheme == "http" else ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise LLMError("response_too_large", "LLM response exceeds the size limit.")
            return json.loads(raw)
    except HTTPError as exc:
        retryable = exc.code in RETRYABLE_STATUS or exc.code >= 500
        raise LLMError(f"http_{exc.code}", "LLM request failed.", retryable=retryable) from exc
    except LLMError:
        raise
    except (TimeoutError, URLError, OSError) as exc:
        raise LLMError("transport_error", "Could not connect to the LLM provider.", retryable=True) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMError("invalid_response", "LLM returned an invalid response.") from exc


def _read_completion(response):
    try:
        choice = response["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise TypeError
        usage = response.get("usage")
        return content, choice.get("finish_reason"), response.get("model", ""), usage if isinstance(usage, dict) else None
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("invalid_response", "LLM returned an invalid completion object.") from exc
