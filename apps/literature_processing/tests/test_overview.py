import json
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..artifacts import ArtifactReference, PARSE_ARTIFACT_CONTENT_TYPE
from ..jobs import enqueue_processing
from ..models import DocumentAnalysis, DocumentParse, DocumentProcessingJob, LiteratureChunk
from ..overview import (
    OVERVIEW_SCHEMA_VERSION,
    OverviewGenerationError,
    build_overview_packet,
    generate_and_persist_overview,
    generate_deepseek_overview,
    overview_input_fingerprint,
)
from ..parsers import ParsedDocument, ParsedPage
from ..persistence import persist_parsed_document
from ..pipeline import process_next_job
from ..versions import PARSER_VERSION, PROMPT_VERSION


def overview_payload(chunk, *, page=None, chunk_id=None):
    return {
        "summary_short": "Short generated summary.",
        "summary": "A longer generated summary grounded in parsed text.",
        "topics": ["general topic"],
        "key_points": [
            {
                "text": "A traceable key point.",
                "evidence": [
                    {
                        "chunk_id": chunk.pk if chunk_id is None else chunk_id,
                        "page": chunk.page_number if page is None else page,
                    }
                ],
            }
        ],
    }


class OverviewTestDataMixin:
    def setUp(self):
        user = get_user_model().objects.create_user(username="overview-test")
        self.canonical = CanonicalDocument.objects.create(
            title="Overview paper",
            abstract="Original bibliographic abstract.",
        )
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=user,
            original_name="overview.pdf",
            remote_path="/Literature/overview.pdf",
            sha256="7" * 64,
            size=128,
        )
        self.document_parse, self.chunk = self.create_parse("first", "Parsed evidence on page two.", 2)

    def create_parse(self, suffix, text, page_number):
        job = DocumentProcessingJob.objects.create(
            uploaded_document=self.upload,
            status=DocumentProcessingJob.Status.SUCCEEDED,
            stage=DocumentProcessingJob.Stage.COMPLETE,
            pipeline_version=f"pipeline-{suffix}",
            parser_version=PARSER_VERSION,
            chunker_version="page-chars-v1",
            prompt_version=PROMPT_VERSION,
        )
        document_parse = DocumentParse.objects.create(
            job=job,
            parser_name="pypdf",
            parser_version=PARSER_VERSION,
            schema_version="plab.parse.v1",
            page_count=page_number,
            artifact_storage_backend=self.upload.storage_backend,
            artifact_path=f"/Literature/{job.run_id}.json",
            artifact_sha256="8" * 64,
            artifact_size=100,
        )
        chunk = LiteratureChunk.objects.create(
            document_parse=document_parse,
            chunk_key=f"p{page_number:04d}-c0000-{suffix}",
            sequence=0,
            page_number=page_number,
            page_sequence=0,
            start_offset=0,
            end_offset=len(text),
            text=text,
            content_sha256="9" * 64,
        )
        return document_parse, chunk

    def create_analysis(self, payload):
        return DocumentAnalysis.objects.create(
            document_parse=self.document_parse,
            analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
            schema_version=OVERVIEW_SCHEMA_VERSION,
            provider="test",
            model="test-model",
            prompt_version=PROMPT_VERSION,
            input_fingerprint="a" * 64,
            payload=payload,
        )


class OverviewValidationTests(OverviewTestDataMixin, TestCase):
    def test_valid_overview_is_saved_separately_from_original_abstract(self):
        analysis = self.create_analysis(overview_payload(self.chunk))

        self.canonical.refresh_from_db()
        self.assertEqual(analysis.payload["key_points"][0]["evidence"][0]["page"], 2)
        self.assertEqual(self.canonical.abstract, "Original bibliographic abstract.")

    def test_nonexistent_or_cross_parse_evidence_is_rejected(self):
        other_parse, other_chunk = self.create_parse("second", "Other parse evidence.", 1)
        invalid_payloads = (
            overview_payload(self.chunk, chunk_id=999999),
            overview_payload(self.chunk, chunk_id=other_chunk.pk, page=other_chunk.page_number),
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                self.create_analysis(payload)

        self.assertFalse(DocumentAnalysis.objects.exists())
        self.assertNotEqual(other_parse.pk, self.document_parse.pk)

    def test_evidence_page_must_match_chunk_page(self):
        with self.assertRaises(ValidationError):
            self.create_analysis(overview_payload(self.chunk, page=1))

        self.assertFalse(DocumentAnalysis.objects.exists())

    def test_payload_rejects_domain_specific_extra_fields(self):
        payload = {**overview_payload(self.chunk), "genes": ["example"]}

        with self.assertRaises(ValidationError):
            self.create_analysis(payload)


class OverviewProviderTests(OverviewTestDataMixin, TestCase):
    @patch.dict(
        "os.environ",
        {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_OVERVIEW_MODEL": "overview-model"},
        clear=False,
    )
    def test_provider_uses_structured_json_and_persists_provenance(self):
        packet = build_overview_packet(self.document_parse)
        payload = overview_payload(self.chunk)
        calls = []

        def request_func(url, body, api_key, timeout):
            calls.append((url, body, api_key, timeout))
            return {
                "model": "returned-model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(payload)},
                    }
                ],
            }

        generated = generate_deepseek_overview(packet, request_func=request_func)
        analysis = generate_and_persist_overview(self.document_parse, generator=lambda value: generated)

        self.assertEqual(calls[0][1]["response_format"], {"type": "json_object"})
        self.assertEqual(calls[0][2], "test-key")
        self.assertEqual(analysis.provider, "deepseek")
        self.assertEqual(analysis.model, "returned-model")
        self.assertEqual(analysis.prompt_version, PROMPT_VERSION)
        self.assertEqual(analysis.input_fingerprint, overview_input_fingerprint(packet))
        self.assertEqual(analysis.payload, payload)

    @patch.dict("os.environ", {}, clear=True)
    def test_provider_requires_configuration(self):
        with self.assertRaises(OverviewGenerationError) as context:
            generate_deepseek_overview(build_overview_packet(self.document_parse))

        self.assertEqual(context.exception.code, "disabled")


class OverviewPipelineTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="overview-pipeline")
        self.canonical = CanonicalDocument.objects.create(
            title="Pipeline paper",
            abstract="Untouched abstract.",
        )
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=user,
            original_name="pipeline.pdf",
            remote_path="/Literature/pipeline.pdf",
            sha256="b" * 64,
            size=128,
        )

    @staticmethod
    def artifact_writer(upload, job, parsed):
        return ArtifactReference(
            storage_backend=upload.storage_backend,
            path=f"/Literature/{job.run_id}.json",
            sha256="c" * 64,
            content_type=PARSE_ARTIFACT_CONTENT_TYPE,
            size=100,
        )

    @staticmethod
    def parsed_document():
        return ParsedDocument(
            parser_name="pypdf",
            parser_version=PARSER_VERSION,
            pages=(ParsedPage(number=1, text="Pipeline evidence."),),
        )

    def run_pipeline(self, overview_processor):
        return process_next_job(
            downloader=lambda upload: BytesIO(b"source"),
            parser=lambda file_obj, parser_name: self.parsed_document(),
            persister=lambda job, parsed: persist_parsed_document(
                job,
                parsed,
                artifact_writer=self.artifact_writer,
            ),
            overview_processor=overview_processor,
        )

    def test_pipeline_saves_valid_overview_before_success(self):
        job, _ = enqueue_processing(self.upload)

        def overview_processor(document_parse):
            chunk = document_parse.chunks.get()
            return generate_and_persist_overview(
                document_parse,
                generator=lambda packet: {
                    "payload": overview_payload(chunk),
                    "provider": "test",
                    "model": "test-model",
                    "prompt_version": PROMPT_VERSION,
                    "attempt_count": 1,
                },
            )

        processed = self.run_pipeline(overview_processor)

        processed.refresh_from_db()
        self.canonical.refresh_from_db()
        self.assertEqual(processed.pk, job.pk)
        self.assertEqual(processed.status, DocumentProcessingJob.Status.SUCCEEDED)
        self.assertTrue(DocumentAnalysis.objects.filter(document_parse__job=job).exists())
        self.assertEqual(self.canonical.abstract, "Untouched abstract.")

    def test_provider_failure_marks_overview_stage_failed_and_keeps_parse(self):
        job, _ = enqueue_processing(self.upload)

        def fail_overview(document_parse):
            raise OverviewGenerationError("provider_down", "secret provider detail")

        with self.assertLogs("apps.literature_processing.pipeline", level="ERROR"):
            processed = self.run_pipeline(fail_overview)

        processed.refresh_from_db()
        self.canonical.refresh_from_db()
        self.assertEqual(processed.pk, job.pk)
        self.assertEqual(processed.status, DocumentProcessingJob.Status.FAILED)
        self.assertEqual(processed.stage, DocumentProcessingJob.Stage.OVERVIEW)
        self.assertEqual(processed.error_code, "overview_provider_down")
        self.assertNotIn("secret", processed.error_message)
        self.assertTrue(DocumentParse.objects.filter(job=job).exists())
        self.assertTrue(LiteratureChunk.objects.filter(document_parse__job=job).exists())
        self.assertEqual(self.canonical.abstract, "Untouched abstract.")
