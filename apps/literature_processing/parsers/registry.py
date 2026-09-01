from dataclasses import replace
from typing import Protocol

from .contracts import ParsedDocument, ParserOutput
from .mineru import MinerUConfigurationError, MinerUParser
from .pypdf_adapter import PyPdfParser


class DocumentParser(Protocol):
    name: str
    parser_version: str

    def parse(self, file_obj) -> ParsedDocument | ParserOutput: ...


class ParserUnavailable(ValueError):
    pass


_PARSERS = {"pypdf": PyPdfParser, "mineru": MinerUParser}


def get_parser(name="pypdf") -> DocumentParser:
    try:
        parser_class = _PARSERS[name]
    except KeyError as exc:
        raise ParserUnavailable(f"Unsupported parser: {name}") from exc
    return parser_class()


def parse_pdf(file_obj, parser_name="pypdf"):
    try:
        return get_parser(parser_name).parse(file_obj)
    except MinerUConfigurationError:
        raise
    except Exception as primary_error:
        if parser_name == "pypdf":
            raise
        file_obj.seek(0)
        fallback = get_parser("pypdf").parse(file_obj)
        return replace(
            fallback,
            warnings=tuple(dict.fromkeys((*fallback.warnings, f"{parser_name}_failed_fallback_pypdf"))),
            runtime_info={
                **fallback.runtime_info,
                "requested_parser": parser_name,
                "actual_parser": "pypdf",
                "fallback_used": True,
                "fallback_reason": getattr(primary_error, "code", "parser_failed"),
            },
        )
