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
        excerpt = evidence.text
        if not excerpt:
            continue
        item = {
            "evidence_id": evidence.evidence_id,
            "kind": evidence.kind,
            "text": excerpt,
            "pages": list(evidence.pages),
            "section_path": list(evidence.section_path),
            "score": {"total": hit.score, "lexical": hit.lexical_score, "structural": hit.structural_score},
        }
        serialized_size = len(json.dumps(item, ensure_ascii=False))
        if used + serialized_size > budget:
            continue
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
    """Round-robin complete source items; reserve every present section and figure."""
    import re
    groups = {}
    seen = set()
    figures = [item for item in catalog.items if item.kind == "figure"]
    # Structured blocks prevent duplicate chunk+block copies of the same text.
    structured = any(item.block_ids and item.text.strip() for item in catalog.items)
    for item in catalog.items:
        if item.kind == "figure" or not item.text.strip():
            continue
        if structured and not item.block_ids:
            continue
        section = " ".join(item.section_path[-1:]).lower()
        if any(word in section for word in ("references", "acknowledg", "competing", "rights", "permission", "related articles", "take down", "citing this", "author contributions")):
            continue
        text = item.text.strip()
        normalized = " ".join(text.split())
        if normalized in seen or len(text) < 60:
            continue
        seen.add(normalized)
        bucket = _bucket(item.section_path, text)
        if re.match(r"^(?:fig(?:ure)?|图)\.?\s*\d+", text, re.I):
            # Each caption is a reserved group, including the final figure.
            bucket = "caption:" + item.evidence_id
        groups.setdefault(bucket, []).append(item)
    ordered = [key for key in ("abstract", "introduction", "method", "results", "conclusion", "other") if key in groups]
    ordered += [key for key in groups if key.startswith("caption:")]
    selected = []
    selected_ids = set()
    def pack(item):
        return {"evidence_id": item.evidence_id, "kind": item.kind, "text": item.text,
                "pages": list(item.pages), "section_path": list(item.section_path)}
    payload = {"schema_version": CONTEXT_VERSION, "context_version": "skeleton-balanced-v2",
               "purpose": "skeleton", "parse_id": catalog.document_parse.pk,
               "artifact_sha256": catalog.document_parse.artifact_sha256,
               "items": [], "allowed_evidence_ids": [], "coverage": {}}
    def fits(items):
        candidate = {**payload, "items": [pack(item) for item in items],
                     "allowed_evidence_ids": [item.evidence_id for item in items]}
        # Reserve metadata room; JSON UTF-8 bytes conservatively bound text tokens.
        return len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) + 2048 <= budget
    for key in ordered:
        item = groups[key][0]
        if not fits(selected + [item]):
            raise ContextError("context_budget_exceeded", "上下文预算不足以覆盖章节和图注，请提高 PAPER_SKELETON_CONTEXT_BYTES。")
        selected.append(item); selected_ids.add(item.evidence_id)
    for figure in figures:
        if fits(selected + [figure]):
            selected.append(figure); selected_ids.add(figure.evidence_id)
    depth = 1
    while any(len(groups[key]) > depth for key in ordered):
        for key in ordered:
            if len(groups[key]) > depth:
                item = groups[key][depth]
                if fits(selected + [item]):
                    selected.append(item); selected_ids.add(item.evidence_id)
        depth += 1
    if not any(item.text.strip() for item in selected):
        raise ContextError("no_text", "没有可用于总览的论文正文。")
    eligible = [item for group in groups.values() for item in group] + figures
    payload["items"] = [pack(item) for item in selected]
    payload["allowed_evidence_ids"] = [item.evidence_id for item in selected]
    payload["coverage"] = {"partial": len(selected) < len(eligible),
                           "selected": len(selected), "total": len(eligible),
                           "sections": [key for key in ordered if not key.startswith("caption:")],
                           "figures_selected": sum(item.kind == "figure" for item in selected),
                           "figures_total": len(figures)}
    payload["budget"] = {"max_bytes": budget, "estimated": True}
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > budget:
        raise ContextError("context_budget_exceeded", "上下文超过预算。")
    return payload


def _coverage(catalog, items, purpose):
    inventory = build_skeleton_inventory(catalog) if purpose == "skeleton" else {}
    return {"purpose": purpose, "selected": len(items), "total": len(catalog.items), "inventory": inventory}


def _bucket(section_path, text):
    value = " ".join(section_path[-1:]).lower()
    if any(word in value for word in ("conclusion",)):
        return "conclusion"
    if any(word in value for word in ("method", "architecture", "approach")):
        return "method"
    if any(word in value for word in ("result", "experiment")):
        return "results"
    if "introduction" in value or "motivation" in value:
        return "introduction"
    if "abstract" in value or text.lstrip().lower().startswith("abstract"):
        return "abstract"
    return "other"
