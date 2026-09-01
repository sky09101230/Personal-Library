from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase
from pypdf import PdfWriter

from ..parsers import ParsedDocument, ParsedPage, ParserOutput
from ..parsers.mineru import MinerUAPIError, MinerUConfigurationError
from ..parsers.mineru.parser import MinerUParser
from ..parsers.mineru.types import MinerURawResult
from ..parsers.pypdf_adapter import PyPdfParser
from ..parsers.registry import parse_pdf


def two_page_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    target = BytesIO()
    writer.write(target)
    target.seek(0)
    return target


class MinerUParserTests(SimpleTestCase):
    def test_parser_orchestrates_page_count_client_adapter_and_raw_bundle(self):
        calls = []
        raw_result = MinerURawResult(
            batch_id="batch",
            model_version="vlm",
            page_count=2,
            segments=(),
            runtime_info={},
        )
        document = ParsedDocument(
            parser_name="mineru",
            parser_version="mineru-api-v4-vlm",
            pages=(ParsedPage(1, ""), ParsedPage(2, "")),
            schema_version="plab.parse.v2",
        )
        client = type("Client", (), {
            "parse_pdf": lambda self, file_obj, **kwargs: calls.append(kwargs) or raw_result
        })()
        adapter = type("Adapter", (), {"convert": lambda self, value: document})()

        output = MinerUParser(client=client, adapter=adapter).parse(two_page_pdf())

        self.assertIsInstance(output, ParserOutput)
        self.assertEqual(calls[0]["page_count"], 2)
        self.assertTrue(calls[0]["data_id"].startswith("plab-"))
        self.assertEqual(output.document, document)
        self.assertEqual(output.raw_artifact.content_type, "application/vnd.plab.mineru-result+zip")

    @patch.dict("os.environ", {}, clear=True)
    def test_explicit_mineru_parser_without_token_has_clear_error(self):
        with self.assertRaises(MinerUConfigurationError) as context:
            MinerUParser().parse(two_page_pdf())

        self.assertEqual(context.exception.code, "mineru_configuration")

    @patch.dict("os.environ", {}, clear=True)
    def test_registry_does_not_hide_missing_token_with_fallback(self):
        with self.assertRaises(MinerUConfigurationError):
            parse_pdf(two_page_pdf(), parser_name="mineru")

    @patch.object(MinerUParser, "parse")
    @patch.object(PyPdfParser, "parse")
    def test_runtime_mineru_failure_falls_back_to_pypdf(self, pypdf_parse, mineru_parse):
        mineru_parse.side_effect = MinerUAPIError("provider unavailable")
        pypdf_parse.return_value = ParsedDocument(
            parser_name="pypdf",
            parser_version="pypdf-test",
            pages=(ParsedPage(1, "fallback"),),
        )

        parsed = parse_pdf(BytesIO(b"source"), parser_name="mineru")

        self.assertEqual(parsed.parser_name, "pypdf")
        self.assertIn("mineru_failed_fallback_pypdf", parsed.warnings)
        self.assertTrue(parsed.runtime_info["fallback_used"])
        self.assertEqual(parsed.runtime_info["fallback_reason"], "mineru_api")
