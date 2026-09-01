from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..models import DocumentAnalysis, DocumentParse, DocumentProcessingJob, LiteratureChunk


class LiteratureProcessingModelTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="processor-test")
        self.canonical = CanonicalDocument.objects.create(title="Traceable paper")
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=user,
            original_name="paper.pdf",
            remote_path="/Literature/paper.pdf",
            sha256="a" * 64,
            size=128,
        )

    def create_job(self, *, status=DocumentProcessingJob.Status.SUCCEEDED, suffix="1"):
        return DocumentProcessingJob.objects.create(
            uploaded_document=self.upload,
            status=status,
            stage=(
                DocumentProcessingJob.Stage.COMPLETE
                if status == DocumentProcessingJob.Status.SUCCEEDED
                else DocumentProcessingJob.Stage.QUEUED
            ),
            pipeline_version=f"pipeline-{suffix}",
            parser_version=f"pypdf-{suffix}",
            chunker_version=f"chars-{suffix}",
            prompt_version=f"overview-{suffix}",
        )

    def create_parse(self, job, *, suffix="1"):
        return DocumentParse.objects.create(
            job=job,
            parser_name="pypdf",
            parser_version=job.parser_version,
            schema_version="plab-parse-v1",
            page_count=2,
            artifact_storage_backend="nas_webdav",
            artifact_path=f"/derived/{job.run_id}/parse-{suffix}.json",
            artifact_sha256=suffix * 64,
            artifact_size=256,
        )

    def test_chunk_traces_to_parse_upload_canonical_and_page(self):
        document_parse = self.create_parse(self.create_job())
        chunk = LiteratureChunk.objects.create(
            document_parse=document_parse,
            chunk_key="p0002-c0001-abc",
            sequence=0,
            page_number=2,
            page_sequence=0,
            start_offset=0,
            end_offset=12,
            text="Page 2 text",
            content_sha256="b" * 64,
        )

        self.assertEqual(chunk.document_parse, document_parse)
        self.assertEqual(chunk.uploaded_document, self.upload)
        self.assertEqual(chunk.canonical_document, self.canonical)
        self.assertEqual(chunk.page_number, 2)

    def test_only_one_active_job_is_allowed_per_upload(self):
        first = self.create_job(status=DocumentProcessingJob.Status.QUEUED)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_job(status=DocumentProcessingJob.Status.RUNNING, suffix="2")

        self.assertEqual(DocumentProcessingJob.objects.get(), first)

    def test_reprocessing_preserves_old_parse_chunks_and_analysis(self):
        first_parse = self.create_parse(self.create_job(suffix="1"), suffix="1")
        second_parse = self.create_parse(self.create_job(suffix="2"), suffix="2")
        first_chunk = LiteratureChunk.objects.create(
            document_parse=first_parse,
            chunk_key="p0001-c0001-old",
            sequence=0,
            page_number=1,
            page_sequence=0,
            start_offset=0,
            end_offset=3,
            text="old",
            content_sha256="c" * 64,
        )
        DocumentAnalysis.objects.create(
            document_parse=first_parse,
            analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
            schema_version="overview-v1",
            provider="test",
            model="test-model",
            prompt_version="overview-1",
            input_fingerprint="d" * 64,
            payload={
                "summary_short": "Old summary.",
                "summary": "Old generated summary.",
                "topics": ["testing"],
                "key_points": [
                    {
                        "text": "Old key point.",
                        "evidence": [{"chunk_id": first_chunk.pk, "page": first_chunk.page_number}],
                    }
                ],
            },
        )

        self.assertEqual(DocumentParse.objects.count(), 2)
        self.assertTrue(LiteratureChunk.objects.filter(pk=first_chunk.pk, document_parse=first_parse).exists())
        self.assertTrue(DocumentAnalysis.objects.filter(document_parse=first_parse).exists())
        self.assertFalse(second_parse.chunks.exists())

    def test_derived_rows_do_not_block_existing_upload_deletion(self):
        document_parse = self.create_parse(self.create_job())
        LiteratureChunk.objects.create(
            document_parse=document_parse,
            chunk_key="p0001-c0001-delete",
            sequence=0,
            page_number=1,
            page_sequence=0,
            start_offset=0,
            end_offset=6,
            text="delete",
            content_sha256="e" * 64,
        )

        self.upload.delete()

        self.assertFalse(DocumentProcessingJob.objects.exists())
        self.assertFalse(DocumentParse.objects.exists())
        self.assertFalse(LiteratureChunk.objects.exists())
        self.assertTrue(CanonicalDocument.objects.filter(pk=self.canonical.pk).exists())
