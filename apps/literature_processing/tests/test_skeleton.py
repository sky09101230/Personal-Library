import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..evidence import Evidence, EvidenceCatalog
from ..models import DocumentParse, DocumentProcessingJob
from ..skeleton import generate_skeleton, validate_skeleton_payload
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
