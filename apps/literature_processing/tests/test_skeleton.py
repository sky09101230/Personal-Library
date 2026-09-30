import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.exceptions import ValidationError
from unittest.mock import Mock

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..evidence import Evidence, EvidenceCatalog
from ..models import DocumentParse, DocumentProcessingJob
from ..skeleton import generate_skeleton, validate_skeleton_payload, SkeletonError
from ..llm import LLMError
from ..paper_context import build_skeleton_context
from ..versions import PARSER_VERSION, PROMPT_VERSION


class SkeletonTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='skeleton-user')
        document = CanonicalDocument.objects.create(title='Skeleton paper', index_status=CanonicalDocument.IndexStatus.PUBLISHED)
        upload = UploadedDocument.objects.create(canonical_document=document, uploader=self.user, original_name='paper.pdf',
            remote_path='originals/paper.pdf', sha256='a'*64, size=1, storage_backend=UploadedDocument.StorageBackend.LOCAL)
        job = DocumentProcessingJob.objects.create(uploaded_document=upload, status='succeeded', stage='complete',
            pipeline_version='test', parser_version=PARSER_VERSION, chunker_version='test', prompt_version=PROMPT_VERSION)
        self.parse = DocumentParse.objects.create(job=job, parser_name='pypdf', parser_version=PARSER_VERSION,
            schema_version='plab.parse.v1', page_count=1, artifact_storage_backend='local', artifact_path='x', artifact_sha256='b'*64, artifact_size=1)
        self.item = Evidence('ev-skeleton', 'text', self.parse.pk, self.parse.artifact_sha256, 'The method works.', (1,), locator=('x',))
        self.catalog = EvidenceCatalog(self.parse, [self.item])

    def payload(self):
        claim = {'text': 'The method works.', 'evidence_ids': [self.item.evidence_id], 'kind': 'finding'}
        return {'language': 'en', 'sections': {name: {'claims': [claim], 'status': 'supported'} for name in ('introduction','motivation','gap','proposed_idea','method','experiments','results','conclusion')},
                'figures': [], 'limitations': [], 'coverage': {'partial': False}}

    @patch('apps.literature_processing.skeleton.build_skeleton_context')
    def test_generation_is_persisted_and_cached(self, context_builder):
        context_builder.return_value = {'allowed_evidence_ids': [self.item.evidence_id], 'items': [{'evidence_id': self.item.evidence_id, 'text': self.item.text}]}
        result = SimpleNamespace(content=json.dumps(self.payload()), provider='test', requested_model='overview', returned_model='overview')
        run = generate_skeleton(self.parse, self.user, provider=lambda *args, **kwargs: result, catalog=self.catalog)
        self.assertEqual(run.status, run.Status.SUCCEEDED)
        cached = generate_skeleton(self.parse, self.user, provider=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()), catalog=self.catalog)
        self.assertEqual(cached.pk, run.pk)

    def test_payload_rejects_missing_section(self):
        payload = self.payload()
        payload['sections'].pop('gap')
        with self.assertRaises(Exception):
            validate_skeleton_payload(payload)

    @patch('apps.literature_processing.skeleton.build_skeleton_context')
    def test_empty_or_malformed_analysis_is_not_saved(self, context_builder):
        context_builder.return_value = {'allowed_evidence_ids': [self.item.evidence_id], 'items': []}
        empty = self.payload()
        for section in empty['sections'].values():
            section.update(status='insufficient_evidence', claims=[])
        provider = Mock(return_value=SimpleNamespace(content=json.dumps(empty)))
        with self.assertRaises(SkeletonError) as raised:
            generate_skeleton(self.parse, self.user, provider=provider, catalog=self.catalog)
        self.assertEqual(raised.exception.code, 'empty_analysis')
        self.assertFalse(self.parse.analyses.exists())
        self.assertEqual(self.parse.paper_analysis_runs.get().status, 'failed')
        broken = self.payload()
        broken['sections']['method']['claims'] = ['This is not a claim object']
        with self.assertRaises(ValidationError):
            validate_skeleton_payload(broken)

    @patch('apps.literature_processing.skeleton.build_skeleton_context')
    def test_force_appends_and_invalid_evidence_preserves_previous_result(self, context_builder):
        context_builder.return_value = {'allowed_evidence_ids': [self.item.evidence_id], 'items': []}
        provider = Mock(return_value=SimpleNamespace(content=json.dumps(self.payload()), provider='test', returned_model='overview'))
        first = generate_skeleton(self.parse, self.user, provider=provider, catalog=self.catalog)
        second = generate_skeleton(self.parse, self.user, provider=provider, catalog=self.catalog, force=True)
        self.assertNotEqual(first.result_id, second.result_id)
        invalid = self.payload()
        invalid['sections']['method']['claims'][0]['evidence_ids'] = ['not-in-packet']
        provider.return_value.content = json.dumps(invalid)
        with self.assertRaises(SkeletonError):
            generate_skeleton(self.parse, self.user, provider=provider, catalog=self.catalog, force=True)
        self.assertEqual(self.parse.analyses.count(), 2)

    def test_reader_tabs_and_empty_legacy_result_regenerate(self):
        from ..models import DocumentAnalysis
        payload = self.payload()
        for section in payload['sections'].values():
            section.update(status='insufficient_evidence', claims=[])
        DocumentAnalysis.objects.create(document_parse=self.parse, analysis_type='paper_skeleton',
            schema_version='personal.paper-skeleton.v1', provider='test', model='test', prompt_version='paper-skeleton-v1',
            input_fingerprint='f'*64, payload=payload)
        self.client.force_login(self.user)
        response = self.client.get(f'/library/{self.parse.canonical_document.pk}/')
        self.assertContains(response, 'role="tablist"')
        self.assertContains(response, 'id="intelligence"')
        self.assertContains(response, '重新生成总览')
        self.assertContains(response, '旧总览没有生成有效的带证据结论')
        self.assertNotContains(response, '<h4>introduction</h4>')

    @patch('apps.literature_processing.skeleton.load_config')
    @patch('apps.literature_processing.skeleton.complete')
    @patch('apps.literature_processing.skeleton.build_skeleton_context')
    def test_default_provider_uses_skeleton_timeout_without_changing_chat(self, builder, complete, config):
        from ..llm import LLMConfig
        config.return_value = LLMConfig('http://localhost:53347/v1', 'dummy', 'chat', 'overview')
        builder.return_value = {'allowed_evidence_ids': [self.item.evidence_id], 'items': []}
        complete.return_value = SimpleNamespace(content=json.dumps(self.payload()), provider='test', returned_model='overview')
        run = generate_skeleton(self.parse, self.user, catalog=self.catalog)
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(complete.call_args.kwargs['config'].timeout, 180)
        self.assertEqual(complete.call_args.kwargs['config'].max_retries, 0)
        self.assertEqual(complete.call_args.kwargs['max_tokens'], 2048)
        self.assertEqual(config.return_value.timeout, 30)

    @patch('apps.literature_processing.skeleton.load_config')
    @patch('apps.literature_processing.skeleton.complete')
    @patch('apps.literature_processing.skeleton.build_skeleton_context')
    def test_default_provider_retries_transport_with_compact_context(self, builder, complete, config):
        from ..llm import LLMConfig
        config.return_value = LLMConfig('http://localhost:53347/v1', 'dummy', 'chat', 'overview')
        initial = {'allowed_evidence_ids': [self.item.evidence_id], 'items': [{'evidence_id': self.item.evidence_id, 'text': self.item.text}]}
        compact = {**initial, 'context_version': 'compact'}
        builder.side_effect = [initial, compact]
        complete.side_effect = [LLMError('transport_error', 'timeout', retryable=True),
                                SimpleNamespace(content=json.dumps(self.payload()), provider='test', returned_model='overview')]

        run = generate_skeleton(self.parse, self.user, catalog=self.catalog)

        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(builder.call_count, 2)
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(complete.call_args.kwargs['config'].reasoning_effort, 'low')
        self.assertEqual(run.context_manifest['context_version'], 'compact')

    @patch.dict('os.environ', {'PAPER_SKELETON_MAX_TOKENS': '256'}, clear=False)
    @patch('apps.literature_processing.skeleton.load_config')
    def test_invalid_skeleton_output_budget_is_rejected(self, config):
        from ..llm import LLMConfig
        config.return_value = LLMConfig('http://localhost:53347/v1', 'dummy', 'chat', 'overview')
        with self.assertRaisesMessage(SkeletonError, 'PAPER_SKELETON_MAX_TOKENS'):
            generate_skeleton(self.parse, self.user, catalog=self.catalog)
