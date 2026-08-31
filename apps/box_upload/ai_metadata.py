import hashlib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .metadata import DOI_PATTERN, extract_pdf_evidence, normalize_doi


PROMPT_VERSION = "plab-metadata-v1"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
MAX_PAGE_TEXT = 6000
MAX_AUTHORS = 100
MAX_TAGS = 30


class DeepSeekProposalError(Exception):
    def __init__(self, code, message, *, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProposalValidationError(Exception):
    pass


def deepseek_configured():
    return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())


def build_evidence_packet(canonical, uploaded_file=None):
    pdf_evidence = dict((canonical.metadata_evidence or {}).get("pdf") or {})
    if uploaded_file is not None:
        extracted = extract_pdf_evidence(uploaded_file)
        pdf_evidence = {**pdf_evidence, **extracted}

    pages = []
    for page in pdf_evidence.get("pages") or []:
        if not isinstance(page, dict):
            continue
        try:
            number = int(page.get("number"))
        except (TypeError, ValueError):
            continue
        text = _clean_text(page.get("text"))[:MAX_PAGE_TEXT]
        if text:
            pages.append({"number": number, "text": text})

    provider_evidence = {}
    for key in ("crossref", "zotero"):
        value = (canonical.metadata_evidence or {}).get(key)
        if value:
            provider_evidence[key] = value

    return {
        "canonical": canonical_metadata_snapshot(canonical),
        "provider_evidence": provider_evidence,
        "existing_candidates": canonical.metadata_candidates or {},
        "pdf": {
            "doi": pdf_evidence.get("doi"),
            "title": pdf_evidence.get("title"),
            "authors": pdf_evidence.get("authors") or [],
            "page_numbers_scanned": [page["number"] for page in pages],
            "pages": pages[:4],
        },
    }


def canonical_metadata_snapshot(canonical):
    return {
        "title": canonical.title,
        "authors": canonical.authors,
        "abstract": canonical.abstract,
        "journal": canonical.journal,
        "publication_year": canonical.publication_year,
        "doi": canonical.doi,
        "identifiers": canonical.identifiers,
        "source_tags": canonical.source_tags,
        "ai_tags": canonical.ai_tags,
        "metadata_source": canonical.metadata_source,
        "metadata_status": canonical.metadata_status,
    }


def evidence_fingerprint(packet):
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_metadata_proposal(payload, packet):
    if not isinstance(payload, dict):
        raise ProposalValidationError("DeepSeek metadata proposal must be a JSON object.")
    metadata = payload.get("metadata", payload)
    if not isinstance(metadata, dict):
        raise ProposalValidationError("The metadata property must be a JSON object.")

    title = _bounded_string(metadata.get("title"), 500, "title")
    abstract = _bounded_string(metadata.get("abstract"), 20000, "abstract")
    journal = _bounded_string(metadata.get("journal"), 500, "journal")
    doi = normalize_doi(_bounded_string(metadata.get("doi"), 255, "doi"))
    if doi and DOI_PATTERN.fullmatch(doi) is None:
        raise ProposalValidationError("The proposed DOI has an invalid format.")

    publication_year = metadata.get("publication_year")
    if publication_year in (None, ""):
        publication_year = None
    else:
        try:
            publication_year = int(publication_year)
        except (TypeError, ValueError) as exc:
            raise ProposalValidationError("The proposed publication year is invalid.") from exc
        if publication_year < 1800 or publication_year > 2100:
            raise ProposalValidationError("The proposed publication year is outside the accepted range.")

    authors = _normalize_authors(metadata.get("authors"))
    tags = _normalize_tags(metadata.get("keywords") or metadata.get("ai_tags"))
    confidence = _normalize_confidence(payload.get("confidence") or metadata.get("confidence"))
    field_evidence, warnings = _validate_field_evidence(
        payload.get("evidence") or metadata.get("evidence") or {},
        packet,
    )
    for warning in payload.get("warnings") or []:
        if isinstance(warning, str) and warning.strip():
            warnings.append(warning.strip()[:500])
    if not title:
        warnings.append("缺少标题。")
    if not authors:
        warnings.append("缺少作者。")

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "journal": journal,
        "publication_year": publication_year,
        "doi": doi,
        "ai_tags": tags,
        "field_confidence": confidence,
        "field_evidence": field_evidence,
    }, _deduplicate(warnings)


def generate_deepseek_proposal(packet, request_func=None):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise DeepSeekProposalError("disabled", "DeepSeek API key is not configured.")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.netloc:
        raise DeepSeekProposalError("invalid_configuration", "DeepSeek base URL must use HTTPS.")
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    try:
        timeout = max(1, int(os.environ.get("DEEPSEEK_TIMEOUT", "30")))
    except ValueError as exc:
        raise DeepSeekProposalError("invalid_configuration", "DeepSeek timeout must be an integer.") from exc

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": "Evidence JSON:\n" + json.dumps(packet, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 4096,
    }
    request_func = request_func or _post_json
    last_error = None
    for attempt in range(2):
        try:
            response = request_func(
                f"{base_url}/chat/completions",
                body,
                api_key,
                timeout,
            )
            content, finish_reason, returned_model = _completion_content(response)
            if finish_reason != "stop":
                code = "truncated" if finish_reason == "length" else f"finish_{finish_reason or 'unknown'}"
                raise DeepSeekProposalError(code, "DeepSeek did not complete the metadata response.")
            if not content.strip():
                raise DeepSeekProposalError("empty_output", "DeepSeek returned an empty response.", retryable=True)
            try:
                raw_proposal = json.loads(content)
            except json.JSONDecodeError as exc:
                raise DeepSeekProposalError("invalid_json", "DeepSeek returned malformed JSON.") from exc
            proposal, warnings = validate_metadata_proposal(raw_proposal, packet)
            return {
                "proposal": proposal,
                "warnings": warnings,
                "model": returned_model or model,
                "prompt_version": PROMPT_VERSION,
                "attempt_count": attempt + 1,
            }
        except DeepSeekProposalError as exc:
            last_error = exc
            if not exc.retryable or attempt == 1:
                raise
    raise last_error


def _post_json(url, body, api_key, timeout):
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        retryable = exc.code == 429 or exc.code >= 500
        raise DeepSeekProposalError(f"http_{exc.code}", "DeepSeek API request failed.", retryable=retryable) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise DeepSeekProposalError("transport_error", "Could not connect to DeepSeek.", retryable=True) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeepSeekProposalError("invalid_response", "DeepSeek returned an invalid response.") from exc


def _completion_content(response):
    try:
        choice = response["choices"][0]
        return choice["message"].get("content") or "", choice.get("finish_reason"), response.get("model", "")
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekProposalError("invalid_response", "DeepSeek returned an invalid completion object.") from exc


def _system_prompt():
    return """Extract bibliographic metadata only from the supplied evidence. Return JSON and do not use outside knowledge.
JSON example:
{
  "metadata": {
    "title": "",
    "authors": [{"name": "", "orcid": ""}],
    "abstract": "",
    "journal": "",
    "publication_year": null,
    "doi": "",
    "keywords": []
  },
  "confidence": {"title": 0.0, "authors": 0.0, "abstract": 0.0, "journal": 0.0, "publication_year": 0.0, "doi": 0.0},
  "evidence": {"title": [{"source": "pdf_page", "page": 1, "quote": ""}]},
  "warnings": []
}
For unknown values use an empty string, empty list, or null. Evidence quotes must occur verbatim in the supplied page text."""


def _validate_field_evidence(evidence, packet):
    if not isinstance(evidence, dict):
        raise ProposalValidationError("The evidence property must be a JSON object.")
    pages = {page["number"]: _normalize_for_match(page["text"]) for page in packet.get("pdf", {}).get("pages", [])}
    normalized = {}
    warnings = []
    for field, entries in evidence.items():
        if not isinstance(field, str) or not isinstance(entries, list):
            continue
        accepted = []
        for entry in entries[:10]:
            if not isinstance(entry, dict):
                continue
            source = _bounded_string(entry.get("source"), 64, "evidence source") or "unknown"
            quote = _bounded_string(entry.get("quote"), 500, "evidence quote")
            page = entry.get("page")
            if source == "pdf_page" and quote:
                try:
                    page = int(page)
                except (TypeError, ValueError):
                    warnings.append(f"{field} 的 PDF 证据缺少有效页码。")
                    continue
                if _normalize_for_match(quote) not in pages.get(page, ""):
                    warnings.append(f"{field} 的第 {page} 页引文未在输入文本中找到。")
                    continue
            accepted.append({"source": source, "page": page, "quote": quote})
        if accepted:
            normalized[field] = accepted
    return normalized, warnings


def _normalize_authors(value):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ProposalValidationError("The proposed authors must be a list.")
    result = []
    for author in value[:MAX_AUTHORS]:
        if isinstance(author, str):
            name = _clean_text(author)[:300]
            record = {"name": name} if name else None
        elif isinstance(author, dict):
            name = _bounded_string(author.get("name"), 300, "author name")
            record = {"name": name} if name else None
            if record and author.get("orcid"):
                record["orcid"] = _bounded_string(author.get("orcid"), 64, "ORCID").removeprefix("https://orcid.org/")
        else:
            raise ProposalValidationError("Each proposed author must be a string or object.")
        if record:
            result.append(record)
    return result


def _normalize_tags(value):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ProposalValidationError("The proposed keywords must be a list.")
    return _deduplicate([_clean_text(tag)[:100] for tag in value[:MAX_TAGS] if isinstance(tag, str) and _clean_text(tag)])


def _normalize_confidence(value):
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ProposalValidationError("The confidence property must be a JSON object.")
    result = {}
    for key, score in value.items():
        if not isinstance(key, str):
            continue
        try:
            result[key] = min(1.0, max(0.0, float(score)))
        except (TypeError, ValueError):
            continue
    return result


def _bounded_string(value, limit, field):
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ProposalValidationError(f"The proposed {field} must be text.")
    return _clean_text(value)[:limit]


def _clean_text(value):
    return " ".join(str(value or "").split())


def _normalize_for_match(value):
    return " ".join(re.findall(r"\w+", str(value or "").lower()))


def _deduplicate(values):
    return list(dict.fromkeys(value for value in values if value))
