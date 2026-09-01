from dataclasses import dataclass, field


PARSE_SCHEMA_VERSION = "plab.parse.v1"


@dataclass(frozen=True, slots=True)
class ParsedPage:
    number: int
    text: str

    def __post_init__(self):
        if self.number < 1:
            raise ValueError("Page numbers must start at 1.")
        if not isinstance(self.text, str):
            raise TypeError("Page text must be a string.")

    def as_dict(self):
        return {"number": self.number, "text": self.text}


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    parser_name: str
    parser_version: str
    pages: tuple[ParsedPage, ...]
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    schema_version: str = PARSE_SCHEMA_VERSION

    def __post_init__(self):
        expected_numbers = tuple(range(1, len(self.pages) + 1))
        actual_numbers = tuple(page.number for page in self.pages)
        if actual_numbers != expected_numbers:
            raise ValueError("Parsed pages must be contiguous and start at 1.")
        if self.schema_version != PARSE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported parse schema: {self.schema_version}")

    def as_dict(self):
        return {
            "schema_version": self.schema_version,
            "parser": {"name": self.parser_name, "version": self.parser_version},
            "page_count": len(self.pages),
            "pages": [page.as_dict() for page in self.pages],
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
        }

