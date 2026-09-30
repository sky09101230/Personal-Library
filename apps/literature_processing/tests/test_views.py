from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from ..evidence import Evidence, EvidenceCatalog

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
        self.status_url = reverse("literature-processing-status", args=[self.literature.pk])

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
            raw_artifact_storage_backend=self.upload.storage_backend,
            raw_artifact_path=f"/Literature/{job.run_id}-raw.zip",
            raw_artifact_sha256="a" * 64,
            raw_artifact_content_type="application/vnd.plab.mineru-result+zip",
            raw_artifact_size=200,
            runtime_info={
                "model_version": "vlm",
                "batch_id": "batch-test",
                "page_ranges": ["1-2"],
            },
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
            end_page_number=2,
            section_path=["Results"],
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
                "chinese_translation": {
                    "summary_short": "简短综述。",
                    "summary": "基于解析页面的中文翻译。",
                    "topics": ["可追溯性"],
                    "key_points": [
                        {
                            "text": "可追溯的中文结论。",
                            "evidence": [{"chunk_id": chunk.pk, "page": 2}],
                        }
                    ],
                },
            },
        )
        return job, document_parse, chunk, analysis

    def test_detail_requires_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('login')}?next={self.url}")

        status_response = self.client.get(self.status_url)
        self.assertEqual(status_response.status_code, 302)
        self.assertEqual(status_response.url, f"{reverse('login')}?next={self.status_url}")

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
        self.assertContains(queued_response, self.status_url)
        self.assertContains(queued_response, "setInterval(refresh, 2000)")
        self.assertContains(failed_response, "处理失败")
        self.assertContains(failed_response, "Literature processing failed during overview.")
        self.assertTrue(UploadedDocument.objects.filter(pk=self.upload.pk).exists())

    def test_processing_status_endpoint_reports_live_page_progress(self):
        job = self.create_job(
            status=DocumentProcessingJob.Status.RUNNING,
            stage=DocumentProcessingJob.Stage.PARSE,
            suffix="progress",
        )
        job.parser_name = "mineru"
        job.queue_lane = DocumentProcessingJob.QueueLane.REALTIME
        job.provider_state = "running"
        job.provider_batch_id = "batch-status"
        job.progress_current = 12
        job.progress_total = 37
        job.progress_unit = "pages"
        job.save(
            update_fields=(
                "parser_name",
                "queue_lane",
                "provider_state",
                "provider_batch_id",
                "progress_current",
                "progress_total",
                "progress_unit",
                "updated_at",
            )
        )
        self.client.force_login(self.user)

        response = self.client.get(self.status_url)
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["job_id"], job.pk)
        self.assertEqual(payload["stage"], "MinerU 解析中")
        self.assertEqual(payload["provider_state"], "running")
        self.assertEqual(payload["parser_name"], "mineru")
        self.assertEqual(payload["queue_lane"], "realtime")
        self.assertEqual(payload["progress_current"], 12)
        self.assertEqual(payload["progress_total"], 37)
        self.assertEqual(payload["progress_percent"], 32)
        self.assertFalse(payload["terminal"])

    def test_processing_status_endpoint_reports_no_job_and_terminal_failure(self):
        self.client.force_login(self.user)

        empty = self.client.get(self.status_url).json()
        failed_job = self.create_job(
            status=DocumentProcessingJob.Status.FAILED,
            stage=DocumentProcessingJob.Stage.PARSE,
            suffix="status-failed",
        )
        failed_job.provider_state = "failed"
        failed_job.error_message = "Literature processing failed during parse."
        failed_job.save(update_fields=("provider_state", "error_message", "updated_at"))
        failed = self.client.get(self.status_url).json()

        self.assertEqual(empty["status"], "not_queued")
        self.assertTrue(empty["terminal"])
        self.assertEqual(failed["job_id"], failed_job.pk)
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed["failed"])
        self.assertTrue(failed["terminal"])
        self.assertEqual(failed["error_message"], "Literature processing failed during parse.")

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
        self.assertContains(response, "简短综述。")
        self.assertContains(response, "traceability")
        self.assertContains(response, "Traceable point.")
        self.assertContains(response, 'data-overview-language="en"')
        self.assertContains(response, 'data-overview-language="zh"')
        self.assertContains(response, 'id="overview-panel-zh"')
        self.assertContains(response, "PDF page 2")
        self.assertContains(response, evidence_url)
        self.assertContains(response, "PDF 第 2 页")
        self.assertContains(response, f'id="chunk-{chunk.pk}"')
        self.assertContains(response, "Evidence preserved from page two.")
        self.assertContains(response, "Model")
        self.assertContains(response, "vlm")
        self.assertContains(response, "batch-test")
        self.assertContains(response, "1-2")
        self.assertContains(response, "Results")
        self.assertContains(response, 'id="paper-chat-shell"')
        self.assertContains(response, 'id="paper-chat-messages"')
        self.assertContains(response, 'data-messages-base=')
        self.assertContains(response, 'data-delete-base=')
        self.assertContains(response, 'data-list-url=')
        self.assertContains(response, 'id="paper-chat-history-list"')
        self.assertContains(response, 'chat-history-delete')
        self.assertContains(response, '确定删除对话')
        self.assertContains(response, "新对话")
        self.assertContains(response, 'data-status-url=')
        self.assertContains(response, 'id="skeleton-generation-progress"')
        self.assertContains(response, "正在加载对话历史")
        self.assertContains(response, "正在检索当前论文 Evidence")
        self.assertContains(response, "chatElapsedTimer")
        self.assertContains(response, "messages.querySelector('.chat-message-pending')")
        self.assertContains(response, "Ctrl/⌘ + Enter")

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

    def test_legacy_single_language_overview_remains_visible_without_switch(self):
        _, _, _, analysis = self.create_result("legacy")
        analysis.schema_version = "plab.overview.v1"
        analysis.payload.pop("chinese_translation")
        analysis.save(update_fields=("schema_version", "payload"))
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, "Short overview.")
        self.assertNotContains(response, "data-overview-language")

    def test_library_links_to_processing_detail(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("library"))

        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, "Traceable literature detail")

    def test_library_uses_overview_topics_and_expands_remaining_labels(self):
        _, _, _, overview = self.create_result()
        topics = ["Polarization multiplexing", "Optical neural networks", "Metasurfaces", "Imaging and classification", "Optical intelligence"]
        overview.payload["topics"] = topics
        overview.payload["chinese_translation"]["topics"] = ["主题一", "主题二", "主题三", "主题四", "主题五"]
        overview.save()
        self.literature.ai_tags = ["metadata-tag-must-not-appear"]
        self.literature.save()
        # A newer failed processing job must not hide the usable Overview topics.
        self.create_job(status="failed", stage="overview", suffix="new-failed")
        self.client.force_login(self.user)
        for url in (reverse("library"), reverse("upload-history"), reverse("home")):
            response = self.client.get(url)
            self.assertContains(response, "展开全部（5）")
            for topic in topics:
                self.assertContains(response, topic, count=1)
            self.assertNotContains(response, "metadata-tag-must-not-appear")

    def test_document_info_is_first_tab_and_default_panel(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertLess(html.index('id="tab-overview"'), html.index('id="tab-intelligence"'))
        self.assertContains(response, 'aria-controls="paper-overview" aria-selected="true"')
        self.assertContains(response, "hash : 'paper-overview'")
        self.assertContains(response, "hash.startsWith('chunk-') ? 'parsed-content'")

    @patch('apps.literature_processing.views.build_catalog')
    def test_skeleton_displays_images_matched_to_its_cited_caption(self, catalog_builder):
        from ..skeleton import SECTION_KEYS
        _, document_parse, _, _ = self.create_result()
        self.literature.index_status = 'published'
        self.literature.save()
        old = Evidence('ev1:old', 'figure', document_parse.pk, document_parse.artifact_sha256, '', (1,),
                       figure_label='2', asset_handle={'segment_index': 0, 'asset_path': 'fig2.jpg'}, caption_evidence_ids=('caption2',))
        caption = Evidence('caption3', 'text', document_parse.pk, document_parse.artifact_sha256, 'Fig. 3. Simulation.', (2,))
        parts = [Evidence(f'fig3-{n}', 'figure', document_parse.pk, document_parse.artifact_sha256, '', (2,),
                         figure_label='3', asset_handle={'segment_index': 0, 'asset_path': f'fig3-{n}.jpg'},
                         caption_evidence_ids=('caption3',)) for n in range(2)]
        catalog_builder.return_value = EvidenceCatalog(document_parse, [old, caption, *parts])
        claim = {'text': '图3展示模拟结果。', 'evidence_ids': ['caption3'], 'kind': 'interpretation'}
        DocumentAnalysis.objects.create(document_parse=document_parse, analysis_type='paper_skeleton',
            schema_version='personal.paper-skeleton.v1', provider='test', model='test', prompt_version='test', input_fingerprint='c'*64,
            payload={'language': 'zh-CN', 'sections': {key: {'status': 'supported', 'claims': [claim]} for key in SECTION_KEYS},
                     'figures': [{'evidence_id': old.evidence_id, 'status': 'supported', 'claims': [claim]}],
                     'limitations': [], 'coverage': {}})
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'Fig. 3 · 图示解读')
        self.assertContains(response, '按引用的原文图注展示')
        self.assertContains(response, 'loading="lazy"', count=2)
        for part in parts:
            self.assertContains(response, reverse('paper-figure-asset', args=[self.literature.pk, document_parse.pk, part.evidence_id]))
        self.assertNotContains(response, reverse('paper-figure-asset', args=[self.literature.pk, document_parse.pk, old.evidence_id]))
        self.assertContains(response, 'Fig. 3. Simulation.')
        self.assertContains(response, f'{reverse("view-document", args=[self.upload.pk])}#page=2')

    @patch('apps.literature_processing.reader_views.read_figure_asset', return_value=('image/jpeg', b'\xff\xd8\xfftest'))
    @patch('apps.literature_processing.reader_views.build_catalog')
    def test_figure_image_endpoint_is_authenticated_and_parse_scoped(self, catalog_builder, asset_reader):
        _, document_parse, _, _ = self.create_result()
        self.literature.index_status = 'published'
        self.literature.save()
        figure = Evidence('figure-test', 'figure', document_parse.pk, document_parse.artifact_sha256, '', (2,))
        catalog_builder.return_value = EvidenceCatalog(document_parse, [figure])
        url = reverse('paper-figure-asset', args=[self.literature.pk, document_parse.pk, figure.evidence_id])
        self.assertEqual(self.client.get(url).status_code, 302)
        asset_reader.assert_not_called()
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        asset_reader.reset_mock()
        self.assertEqual(self.client.get(reverse('paper-figure-asset', args=[self.literature.pk, document_parse.pk+100, figure.evidence_id])).status_code, 404)
        asset_reader.assert_not_called()
        self.literature.index_status = 'pending'
        self.literature.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        asset_reader.assert_not_called()
