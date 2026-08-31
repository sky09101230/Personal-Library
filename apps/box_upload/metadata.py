import json
import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import author as split_bibtex_authors
from bibtexparser.customization import convert_to_unicode
from django.conf import settings
from pypdf import PdfReader

from .models import CanonicalDocument


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
TAG_PATTERN = re.compile(r"<[^>]+>")
PDF_PAGE_TEXT_LIMIT = 6000
BIBTEX_RESPONSE_LIMIT = 100_000
BIBTEX_EVIDENCE_LIMIT = 50_000
DOI_CANDIDATE_LIMIT = 20
DOI_TITLE_MATCH_THRESHOLD = 0.70
GENERATED_PDF_TITLE_PATTERN = re.compile(
    r"^(?:untitled|[A-Z][A-Z0-9-]*\s+\d+\.\.\d+)$",
    re.IGNORECASE,
)
NUMBERED_AUTHOR_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){1,3})"
    r"(?=\d+\s*[*\u2020\u2217,]?(?:\s|$))"
)


class MetadataResolutionError(Exception):
    pass


def normalize_doi(value):
    if not value:
        return ""
    value = str(value).strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi\s*:\s*", "", value, flags=re.IGNORECASE)
    return value.rstrip(".,;:)]}>\"'").lower()


def extract_pdf_evidence(uploaded_file):
    uploaded_file.seek(0)
    raw = uploaded_file.read()
    uploaded_file.seek(0)
    evidence = {
        "doi": None,
        "title": None,
        "authors": [],
        "pages_scanned": 0,
        "page_numbers_scanned": [],
        "pages": [],
        "doi_candidates": [],
        "doi_source": None,
    }

    if raw.startswith(b"%PDF-"):
        try:
            reader = PdfReader(uploaded_file, strict=False)
            metadata = reader.metadata or {}
            embedded_title = _clean_text(getattr(metadata, "title", None) or metadata.get("/Title"))
            evidence["title"] = None if _is_generated_pdf_title(embedded_title) else embedded_title
            author = _clean_text(getattr(metadata, "author", None) or metadata.get("/Author"))
            if author:
                evidence["authors"] = [author]
            page_count = len(reader.pages)
            page_indexes = sorted({
                *range(min(2, page_count)),
                *range(max(0, page_count - 2), page_count),
            })
            for page_index in page_indexes:
                page = reader.pages[page_index]
                text = page.extract_text() or ""
                if page_index == 0 and not evidence["title"]:
                    page_title = _extract_first_page_title(text)
                    if page_title:
                        evidence["title"] = page_title
                if page_index == 0 and not evidence["authors"]:
                    evidence["authors"] = _extract_first_page_authors(text)
                page_dois = _extract_dois(text)
                evidence["page_numbers_scanned"].append(page_index + 1)
                evidence["pages"].append({
                    "number": page_index + 1,
                    "text": _clean_text(text)[:PDF_PAGE_TEXT_LIMIT],
                    "dois": page_dois,
                })
                for doi in page_dois:
                    _append_doi_candidate(
                        evidence["doi_candidates"],
                        {"doi": doi, "source": "pdf_page", "page": page_index + 1},
                    )
            evidence["pages_scanned"] = len(page_indexes)
        except Exception:
            pass
        finally:
            uploaded_file.seek(0)

    for doi in _extract_dois(raw.decode("latin-1", errors="ignore")):
        _append_doi_candidate(
            evidence["doi_candidates"],
            {"doi": doi, "source": "pdf_raw", "page": None},
        )
    if evidence["doi_candidates"]:
        selected = evidence["doi_candidates"][0]
        evidence["doi"] = selected["doi"]
        evidence["doi_source"] = {"source": selected["source"], "page": selected["page"]}
    return evidence


def fetch_doi_bibtex(doi):
    base_url = settings.DOI_RESOLVER_URL.rstrip("/")
    base_parts = urlsplit(base_url)
    if base_parts.scheme != "https" or not base_parts.netloc:
        raise MetadataResolutionError("DOI resolver URL must be a valid HTTPS URL.")
    request = Request(
        f"{base_url}/{quote(normalize_doi(doi), safe='/')}",
        headers={
            "Accept": "application/x-bibtex",
            "User-Agent": _metadata_user_agent(),
        },
    )
    try:
        with urlopen(request, timeout=settings.METADATA_HTTP_TIMEOUT) as response:
            payload = response.read(BIBTEX_RESPONSE_LIMIT + 1)
    except Exception as exc:
        raise MetadataResolutionError("DOI BibTeX lookup failed.") from exc
    if len(payload) > BIBTEX_RESPONSE_LIMIT:
        raise MetadataResolutionError("DOI BibTeX response is too large.")
    try:
        bibtex = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MetadataResolutionError("DOI resolver returned non-UTF-8 BibTeX.") from exc
    if not bibtex.lstrip().startswith("@"):
        raise MetadataResolutionError("DOI resolver returned an invalid BibTeX record.")
    return bibtex


def fetch_crossref_work(doi):
    base_url = settings.CROSSREF_API_URL.rstrip("/")
    base_parts = urlsplit(base_url)
    if base_parts.scheme != "https" or not base_parts.netloc:
        raise MetadataResolutionError("Crossref API URL must be a valid HTTPS URL.")
    request = Request(
        f"{base_url}/works/{quote(normalize_doi(doi), safe='')}",
        headers={
            "Accept": "application/json",
            "User-Agent": _metadata_user_agent(),
        },
    )
    try:
        with urlopen(request, timeout=settings.METADATA_HTTP_TIMEOUT) as response:
            payload = json.load(response)
    except Exception as exc:
        raise MetadataResolutionError("Crossref metadata lookup failed.") from exc
    message = payload.get("message")
    if not isinstance(message, dict):
        raise MetadataResolutionError("Crossref returned an invalid work record.")
    return message


def select_pdf_doi(evidence, bibtex_fetcher=None):
    candidates = evidence.get("doi_candidates") or []
    if len(candidates) < 2 or not evidence.get("title"):
        doi = normalize_doi(evidence.get("doi"))
        if not doi:
            return "", ""
        return doi, (bibtex_fetcher or fetch_doi_bibtex)(doi)

    fetcher = bibtex_fetcher or fetch_doi_bibtex

    def resolve_candidate(candidate):
        doi = normalize_doi(candidate.get("doi"))
        if not doi:
            return None
        try:
            raw_bibtex = fetcher(doi)
            _, metadata = parse_bibtex_metadata(raw_bibtex, expected_doi=doi)
            if normalize_doi(metadata["doi"]) != doi:
                return None
        except MetadataResolutionError:
            return None
        return {
            "doi": doi,
            "raw_bibtex": raw_bibtex,
            "title": metadata["title"],
            "title_similarity": _title_similarity(evidence["title"], metadata["title"]),
            "has_publication_container": bool(metadata["journal"]),
            "source": candidate.get("source"),
            "page": candidate.get("page"),
        }

    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
        matches = [match for match in executor.map(resolve_candidate, candidates) if match]

    if not matches:
        raise MetadataResolutionError("No PDF DOI candidate returned matching BibTeX metadata.")
    selected = max(
        matches,
        key=lambda candidate: (
            candidate["title_similarity"],
            candidate["has_publication_container"],
        ),
    )
    evidence["doi_selection"] = {
        "method": "bibtex_title_similarity_then_publication_container",
        "threshold": DOI_TITLE_MATCH_THRESHOLD,
        "candidates": [{
            "doi": candidate["doi"],
            "title": candidate["title"],
            "title_similarity": round(candidate["title_similarity"], 6),
            "has_publication_container": candidate["has_publication_container"],
        } for candidate in matches],
    }
    if selected["title_similarity"] < DOI_TITLE_MATCH_THRESHOLD:
        raise MetadataResolutionError("No PDF DOI candidate matches the PDF title.")
    evidence["doi"] = selected["doi"]
    evidence["doi_source"] = {"source": selected["source"], "page": selected["page"]}
    return selected["doi"], selected["raw_bibtex"]


def resolve_pdf_metadata(canonical, uploaded_file, crossref_fetcher=None, bibtex_fetcher=None):
    if canonical.metadata_status not in {
        CanonicalDocument.MetadataStatus.PENDING,
        CanonicalDocument.MetadataStatus.INCOMPLETE,
    }:
        return canonical

    evidence = extract_pdf_evidence(uploaded_file)
    canonical.metadata_evidence = {**canonical.metadata_evidence, "pdf": evidence}
    canonical.metadata_source = "pdf"
    if not canonical.title and evidence["title"]:
        canonical.title = evidence["title"]
    if not canonical.authors and evidence["authors"]:
        canonical.authors = [{"name": name} for name in evidence["authors"]]

    provider_errors = {}
    raw_bibtex = ""
    candidate_dois = [normalize_doi(candidate.get("doi")) for candidate in evidence["doi_candidates"]]
    doi = normalize_doi(canonical.doi) if normalize_doi(canonical.doi) in candidate_dois else ""
    if not doi and len(candidate_dois) > 1:
        try:
            doi, raw_bibtex = select_pdf_doi(evidence, bibtex_fetcher=bibtex_fetcher)
        except MetadataResolutionError as exc:
            return _save_conflict(
                canonical,
                "doi",
                [{"value": candidate["doi"], "source": candidate["source"]} for candidate in evidence["doi_candidates"]],
                provider_errors={"bibtex": str(exc)},
            )
    doi = doi or evidence["doi"]
    if not doi:
        canonical.metadata_status = CanonicalDocument.MetadataStatus.INCOMPLETE
        canonical.save()
        return canonical

    canonical.doi = doi
    canonical.identifiers = {**canonical.identifiers, "doi": doi}
    canonical.metadata_status = CanonicalDocument.MetadataStatus.NEEDS_REVIEW
    canonical.metadata_confidence = 0.600

    bibtex_entry = None
    bibtex_metadata = None
    try:
        raw_bibtex = raw_bibtex or (bibtex_fetcher or fetch_doi_bibtex)(doi)
        bibtex_entry, bibtex_metadata = parse_bibtex_metadata(raw_bibtex, expected_doi=doi)
    except MetadataResolutionError as exc:
        provider_errors["bibtex"] = str(exc)

    crossref_metadata = None
    try:
        work = (crossref_fetcher or fetch_crossref_work)(doi)
        crossref_metadata = _crossref_metadata(work)
    except MetadataResolutionError as exc:
        provider_errors["crossref"] = str(exc)

    if bibtex_metadata and normalize_doi(bibtex_metadata["doi"]) != doi:
        return _save_conflict(canonical, "doi", [
            {"value": doi, "source": "pdf"},
            {"value": bibtex_metadata["doi"], "source": "bibtex"},
        ], provider_errors=provider_errors, provider_evidence=_conflict_provider_evidence(
            canonical.metadata_evidence, raw_bibtex, bibtex_metadata, crossref_metadata,
        ))
    if crossref_metadata and normalize_doi(crossref_metadata["doi"]) != doi:
        return _save_conflict(canonical, "doi", [
            {"value": doi, "source": "pdf"},
            {"value": crossref_metadata["doi"], "source": "crossref"},
        ], provider_errors=provider_errors, provider_evidence=_conflict_provider_evidence(
            canonical.metadata_evidence, raw_bibtex, bibtex_metadata, crossref_metadata,
        ))

    if (
        bibtex_metadata
        and crossref_metadata
        and bibtex_metadata["title"]
        and crossref_metadata["title"]
        and _title_similarity(bibtex_metadata["title"], crossref_metadata["title"]) < 0.45
    ):
        return _save_conflict(canonical, "title", [
            {"value": bibtex_metadata["title"], "source": "bibtex"},
            {"value": crossref_metadata["title"], "source": "crossref"},
        ], provider_errors=provider_errors, provider_evidence=_conflict_provider_evidence(
            canonical.metadata_evidence, raw_bibtex, bibtex_metadata, crossref_metadata,
        ))

    resolved, field_sources = _merge_metadata(bibtex_metadata, crossref_metadata)
    if not resolved:
        canonical.metadata_evidence = _with_provider_errors(canonical.metadata_evidence, provider_errors)
        canonical.save()
        return canonical

    if (
        evidence["title"]
        and resolved["title"]
        and _title_similarity(evidence["title"], resolved["title"]) < DOI_TITLE_MATCH_THRESHOLD
    ):
        return _save_conflict(canonical, "title", [
            {"value": evidence["title"], "source": "pdf"},
            {"value": resolved["title"], "source": "bibtex" if bibtex_metadata else "crossref"},
        ], provider_errors=provider_errors, provider_evidence=_conflict_provider_evidence(
            canonical.metadata_evidence, raw_bibtex, bibtex_metadata, crossref_metadata,
        ))

    for field in ("title", "authors", "abstract", "journal", "publication_year", "source_tags"):
        value = resolved.get(field)
        if value not in (None, "", []):
            setattr(canonical, field, value)
    canonical.doi = doi
    canonical.identifiers = {**canonical.identifiers, "doi": doi}
    canonical.metadata_source = "bibtex" if bibtex_metadata else "crossref"
    if bibtex_metadata:
        complete = _metadata_is_complete(resolved)
        canonical.metadata_status = (
            CanonicalDocument.MetadataStatus.VERIFIED
            if complete
            else CanonicalDocument.MetadataStatus.NEEDS_REVIEW
        )
        canonical.metadata_confidence = 1.000 if complete and crossref_metadata else (0.900 if complete else 0.700)
    else:
        canonical.metadata_status = CanonicalDocument.MetadataStatus.VERIFIED
        canonical.metadata_confidence = 1.000

    provider_evidence = dict(canonical.metadata_evidence)
    if crossref_metadata:
        provider_evidence["crossref"] = {
            "doi": crossref_metadata["doi"],
            "fields": _populated_fields(crossref_metadata),
        }
    if bibtex_metadata:
        try:
            enriched_bibtex = _enriched_bibtex(bibtex_entry, resolved)
        except Exception:
            enriched_bibtex = raw_bibtex
            provider_errors["bibtex_enrichment"] = "BibTeX evidence enrichment failed."
        provider_evidence["bibtex"] = {
            "doi": bibtex_metadata["doi"],
            "fields": _populated_fields(bibtex_metadata),
            "field_sources": field_sources,
            "abstract_source": field_sources.get("abstract"),
            "raw": raw_bibtex[:BIBTEX_EVIDENCE_LIMIT],
            "raw_truncated": len(raw_bibtex) > BIBTEX_EVIDENCE_LIMIT,
            "enriched": enriched_bibtex[:BIBTEX_EVIDENCE_LIMIT],
            "enriched_truncated": len(enriched_bibtex) > BIBTEX_EVIDENCE_LIMIT,
        }
    canonical.metadata_evidence = _with_provider_errors(provider_evidence, provider_errors)
    canonical.save()
    return canonical


def resolve_pdf_metadata_safely(canonical, uploaded_file, crossref_fetcher=None, bibtex_fetcher=None):
    try:
        return resolve_pdf_metadata(
            canonical,
            uploaded_file,
            crossref_fetcher=crossref_fetcher,
            bibtex_fetcher=bibtex_fetcher,
        )
    except Exception:
        canonical.metadata_status = CanonicalDocument.MetadataStatus.NEEDS_REVIEW
        canonical.metadata_source = canonical.metadata_source or "pdf"
        canonical.save(update_fields=("metadata_status", "metadata_source", "updated_at"))
        return canonical


def _crossref_metadata(work):
    title = _first(work.get("title"))
    journal = _first(work.get("container-title"))
    authors = []
    for author in work.get("author") or []:
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part).strip()
        if not name:
            name = author.get("name", "").strip()
        if name:
            record = {"name": name}
            if author.get("ORCID"):
                record["orcid"] = author["ORCID"].removeprefix("https://orcid.org/")
            authors.append(record)

    year = None
    for date_field in ("published-print", "published-online", "published", "issued", "created"):
        parts = (work.get(date_field) or {}).get("date-parts") or []
        if parts and parts[0]:
            year = parts[0][0]
            break
    if year is None:
        match = YEAR_PATTERN.search(str(work.get("published", "")))
        year = int(match.group(0)) if match else None

    abstract = _clean_text(TAG_PATTERN.sub(" ", unescape(work.get("abstract") or "")))
    return {
        "doi": normalize_doi(work.get("DOI")),
        "title": _clean_text(title),
        "authors": authors,
        "abstract": abstract,
        "journal": _clean_text(journal),
        "publication_year": year,
        "source_tags": [],
    }


def parse_bibtex_metadata(raw_bibtex, expected_doi=""):
    parser = BibTexParser(common_strings=True)
    parser.bib_database.strings.update({
        month.lower(): month for month in (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )
    })
    parser.bib_database.strings["sept"] = "September"
    parser.customization = _customize_bibtex_record
    try:
        database = bibtexparser.loads(raw_bibtex, parser=parser)
    except Exception as exc:
        raise MetadataResolutionError("DOI resolver returned unparseable BibTeX.") from exc
    entries = database.entries
    if not entries:
        raise MetadataResolutionError("DOI resolver returned BibTeX without an entry.")

    expected_doi = normalize_doi(expected_doi)
    matching = [entry for entry in entries if normalize_doi(entry.get("doi")) == expected_doi]
    if matching:
        entry = matching[0]
    elif len(entries) == 1:
        entry = entries[0]
    else:
        raise MetadataResolutionError("DOI resolver returned ambiguous BibTeX entries.")
    if expected_doi and not normalize_doi(entry.get("doi")):
        entry["doi"] = expected_doi
    return entry, _bibtex_metadata(entry)


def _bibtex_metadata(entry):
    author_values = entry.get("author") or []
    if isinstance(author_values, str):
        author_values = [author_values]
    authors = []
    for value in author_values:
        name = _bibtex_author_name(value)
        if name:
            authors.append({"name": name})
    year_match = YEAR_PATTERN.search(str(entry.get("year") or entry.get("date") or ""))
    keywords = re.split(r"\s*[;,]\s*", _clean_text(entry.get("keywords") or entry.get("keyword")))
    return {
        "doi": normalize_doi(entry.get("doi")),
        "title": _clean_text(entry.get("title")),
        "authors": authors,
        "abstract": _clean_text(entry.get("abstract")),
        "journal": _clean_text(entry.get("journal") or entry.get("booktitle")),
        "publication_year": int(year_match.group(0)) if year_match else None,
        "source_tags": list(dict.fromkeys(value for value in keywords if value)),
    }


def _merge_metadata(primary, supplemental):
    if not primary and not supplemental:
        return None, {}
    merged = {}
    field_sources = {}
    for field in ("doi", "title", "authors", "abstract", "journal", "publication_year", "source_tags"):
        primary_value = (primary or {}).get(field)
        supplemental_value = (supplemental or {}).get(field)
        if primary_value not in (None, "", []):
            merged[field] = primary_value
            field_sources[field] = "bibtex"
        elif supplemental_value not in (None, "", []):
            merged[field] = supplemental_value
            field_sources[field] = "crossref"
        else:
            merged[field] = [] if field in {"authors", "source_tags"} else None
    return merged, field_sources


def _enriched_bibtex(entry, resolved):
    enriched = dict(entry)
    if isinstance(enriched.get("author"), list):
        enriched["author"] = " and ".join(enriched["author"])
    if resolved.get("abstract") and not enriched.get("abstract"):
        enriched["abstract"] = resolved["abstract"]
    if resolved.get("journal") and not (enriched.get("journal") or enriched.get("booktitle")):
        enriched["journal"] = resolved["journal"]
    if resolved.get("publication_year") and not enriched.get("year"):
        enriched["year"] = str(resolved["publication_year"])
    if resolved.get("title") and not enriched.get("title"):
        enriched["title"] = resolved["title"]
    if resolved.get("authors") and not enriched.get("author"):
        enriched["author"] = " and ".join(author["name"] for author in resolved["authors"])
    database = BibDatabase()
    database.entries = [enriched]
    writer = BibTexWriter()
    writer.order_entries_by = None
    return bibtexparser.dumps(database, writer=writer)


def _customize_bibtex_record(record):
    return split_bibtex_authors(convert_to_unicode(record))


def _bibtex_author_name(value):
    parts = [part.strip() for part in str(value or "").strip("{} ").split(",")]
    if len(parts) == 2 and all(parts):
        return _clean_text(f"{parts[1]} {parts[0]}")
    return _clean_text(" ".join(parts))


def _metadata_is_complete(metadata):
    return bool(metadata.get("doi") and metadata.get("title") and metadata.get("authors") and metadata.get("publication_year"))


def _populated_fields(metadata):
    return [key for key, value in metadata.items() if value not in (None, "", [])]


def _save_conflict(canonical, field, candidates, provider_errors=None, provider_evidence=None):
    canonical.metadata_candidates = {**canonical.metadata_candidates, field: candidates}
    canonical.metadata_status = CanonicalDocument.MetadataStatus.CONFLICT
    canonical.metadata_evidence = _with_provider_errors(
        provider_evidence or canonical.metadata_evidence,
        provider_errors or {},
    )
    canonical.save()
    return canonical


def _conflict_provider_evidence(evidence, raw_bibtex, bibtex_metadata, crossref_metadata):
    result = dict(evidence)
    if bibtex_metadata:
        bounded_raw = raw_bibtex[:BIBTEX_EVIDENCE_LIMIT]
        result["bibtex"] = {
            "doi": bibtex_metadata["doi"],
            "fields": _populated_fields(bibtex_metadata),
            "raw": bounded_raw,
            "raw_truncated": len(raw_bibtex) > BIBTEX_EVIDENCE_LIMIT,
            "enriched": bounded_raw,
            "enriched_truncated": len(raw_bibtex) > BIBTEX_EVIDENCE_LIMIT,
        }
    if crossref_metadata:
        result["crossref"] = {
            "doi": crossref_metadata["doi"],
            "fields": _populated_fields(crossref_metadata),
        }
    return result


def _with_provider_errors(evidence, provider_errors):
    result = dict(evidence)
    if provider_errors:
        result["provider_errors"] = provider_errors
    else:
        result.pop("provider_errors", None)
    return result


def _extract_dois(text):
    return list(dict.fromkeys(normalize_doi(match.group(0)) for match in DOI_PATTERN.finditer(text)))


def _append_doi_candidate(candidates, candidate):
    if len(candidates) >= DOI_CANDIDATE_LIMIT:
        return
    if any(item["doi"] == candidate["doi"] for item in candidates):
        return
    candidates.append(candidate)


def _title_similarity(left, right):
    normalize = lambda value: " ".join(re.findall(r"\w+", value.lower()))
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def _is_generated_pdf_title(value):
    return bool(value and GENERATED_PDF_TITLE_PATTERN.fullmatch(_clean_text(value)))


def _extract_first_page_title(text):
    lines = [_clean_text(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    title_lines = []
    for line in lines[:20]:
        if re.match(r"^(?:abstract|\u6458\u8981)\b", line, re.IGNORECASE):
            break
        if title_lines and (_looks_like_pdf_author_line(line) or _looks_like_numbered_author_line(line)):
            break
        title_lines.append(line)
    return _clean_text(" ".join(title_lines))


def _looks_like_pdf_author_line(line):
    return bool(
        re.search(r",\s*[a-z](?:\s*,\s*[a-z])*(?:\s*[,*\u2020])", line, re.IGNORECASE)
        or re.search(r"\s+(?:and|\u7b49)\s*$", line, re.IGNORECASE)
    )


def _looks_like_numbered_author_line(line):
    return bool(NUMBERED_AUTHOR_PATTERN.search(line))


def _extract_first_page_authors(text):
    lines = [_clean_text(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    started = False
    authors = []
    for line in lines[:20]:
        if re.match(r"^(?:abstract|\u6458\u8981)\b", line, re.IGNORECASE):
            break
        numbered = _looks_like_numbered_author_line(line)
        if not started:
            if not (numbered or _looks_like_pdf_author_line(line)):
                continue
            started = True
        if numbered:
            authors.extend(_clean_text(value) for value in NUMBERED_AUTHOR_PATTERN.findall(line))
        elif not authors and _looks_like_pdf_author_line(line):
            authors.append(line)
        else:
            break
    return list(dict.fromkeys(author for author in authors if author))


def _first(value):
    return value[0] if isinstance(value, list) and value else ""


def _clean_text(value):
    return " ".join(str(value or "").replace("\x00", " ").split())


def _metadata_user_agent():
    mailto = settings.CROSSREF_MAILTO.strip()
    return f"PLAB-Literature/1.0 (mailto:{mailto})" if mailto else "PLAB-Literature/1.0"
