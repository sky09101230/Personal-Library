"""Bounded, reproducible context packets for chat and skeleton generation."""

from dataclasses import dataclass
import hashlib
import json

from .retrieval import RETRIEVAL_VERSION, retrieve, rewrite_query


CONTEXT_VERSION = "personal.paper-context.v1"
DEFAULT_BUDGET = 24000


class ContextError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ContextPacket:
    payload: dict

    @property
    def fingerprint(self):
        return self.payload["fingerprint"]

    @property
    def allowed_evidence_ids(self):
        return frozenset(self.payload["allowed_evidence_ids"])


def build_context_packet(catalog, query="", *, history=(), budget=DEFAULT_BUDGET, purpose="chat", provider=None, rewritten_queries=None):
    budget = int(budget)
    if budget < 100:
        raise ContextError("context_budget_exceeded", "Context budget is too small.")
    rewritten, warning = ((tuple(rewritten_queries), "") if rewritten_queries is not None
                          else rewrite_query(query, history=history, provider=provider))
    hits = retrieve(catalog, query, rewritten_queries=rewritten, limit=100)
    items = []
    used = 0
    for hit in hits:
        evidence = hit.evidence
        excerpt = evidence.text[: max(0, budget - used)]
        if not excerpt:
            break
        item = {
            "evidence_id": evidence.evidence_id,
            "kind": evidence.kind,
            "text": excerpt,
            "pages": list(evidence.pages),
            "section_path": list(evidence.section_path),
            "score": {"total": hit.score, "lexical": hit.lexical_score, "structural": hit.structural_score},
        }
        serialized_size = len(json.dumps(item, ensure_ascii=False))
        if used + serialized_size > budget and items:
            break
        used += serialized_size
        items.append(item)
    if not items and query:
        raise ContextError("insufficient_retrieval", "No evidence matched the paper.")
    coverage = _coverage(catalog, items, purpose)
    payload = {
        "schema_version": CONTEXT_VERSION, "purpose": purpose, "parse_id": catalog.document_parse.pk,
        "artifact_sha256": catalog.document_parse.artifact_sha256, "query": query,
        "rewritten_queries": list(rewritten), "retrieval_version": RETRIEVAL_VERSION,
        "items": items, "allowed_evidence_ids": [item["evidence_id"] for item in items],
        "budget": {"max_chars": budget, "estimated": True, "used": used}, "coverage": coverage,
        "warnings": [warning] if warning else [],
    }
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return ContextPacket({**payload, "fingerprint": fingerprint})


def build_skeleton_inventory(catalog):
    sections = {}
    figures = []
    for item in catalog.items:
        bucket = _bucket(item.section_path, item.text)
        if item.text:
            sections.setdefault(bucket, []).append(item.evidence_id)
        if item.kind == "figure":
            figures.append({"evidence_id": item.evidence_id, "label": item.figure_label, "pages": list(item.pages), "availability": item.availability})
    return {"sections": sections, "figures": figures, "total_evidence": len(catalog.items)}


def build_skeleton_context(catalog, *, budget=DEFAULT_BUDGET):
    """Select structural buckets before filling remaining budget."""
    inventory = build_skeleton_inventory(catalog)
    selected = []
    selected_ids = set()
    preferred = ("introduction", "method", "results", "conclusion", "other")
    per_bucket = max(1, int(budget / max(1, len(preferred))))
    used = 0
    for bucket in preferred:
        for evidence_id in inventory["sections"].get(bucket, ()):
            item = catalog.get(evidence_id)
            size = len(item.text) + 120
            if used + size > budget and selected:
                break
            selected.append(item)
            selected_ids.add(item.evidence_id)
            used += size
            if used >= budget:
                break
        if used >= budget:
            break
    omitted = [figure for figure in inventory["figures"] if figure["evidence_id"] not in selected_ids]
    return {
        "schema_version": CONTEXT_VERSION,
        "purpose": "skeleton",
        "items": [{"evidence_id": item.evidence_id, "text": item.text, "pages": list(item.pages), "kind": item.kind} for item in selected],
        "allowed_evidence_ids": [item.evidence_id for item in selected],
        "coverage": {"inventory": inventory, "selected": len(selected), "omitted_figures": omitted,
                     "partial": bool(omitted)},
        "budget": {"max_chars": budget, "used": used, "estimated": True},
    }


def _coverage(catalog, items, purpose):
    inventory = build_skeleton_inventory(catalog) if purpose == "skeleton" else {}
    return {"purpose": purpose, "selected": len(items), "total": len(catalog.items), "inventory": inventory}


def _bucket(section_path, text):
    value = " ".join(section_path).lower()
    if any(word in value for word in ("conclusion", "discussion")):
        return "conclusion"
    if any(word in value for word in ("method", "architecture", "approach")):
        return "method"
    if any(word in value for word in ("result", "experiment")):
        return "results"
    if "introduction" in value or "motivation" in value:
        return "introduction"
    return "other"
