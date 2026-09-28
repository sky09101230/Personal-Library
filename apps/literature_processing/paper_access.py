"""Public access boundary for Paper Intelligence services."""

from .evidence import build_catalog, select_active_parse


def open_paper(user, document_id, *, parse_id=None):
    parse = select_active_parse(user, document_id, parse_id=parse_id)
    return parse, build_catalog(parse)
