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
from ..parsers import ParsedDocument, ParsedPage, ParserUnavailable, get_parser
from ..parsers.pypdf_adapter import PyPdfParser
from ..persistence import persist_parsed_document


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

            def upload(self, uploaded_file):
                self.uploaded = b"".join(uploaded_file.chunks())
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
