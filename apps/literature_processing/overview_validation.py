from django.core.exceptions import ValidationError

from .models import LiteratureChunk


_OVERVIEW_FIELDS = {"summary_short", "summary", "topics", "key_points"}


def validate_overview_payload(payload, document_parse_id):
    if not document_parse_id:
        raise ValidationError({"document_parse": "Overview requires a saved parse."})
    if not isinstance(payload, dict) or set(payload) != _OVERVIEW_FIELDS:
        raise ValidationError({"payload": "Overview must contain only the four supported fields."})
    _require_text(payload["summary_short"], "summary_short", max_length=500)
    _require_text(payload["summary"], "summary", max_length=10_000)
    _validate_topics(payload["topics"])

    key_points = payload["key_points"]
    if not isinstance(key_points, list) or not 1 <= len(key_points) <= 50:
        raise ValidationError({"payload": "Overview key_points must contain between 1 and 50 items."})

    evidence_items = []
    chunk_ids = set()
    for key_point in key_points:
        if not isinstance(key_point, dict) or set(key_point) != {"text", "evidence"}:
            raise ValidationError({"payload": "Each key point must contain text and evidence."})
        _require_text(key_point["text"], "key point", max_length=2000)
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
            chunk_ids.add(chunk_id)
            evidence_items.append(item)

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


def _validate_topics(topics):
    if not isinstance(topics, list) or len(topics) > 50:
        raise ValidationError({"payload": "Overview topics must be a list with at most 50 items."})
    for topic in topics:
        _require_text(topic, "topic", max_length=200)


def _require_text(value, field_name, *, max_length):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValidationError({"payload": f"Overview {field_name} must be non-empty text."})


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0

