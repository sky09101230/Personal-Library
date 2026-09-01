from django.core.exceptions import ValidationError

from .models import LiteratureChunk


_OVERVIEW_FIELDS = {"summary_short", "summary", "topics", "key_points"}
_TRANSLATION_FIELD = "chinese_translation"


def validate_overview_payload(payload, document_parse_id):
    if not document_parse_id:
        raise ValidationError({"document_parse": "Overview requires a saved parse."})
    if not isinstance(payload, dict) or frozenset(payload) not in {
        frozenset(_OVERVIEW_FIELDS),
        frozenset(_OVERVIEW_FIELDS | {_TRANSLATION_FIELD}),
    }:
        raise ValidationError({"payload": "Overview contains unsupported fields."})

    english_content = {field: payload[field] for field in _OVERVIEW_FIELDS}
    evidence_items = _validate_overview_content(english_content)
    translation = payload.get(_TRANSLATION_FIELD)
    if translation is not None:
        _validate_overview_content(translation, field_prefix="translated ")
        if len(translation["topics"]) != len(payload["topics"]):
            raise ValidationError({"payload": "Translated topics must match the English topic count."})
        if len(translation["key_points"]) != len(payload["key_points"]):
            raise ValidationError({"payload": "Translated key points must match the English key point count."})
        for english_point, translated_point in zip(payload["key_points"], translation["key_points"]):
            if translated_point["evidence"] != english_point["evidence"]:
                raise ValidationError({"payload": "Each translated key point must preserve its English evidence."})

    _validate_evidence(evidence_items, document_parse_id)


def _validate_overview_content(payload, *, field_prefix=""):
    if not isinstance(payload, dict) or set(payload) != _OVERVIEW_FIELDS:
        raise ValidationError({"payload": "Each overview language must contain only the four supported fields."})
    _require_text(payload["summary_short"], f"{field_prefix}summary_short", max_length=500)
    _require_text(payload["summary"], f"{field_prefix}summary", max_length=10_000)
    _validate_topics(payload["topics"], field_prefix=field_prefix)

    key_points = payload["key_points"]
    if not isinstance(key_points, list) or not 1 <= len(key_points) <= 50:
        raise ValidationError({"payload": f"Overview {field_prefix}key_points must contain between 1 and 50 items."})

    evidence_items = []
    for key_point in key_points:
        if not isinstance(key_point, dict) or set(key_point) != {"text", "evidence"}:
            raise ValidationError({"payload": "Each key point must contain text and evidence."})
        _require_text(key_point["text"], f"{field_prefix}key point", max_length=2000)
        evidence = key_point["evidence"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
            raise ValidationError({"payload": "Each key point must cite at least one evidence item."})
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"chunk_id", "page"}:
                raise ValidationError({"payload": "Evidence must contain chunk_id and page."})
            chunk_id = item["chunk_id"]
            page = item["page"]
            if not _is_integer(chunk_id) or not _is_integer(page):
                raise ValidationError({"payload": "Evidence chunk_id and page must be positive integers."})
            evidence_items.append(item)
    return evidence_items


def _validate_evidence(evidence_items, document_parse_id):
    chunk_ids = {item["chunk_id"] for item in evidence_items}

    chunks = {
        chunk.pk: chunk
        for chunk in LiteratureChunk.objects.filter(document_parse_id=document_parse_id, pk__in=chunk_ids)
    }
    for item in evidence_items:
        chunk = chunks.get(item["chunk_id"])
        if chunk is None:
            raise ValidationError({"payload": "Evidence chunk does not belong to this parse."})
        if chunk.page_number != item["page"]:
            raise ValidationError({"payload": "Evidence page does not match its chunk."})


def _validate_topics(topics, *, field_prefix=""):
    if not isinstance(topics, list) or len(topics) > 50:
        raise ValidationError({"payload": f"Overview {field_prefix}topics must be a list with at most 50 items."})
    for topic in topics:
        _require_text(topic, f"{field_prefix}topic", max_length=200)


def _require_text(value, field_name, *, max_length):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValidationError({"payload": f"Overview {field_name} must be non-empty text."})


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
