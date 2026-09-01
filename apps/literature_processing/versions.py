from .chunking import CHUNKER_VERSION
from .parsers.pypdf_adapter import PyPdfParser


PIPELINE_VERSION = "literature-overview-v1"
PARSER_NAME = PyPdfParser.name
PARSER_VERSION = PyPdfParser.parser_version
PROMPT_VERSION = "overview-v1"


def current_versions():
    return {
        "pipeline_version": PIPELINE_VERSION,
        "parser_version": PARSER_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "prompt_version": PROMPT_VERSION,
    }
