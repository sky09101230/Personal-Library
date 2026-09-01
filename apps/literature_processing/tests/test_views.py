from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..models import DocumentAnalysis, DocumentParse, DocumentProcessingJob, LiteratureChunk
from ..overview import OVERVIEW_SCHEMA_VERSION
from ..versions import CHUNKER_VERSION, PARSER_VERSION, PROMPT_VERSION


class LiteratureDetailViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="detail-test",
            password="Strong-pass-1234",
        )
        self.literature = CanonicalDocument.objects.create(
            title="Traceable literature detail",
            authors=[{"name": "Ada Lovelace"}],
            journal="Journal of Tests",
            publication_year=2026,
            doi="10.1000/detail.1",
            abstract="Original bibliographic abstract.",
        )
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.literature,
            uploader=self.user,
            original_name="detail.pdf",
            remote_path="/Literature/detail.pdf",
            sha256="d" * 64,
            size=128,
        )
        self.url = reverse("literature-detail", args=[self.literature.pk])

    def create_job(self, *, status, stage, suffix):
        return DocumentProcessingJob.objects.create(
            uploaded_document=self.upload,
            status=status,
            stage=stage,
            pipeline_version=f"pipeline-{suffix}",
            parser_version=PARSER_VERSION,
            chunker_version=CHUNKER_VERSION,
            prompt_version=PROMPT_VERSION,
            error_code="overview_failed" if status == DocumentProcessingJob.Status.FAILED else "",
            error_message=(
                "Literature processing failed during overview."
                if status == DocumentProcessingJob.Status.FAILED
                else ""
            ),
        )

    def create_result(self, suffix="success"):
        job = self.create_job(
            status=DocumentProcessingJob.Status.SUCCEEDED,
            stage=DocumentProcessingJob.Stage.COMPLETE,
            suffix=suffix,
        )
        document_parse = DocumentParse.objects.create(
            job=job,
            parser_name="pypdf",
            parser_version=PARSER_VERSION,
            schema_version="plab.parse.v1",
            page_count=2,
            artifact_storage_backend=self.upload.storage_backend,
            artifact_path=f"/Literature/{job.run_id}.json",
            artifact_sha256="e" * 64,
            artifact_size=100,
        )
        text = "Evidence preserved from page two."
        chunk = LiteratureChunk.objects.create(
            document_parse=document_parse,
            chunk_key=f"p0002-c0000-{suffix}",
            sequence=0,
            page_number=2,
            page_sequence=0,
            start_offset=0,
            end_offset=len(text),
            text=text,
            content_sha256="f" * 64,
        )
        analysis = DocumentAnalysis.objects.create(
            document_parse=document_parse,
            analysis_type=DocumentAnalysis.AnalysisType.OVERVIEW,
            schema_version=OVERVIEW_SCHEMA_VERSION,
            provider="test-provider",
            model="test-model",
            prompt_version=PROMPT_VERSION,
            input_fingerprint="1" * 64,
            payload={
                "summary_short": "Short overview.",
                "summary": "Long overview grounded in the parsed page.",
                "topics": ["traceability"],
                "key_points": [
                    {
                        "text": "Traceable point.",
                        "evidence": [{"chunk_id": chunk.pk, "page": 2}],
                    }
                ],
            },
        )
        return job, document_parse, chunk, analysis

    def test_detail_requires_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('login')}?next={self.url}")

    def test_unprocessed_detail_keeps_original_metadata_and_pdf_actions(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, "Traceable literature detail")
        self.assertContains(response, "Original bibliographic abstract.")
        self.assertContains(response, "尚未排队")
        self.assertContains(response, "暂无 AI Overview")
        self.assertContains(response, reverse("view-document", args=[self.upload.pk]))

    def test_queued_and_failed_states_are_visible(self):
        queued = self.create_job(
            status=DocumentProcessingJob.Status.QUEUED,
            stage=DocumentProcessingJob.Stage.QUEUED,
            suffix="queued",
        )
        self.client.force_login(self.user)

        queued_response = self.client.get(self.url)
        queued.status = DocumentProcessingJob.Status.FAILED
        queued.stage = DocumentProcessingJob.Stage.OVERVIEW
        queued.error_message = "Literature processing failed during overview."
        queued.save(update_fields=("status", "stage", "error_message", "updated_at"))
        failed_response = self.client.get(self.url)

        self.assertContains(queued_response, "等待处理")
        self.assertContains(failed_response, "处理失败")
        self.assertContains(failed_response, "Literature processing failed during overview.")
        self.assertTrue(UploadedDocument.objects.filter(pk=self.upload.pk).exists())

    def test_completed_detail_shows_overview_parsed_text_and_pdf_page_evidence(self):
        job, document_parse, chunk, analysis = self.create_result()
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        evidence_url = f"{reverse('view-document', args=[self.upload.pk])}#page=2"
        self.assertEqual(response.context["latest_job"], job)
        self.assertEqual(response.context["result_parse"], document_parse)
        self.assertEqual(response.context["overview"], analysis)
        self.assertContains(response, "处理完成")
        self.assertContains(response, "Short overview.")
        self.assertContains(response, "traceability")
        self.assertContains(response, "Traceable point.")
        self.assertContains(response, evidence_url)
        self.assertContains(response, "PDF 第 2 页")
        self.assertContains(response, f'id="chunk-{chunk.pk}"')
        self.assertContains(response, "Evidence preserved from page two.")

    def test_latest_failure_does_not_hide_previous_successful_result(self):
        _, _, _, analysis = self.create_result("old")
        failed = self.create_job(
            status=DocumentProcessingJob.Status.FAILED,
            stage=DocumentProcessingJob.Stage.OVERVIEW,
            suffix="new-failure",
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.context["latest_job"], failed)
        self.assertEqual(response.context["overview"], analysis)
        self.assertContains(response, "处理失败")
        self.assertContains(response, "Short overview.")

    def test_library_links_to_processing_detail(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("library"))

        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, "Traceable literature detail")
