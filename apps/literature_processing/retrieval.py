"""Deterministic single-paper lexical and structural retrieval."""

from dataclasses import dataclass, replace
import json
import re

from .evidence import EvidenceCatalog
from .llm import complete, load_config


RETRIEVAL_VERSION = "paper-lexical-v2"
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]")
_FIGURE = re.compile(r"\b(?:fig(?:ure)?|图)\.?\s*(\d+(?:\s*[a-z])?)\b", re.I)
_STOPWORDS = set("the a an of to in is are was were what how why this that paper work study it does do and for with using used".split())
# These are search aliases only, never answers or evidence.
_QUERY_ALIASES = (
    (("波段", "波长", "频率"), "wavelength frequency spectrum illumination"),
    (("网络结构", "网络架构", "结构", "几层", "层数"), "architecture network layers neurons design"),
    (("方法", "原理", "怎么工作"), "method mechanism design training"),
    (("非相干",), "incoherent illumination"),
    (("相干光",), "coherent illumination"),
    (("准确率", "精度"), "accuracy classification performance"),
    (("实验",), "experimental setup measurements"),
    (("结果", "结论"), "results conclusion performance"),
)


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    evidence_id: str
    score: float
    lexical_score: float
    structural_score: float
    evidence: object


def retrieve(catalog: EvidenceCatalog, query, *, rewritten_queries=(), limit=20):
    queries = tuple(dict.fromkeys((query, *rewritten_queries)))
    query_terms = {term.lower() for value in queries for term in _tokens(value)} - _STOPWORDS
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
    # Preserve source ordering for ties; heterogeneous locator tuples cannot
    # safely be compared (chunk PKs are integers, block IDs are strings).
    hits.sort(key=lambda hit: (-hit.score, -hit.lexical_score))
    return tuple(hits[:max(0, int(limit))])


def rewrite_query(query, *, history=(), provider=None):
    fallback = tuple(alias for triggers, alias in _QUERY_ALIASES if any(trigger in query for trigger in triggers))
    if provider is None or not re.search(r"[\u4e00-\u9fff]", query):
        return fallback, "rewrite_unavailable" if provider is None else ""
    try:
        messages = [
            {"role": "system", "content": "Rewrite the user's question into 1-4 concise English search queries for a single paper. Return JSON ONLY: {\"queries\":[\"...\"]}. Preserve each sub-question, figure numbers, units and named terms. Use history only to resolve pronouns. Do not answer the question or add scientific facts."},
            {"role": "user", "content": json.dumps({"question": query, "history": list(history)[-6:]}, ensure_ascii=False)},
        ]
        if provider is complete:
            config = replace(load_config(), timeout=12, max_retries=0, reasoning_effort="low")
            result = provider("chat", messages, output_mode="json", config=config, max_tokens=384)
        else:
            result = provider("chat", messages, output_mode="json")
        payload = getattr(result, "content", result)
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict) or set(payload) != {"queries"} or not isinstance(payload["queries"], list):
            raise ValueError("Invalid query rewrite")
        values = payload["queries"]
        if not 1 <= len(values) <= 4 or any(not isinstance(value, str) or not value.strip() or len(value) > 256 for value in values):
            raise ValueError("Invalid query rewrite")
        return tuple(dict.fromkeys(list(fallback) + [value.strip() for value in values]))[:4], ""
    except Exception:
        return fallback, "rewrite_unavailable"


def _tokens(text):
    return _WORD.findall(str(text or ""))
