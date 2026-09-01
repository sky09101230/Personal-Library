import os

from .chunking import CHUNKER_VERSION
from .parsers.mineru.parser import MinerUParser
from .parsers.pypdf_adapter import PyPdfParser
from .structure_chunking import STRUCTURE_CHUNKER_VERSION


DEFAULT_PARSER_NAME = PyPdfParser.name
PIPELINE_VERSION = "literature-overview-v1"
PARSER_NAME = DEFAULT_PARSER_NAME
PARSER_VERSION = PyPdfParser.parser_version
PROMPT_VERSION = "overview-v1"
MINERU_PIPELINE_VERSION = "literature-mineru-v1"


def versions_for(parser_name):
    if parser_name == PyPdfParser.name:
        return {
            "pipeline_version": PIPELINE_VERSION,
            "parser_version": PARSER_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "prompt_version": PROMPT_VERSION,
        }
    if parser_name == MinerUParser.name:
        model_version = os.environ.get("MINERU_MODEL_VERSION", "vlm").strip() or "vlm"
        if model_version not in {"vlm", "pipeline"}:
            raise ValueError("MINERU_MODEL_VERSION must be vlm or pipeline.")
        return {
            "pipeline_version": MINERU_PIPELINE_VERSION,
            "parser_version": f"{MinerUParser.parser_version}-{model_version}",
            "chunker_version": STRUCTURE_CHUNKER_VERSION,
            "prompt_version": PROMPT_VERSION,
        }
    raise ValueError(f"Unsupported parser: {parser_name}")


def current_versions():
    return versions_for(DEFAULT_PARSER_NAME)
