from dataclasses import dataclass, field
from enum import StrEnum


PARSE_SCHEMA_VERSION = "plab.parse.v1"
STRUCTURED_PARSE_SCHEMA_VERSION = "plab.parse.v2"


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    FIGURE_CAPTION = "figure_caption"
    EQUATION = "equation"
    LIST = "list"
    CODE = "code"
    REFERENCE = "reference"
    HEADER = "header"
    FOOTER = "footer"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ParsedBoundingBox:
    left: float
    top: float
    right: float
    bottom: float
    coordinate_space: str = "normalized_0_1000"
    origin: str = "top_left"

    def __post_init__(self):
        if self.right < self.left or self.bottom < self.top:
            raise ValueError("Bounding box coordinates are invalid.")

    def as_dict(self):
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "coordinate_space": self.coordinate_space,
            "origin": self.origin,
        }


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    block_id: str
    page_number: int
    reading_order: int
    kind: BlockKind
    text: str = ""
    structured_content: dict[str, object] = field(default_factory=dict)
    bounding_box: ParsedBoundingBox | None = None
    heading_level: int | None = None
    section_path: tuple[str, ...] = ()
    source: dict[str, object] = field(default_factory=dict)

    def __post_init__(self):
        if not self.block_id.strip():
            raise ValueError("Block ids must be non-empty.")
        if self.page_number < 1:
            raise ValueError("Block page numbers must start at 1.")
        if self.reading_order < 0:
            raise ValueError("Block reading order must be non-negative.")
        if not isinstance(self.kind, BlockKind):
            raise TypeError("Block kind must use the PLAB BlockKind enum.")
        if not isinstance(self.text, str):
            raise TypeError("Block text must be a string.")
        if self.heading_level is not None and self.heading_level < 1:
            raise ValueError("Heading level must be positive.")

    def as_dict(self):
        payload = {
            "block_id": self.block_id,
            "page_number": self.page_number,
            "reading_order": self.reading_order,
            "type": self.kind.value,
            "text": self.text,
            "structured_content": dict(self.structured_content),
            "section_path": list(self.section_path),
            "source": dict(self.source),
        }
        if self.bounding_box is not None:
            payload["bbox"] = self.bounding_box.as_dict()
        if self.heading_level is not None:
            payload["heading_level"] = self.heading_level
        return payload


@dataclass(frozen=True, slots=True)
class ParsedPage:
    number: int
    text: str
    blocks: tuple[ParsedBlock, ...] = ()

    def __post_init__(self):
        if self.number < 1:
            raise ValueError("Page numbers must start at 1.")
        if not isinstance(self.text, str):
            raise TypeError("Page text must be a string.")
        if any(block.page_number != self.number for block in self.blocks):
            raise ValueError("Every block must belong to its containing page.")
        expected_order = tuple(range(len(self.blocks)))
        if tuple(block.reading_order for block in self.blocks) != expected_order:
            raise ValueError("Page block reading order must be contiguous.")

    def as_dict(self, *, include_blocks=False):
        payload = {"number": self.number, "text": self.text}
        if include_blocks:
            payload["blocks"] = [block.as_dict() for block in self.blocks]
        return payload


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    parser_name: str
    parser_version: str
    pages: tuple[ParsedPage, ...]
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    runtime_info: dict[str, object] = field(default_factory=dict)
    schema_version: str = PARSE_SCHEMA_VERSION

    def __post_init__(self):
        expected_numbers = tuple(range(1, len(self.pages) + 1))
        actual_numbers = tuple(page.number for page in self.pages)
        if actual_numbers != expected_numbers:
            raise ValueError("Parsed pages must be contiguous and start at 1.")
        if self.schema_version not in {PARSE_SCHEMA_VERSION, STRUCTURED_PARSE_SCHEMA_VERSION}:
            raise ValueError(f"Unsupported parse schema: {self.schema_version}")
        if self.schema_version == PARSE_SCHEMA_VERSION and any(page.blocks for page in self.pages):
            raise ValueError("Parse v1 pages cannot contain structured blocks.")
        block_ids = [block.block_id for page in self.pages for block in page.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("Parsed block ids must be unique within a document.")

    def as_dict(self):
        structured = self.schema_version == STRUCTURED_PARSE_SCHEMA_VERSION
        payload = {
            "schema_version": self.schema_version,
            "parser": {"name": self.parser_name, "version": self.parser_version},
            "page_count": len(self.pages),
            "pages": [page.as_dict(include_blocks=structured) for page in self.pages],
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
        }
        if self.runtime_info:
            payload["runtime_info"] = dict(self.runtime_info)
        return payload
