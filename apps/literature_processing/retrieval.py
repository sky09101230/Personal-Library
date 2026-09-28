"""Deterministic single-paper lexical and structural retrieval."""

from dataclasses import dataclass
import re

from .evidence import EvidenceCatalog


RETRIEVAL_VERSION = "paper-lexical-v1"
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]")
_FIGURE = re.compile(r"\b(?:fig(?:ure)?|图)\.?\s*(\d+(?:\s*[a-z])?)\b", re.I)


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    evidence_id: str
    score: float
    lexical_score: float
    structural_score: float
    evidence: object


def retrieve(catalog: EvidenceCatalog, query, *, rewritten_queries=(), limit=20):
    queries = tuple(dict.fromkeys((query, *rewritten_queries)))
    query_terms = set(term.lower() for value in queries for term in _tokens(value))
    labels = {match.group(1).replace(" ", "").lower() for match in _FIGURE.finditer(query)}
    hits = []
    for order, item in enumerate(catalog.items):
        text_terms = set(term.lower() for term in _tokens(item.text))
        lexical = sum(1 for term in query_terms if term in text_terms)
        if not lexical and not (labels and item.figure_label.lower() in labels):
            continue
        structural = 0.0
        if item.kind == "figure" and labels and item.figure_label.lower() in labels:
            structural += 8.0
        if item.kind in {"table", "equation"} and any(term in text_terms for term in query_terms):
            structural += 2.0
        if item.section_path:
            structural += 0.5
        score = float(lexical) + structural
        hits.append(RetrievalHit(item.evidence_id, score, float(lexical), structural, item))
    hits.sort(key=lambda hit: (-hit.score, -hit.lexical_score, hit.evidence.locator))
    return tuple(hits[:max(0, int(limit))])


def rewrite_query(query, *, history=(), provider=None):
    if provider is None:
        return (), "rewrite_unavailable"
    try:
        result = provider("chat", [{"role": "user", "content": query}], output_mode="json")
        values = result if isinstance(result, list) else result.get("queries", [])
        values = tuple(value.strip() for value in values if isinstance(value, str) and value.strip())
        return values[:4], ""
    except Exception:
        return (), "rewrite_unavailable"


def _tokens(text):
    return _WORD.findall(str(text or ""))
