from typing import Protocol

from .contracts import ParsedDocument
from .pypdf_adapter import PyPdfParser


class DocumentParser(Protocol):
    name: str
    parser_version: str

    def parse(self, file_obj) -> ParsedDocument: ...


class ParserUnavailable(ValueError):
    pass


_PARSERS = {"pypdf": PyPdfParser}


def get_parser(name="pypdf") -> DocumentParser:
    try:
        parser_class = _PARSERS[name]
    except KeyError as exc:
        raise ParserUnavailable(f"Unsupported parser: {name}") from exc
    return parser_class()


def parse_pdf(file_obj, parser_name="pypdf"):
    return get_parser(parser_name).parse(file_obj)

