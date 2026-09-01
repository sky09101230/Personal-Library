from io import BytesIO
import hashlib
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from pypdf import PdfWriter

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..artifacts import ArtifactReference, PARSE_ARTIFACT_CONTENT_TYPE, store_parse_artifact
from ..chunking import chunk_document
from ..models import DocumentProcessingJob, LiteratureChunk
from ..parsers import (
    STRUCTURED_PARSE_SCHEMA_VERSION,
    BlockKind,
    ParsedBlock,
    ParsedBoundingBox,
    ParsedDocument,
    ParsedPage,
    ParserUnavailable,
    get_parser,
)
from ..parsers.pypdf_adapter import PyPdfParser
from ..persistence import persist_parsed_document
from ..structure_chunking import chunk_structured_document


class ParserContractTests(SimpleTestCase):
    def test_contract_rejects_missing_page_numbers(self):
        with self.assertRaises(ValueError):
            ParsedDocument(
                parser_name="test",
                parser_version="test-v1",
                pages=(ParsedPage(number=2, text="second"),),
            )

    @patch("apps.literature_processing.parsers.pypdf_adapter.PdfReader")
    def test_pypdf_adapter_preserves_empty_pages_and_neutralizes_output(self, reader_class):
        class FakePage:
            def __init__(self, text=None, error=False):
                self.text = text
                self.error = error

            def extract_text(self):
                if self.error:
                    raise RuntimeError("backend detail must not escape")
                return self.text

        reader_class.return_value.pages = [FakePage("first\r\npage"), FakePage(), FakePage(error=True)]
        reader_class.return_value.metadata = {"/Title": "Title\x00Value", "/Custom": "private"}

        result = PyPdfParser().parse(BytesIO(b"%PDF-test"))

        self.assertIsInstance(result, ParsedDocument)
        self.assertEqual([page.number for page in result.pages], [1, 2, 3])
        self.assertEqual([page.text for page in result.pages], ["first\npage", "", ""])
        self.assertEqual(result.metadata, {"title": "Title Value"})
        self.assertEqual(result.warnings, ("page_3_text_extraction_failed",))
        self.assertNotIn("backend detail", str(result.as_dict()))

    def test_registry_has_explicit_adapter_boundary(self):
        self.assertIsInstance(get_parser("pypdf"), PyPdfParser)
        with self.assertRaises(ParserUnavailable):
            get_parser("mineru")

    def test_v2_contract_keeps_provider_neutral_blocks_and_bbox(self):
        block = ParsedBlock(
            block_id="p0001-b0000-test",
            page_number=1,
            reading_order=0,
            kind=BlockKind.HEADING,
            text="Methods",
            bounding_box=ParsedBoundingBox(10, 20, 900, 80),
            heading_level=1,
            section_path=("Methods",),
            source={"provider": "fake", "source_index": 4},
        )
        document = ParsedDocument(
            parser_name="fake",
            parser_version="fake-v1",
            pages=(ParsedPage(number=1, text="Methods", blocks=(block,)),),
            schema_version=STRUCTURED_PARSE_SCHEMA_VERSION,
        )

        payload = document.as_dict()

        self.assertEqual(payload["schema_version"], "plab.parse.v2")
        self.assertEqual(payload["pages"][0]["blocks"][0]["type"], "heading")
        self.assertEqual(payload["pages"][0]["blocks"][0]["bbox"]["right"], 900)
        self.assertNotIn("mineru", str(payload).lower())

    def test_pypdf_adapter_parses_real_blank_pdf_without_losing_pages(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_blank_page(width=200, height=200)
        pdf = BytesIO()
        writer.write(pdf)
        pdf.seek(0)

        result = PyPdfParser().parse(pdf)

        self.assertEqual([page.number for page in result.pages], [1, 2])
        self.assertEqual([page.text for page in result.pages], ["", ""])


class ChunkingTests(SimpleTestCase):
    def test_chunking_is_deterministic_page_scoped_and_offset_exact(self):
        document = ParsedDocument(
            parser_name="test",
            parser_version="test-v1",
            pages=(
                ParsedPage(number=1, text="Alpha sentence. Beta sentence. Gamma sentence."),
                ParsedPage(number=2, text=""),
                ParsedPage(number=3, text="Third page text."),
            ),
        )

        first = chunk_document(document, max_chars=24, overlap_chars=5)
        second = chunk_document(document, max_chars=24, overlap_chars=5)

        self.assertEqual(first, second)
        self.assertTrue(all(chunk.page_number in (1, 3) for chunk in first))
        self.assertEqual([chunk.sequence for chunk in first], list(range(len(first))))
        for chunk in first:
            page_text = document.pages[chunk.page_number - 1].text
            self.assertEqual(chunk.text, page_text[chunk.start_offset:chunk.end_offset])
            self.assertEqual(chunk.content_sha256, hashlib.sha256(chunk.text.encode("utf-8")).hexdigest())
            self.assertLessEqual(len(chunk.text), 24)

    def test_trailing_whitespace_does_not_repeat_final_chunk(self):
        document = ParsedDocument(
            parser_name="test",
            parser_version="test-v1",
            pages=(
                ParsedPage(number=1, text="Final paragraph.\n\n"),
                ParsedPage(number=2, text=("A" * 1800) + "\n\n" + ("B" * 1800) + "\n\n"),
            ),
        )

        chunks = chunk_document(document, max_chars=2000, overlap_chars=200)
        page_one = [chunk for chunk in chunks if chunk.page_number == 1]
        page_two = [chunk for chunk in chunks if chunk.page_number == 2]

        self.assertEqual(len(page_one), 1)
        self.assertEqual(page_one[0].text, "Final paragraph.")
        self.assertLessEqual(len(page_two), 3)
        self.assertTrue(page_two[-1].text.endswith("B"))

    def test_structure_chunking_preserves_blocks_and_excludes_page_furniture(self):
        def block(order, kind, text, *, section=("Results",), page=1):
            return ParsedBlock(
                block_id=f"p{page:04d}-b{order:04d}",
                page_number=page,
                reading_order=order,
                kind=kind,
                text=text,
                section_path=section,
            )

        table_text = "| A | B |\n" + "| value | result |\n" * 8
        page = ParsedPage(
            number=1,
            text="",
            blocks=(
                block(0, BlockKind.HEADER, "Repeated journal header", section=()),
                block(1, BlockKind.HEADING, "Results"),
                block(2, BlockKind.PARAGRAPH, "Measured response increased."),
                block(3, BlockKind.EQUATION, "$E = mc^2$"),
                block(4, BlockKind.TABLE, table_text),
                block(5, BlockKind.FOOTER, "Page 1", section=()),
            ),
        )
        document = ParsedDocument(
            parser_name="structured-test",
            parser_version="test-v1",
            pages=(page,),
            schema_version=STRUCTURED_PARSE_SCHEMA_VERSION,
        )

        chunks = chunk_structured_document(document, target_chars=80)

        combined = "\n".join(chunk.text for chunk in chunks)
        self.assertNotIn("Repeated journal header", combined)
        self.assertNotIn("Page 1", combined)
        self.assertIn("Measured response increased.\n\n$E = mc^2$", combined)
        table_chunk = next(chunk for chunk in chunks if table_text.strip() in chunk.text)
        self.assertGreater(len(table_chunk.text), 80)
        self.assertEqual(len(table_chunk.source_spans), 1)
        source = page.blocks[4]
        span = table_chunk.source_spans[0]
        self.assertEqual(span["block_id"], source.block_id)
        self.assertEqual(
            table_chunk.text[span["chunk_start"] : span["chunk_end"]],
            source.text[span["block_start"] : span["block_end"]],
        )

    def test_structure_chunking_splits_long_text_at_word_boundary(self):
        text = " ".join(f"word{index}" for index in range(50))
        block = ParsedBlock(
            block_id="p0001-b0000",
            page_number=1,
            reading_order=0,
            kind=BlockKind.PARAGRAPH,
            text=text,
        )
        document = ParsedDocument(
            parser_name="structured-test",
            parser_version="test-v1",
            pages=(ParsedPage(number=1, text=text, blocks=(block,)),),
            schema_version=STRUCTURED_PARSE_SCHEMA_VERSION,
        )

        chunks = chunk_structured_document(document, target_chars=75)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.text.startswith("word") for chunk in chunks))
        self.assertTrue(all(len(chunk.text) <= 75 for chunk in chunks))


class ParsePersistenceTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="parse-test")
        self.canonical = CanonicalDocument.objects.create(title="Parsed paper")
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=user,
            original_name="paper.pdf",
            remote_path="/Literature/paper.pdf",
            sha256="1" * 64,
            size=128,
        )
        self.job = DocumentProcessingJob.objects.create(
            uploaded_document=self.upload,
            status=DocumentProcessingJob.Status.SUCCEEDED,
            stage=DocumentProcessingJob.Stage.COMPLETE,
            pipeline_version="pipeline-v1",
            parser_version="test-parser-v1",
            chunker_version="page-chars-v1",
            prompt_version="overview-v1",
        )
        self.parsed = ParsedDocument(
            parser_name="test",
            parser_version="test-parser-v1",
            pages=(ParsedPage(number=1, text="Traceable page text."), ParsedPage(number=2, text="")),
        )

    def test_store_artifact_uses_source_backend_and_neutral_json(self):
        class FakeStorage:
            name = "nas_webdav"

            def __init__(self):
                self.uploaded = None
                self.namespace = None

            def upload(self, uploaded_file, namespace=""):
                self.uploaded = b"".join(uploaded_file.chunks())
                self.namespace = namespace
                return "/Literature/derived-random.json"

        storage = FakeStorage()
        requested_backends = []

        reference = store_parse_artifact(
            self.upload,
            self.job,
            self.parsed,
            storage_factory=lambda backend: requested_backends.append(backend) or storage,
        )

        payload = json.loads(storage.uploaded)
        self.assertEqual(requested_backends, [self.upload.storage_backend])
        self.assertEqual(storage.namespace, "derived/parses")
        self.assertEqual(payload["pages"][0], {"number": 1, "text": "Traceable page text."})
        self.assertEqual(payload["parser"], {"name": "test", "version": "test-parser-v1"})
        self.assertEqual(reference.path, "/Literature/derived-random.json")
        self.assertEqual(reference.content_type, PARSE_ARTIFACT_CONTENT_TYPE)
        self.assertEqual(reference.sha256, hashlib.sha256(storage.uploaded).hexdigest())
        self.assertEqual(reference.size, len(storage.uploaded))

    def test_persisted_chunks_keep_full_traceability_and_reuse_same_job_result(self):
        calls = []

        def artifact_writer(upload, job, parsed):
            calls.append((upload.pk, job.pk, parsed.schema_version))
            return ArtifactReference(
                storage_backend="nas_webdav",
                path=f"/Literature/{job.run_id}.json",
                sha256="2" * 64,
                content_type=PARSE_ARTIFACT_CONTENT_TYPE,
                size=100,
            )

        document_parse = persist_parsed_document(self.job, self.parsed, artifact_writer=artifact_writer)
        repeated = persist_parsed_document(self.job, self.parsed, artifact_writer=artifact_writer)
        chunk = LiteratureChunk.objects.get(document_parse=document_parse)

        self.assertEqual(repeated.pk, document_parse.pk)
        self.assertEqual(len(calls), 1)
        self.assertEqual(document_parse.page_count, 2)
        self.assertEqual(chunk.page_number, 1)
        self.assertEqual(chunk.uploaded_document, self.upload)
        self.assertEqual(chunk.canonical_document, self.canonical)
        self.assertEqual(chunk.text, "Traceable page text.")
