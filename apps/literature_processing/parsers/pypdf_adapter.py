from importlib.metadata import version

from pypdf import PdfReader

from .contracts import ParsedDocument, ParsedPage


class PyPdfParser:
    name = "pypdf"
    parser_version = f"pypdf-{version('pypdf')}"

    _METADATA_FIELDS = {
        "/Title": "title",
        "/Author": "author",
        "/Subject": "subject",
        "/Keywords": "keywords",
        "/Creator": "creator",
        "/Producer": "producer",
        "/CreationDate": "creation_date",
        "/ModDate": "modification_date",
    }

    def parse(self, file_obj):
        reader = PdfReader(file_obj)
        warnings = []
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
                warnings.append(f"page_{number}_text_extraction_failed")
            pages.append(ParsedPage(number=number, text=_normalize_text(text)))

        metadata = {}
        for source_name, neutral_name in self._METADATA_FIELDS.items():
            value = (reader.metadata or {}).get(source_name)
            if value is not None:
                metadata[neutral_name] = _normalize_text(str(value)).strip()

        return ParsedDocument(
            parser_name=self.name,
            parser_version=self.parser_version,
            pages=tuple(pages),
            metadata=metadata,
            warnings=tuple(warnings),
        )


def _normalize_text(value):
    return value.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")

