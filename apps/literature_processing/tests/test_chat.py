import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..chat import ChatError, ask_conversation, create_conversation
from ..models import DocumentParse, DocumentProcessingJob, LiteratureChunk, PaperChatMessage
from ..versions import PARSER_VERSION, PROMPT_VERSION


class PaperChatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='chat-user')
        self.other = get_user_model().objects.create_user(username='other-user')
        self.document = CanonicalDocument.objects.create(title='Chat paper', index_status=CanonicalDocument.IndexStatus.PUBLISHED)
        self.upload = UploadedDocument.objects.create(canonical_document=self.document, uploader=self.user,
            original_name='paper.pdf', remote_path='originals/paper.pdf', sha256='1'*64, size=10,
            storage_backend=UploadedDocument.StorageBackend.LOCAL)
        job = DocumentProcessingJob.objects.create(uploaded_document=self.upload, status='succeeded', stage='complete',
            pipeline_version='test', parser_version=PARSER_VERSION, chunker_version='test', prompt_version=PROMPT_VERSION)
        self.parse = DocumentParse.objects.create(job=job, parser_name='pypdf', parser_version=PARSER_VERSION,
            schema_version='plab.parse.v1', page_count=1, artifact_storage_backend='local', artifact_path='x', artifact_sha256='2'*64, artifact_size=1)
        self.chunk = LiteratureChunk.objects.create(document_parse=self.parse, chunk_key='p1', sequence=0, page_number=1,
            page_sequence=0, start_offset=0, end_offset=30, text='The method improves accuracy.', content_sha256='3'*64)

    def provider(self, role, messages, *, output_mode):
        return SimpleNamespace(content=json.dumps({'status': 'supported', 'claims': [
            {'text': 'The method improves accuracy.', 'evidence_ids': [self.evidence_id], 'kind': 'finding'}]}),
            provider='test', requested_model='test-chat', returned_model='test-chat')

    @patch('apps.literature_processing.chat.build_context_packet')
    @patch('apps.literature_processing.chat.open_paper')
    def test_grounded_answer_persists_and_repeats_idempotently(self, open_paper, build_packet):
        from ..evidence import Evidence, EvidenceCatalog
        from ..paper_context import ContextPacket
        item = Evidence('ev1:1:test', 'text', self.parse.pk, self.parse.artifact_sha256, self.chunk.text, (1,), chunk_ids=(self.chunk.pk,), locator=('chunk', self.chunk.pk))
        self.evidence_id = item.evidence_id
        open_paper.return_value = (self.parse, EvidenceCatalog(self.parse, [item]))
        payload = {'schema_version': 'personal.paper-context.v1', 'parse_id': self.parse.pk, 'artifact_sha256': self.parse.artifact_sha256,
                   'items': [{'evidence_id': item.evidence_id, 'text': item.text, 'pages': [1]}], 'allowed_evidence_ids': [item.evidence_id]}
        build_packet.return_value = ContextPacket(payload)
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        message = ask_conversation(conversation, self.user, 'What improves?', request_id='r1', provider=self.provider)
        self.assertEqual(message.status, PaperChatMessage.Status.SUCCEEDED)
        self.assertEqual(conversation.messages.count(), 2)
        again = ask_conversation(conversation, self.user, 'ignored', request_id='r1', provider=self.provider)
        self.assertEqual(again.pk, message.pk)

    def test_other_user_cannot_ask(self):
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        with self.assertRaisesMessage(ChatError, 'unavailable'):
            ask_conversation(conversation, self.other, 'question', provider=self.provider)

    def test_question_without_matches_returns_insufficient_evidence_success(self):
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        message = ask_conversation(conversation, self.user, '你好', request_id='no-match', provider=self.provider)
        self.assertEqual(message.status, PaperChatMessage.Status.SUCCEEDED)
        self.assertEqual(message.structured_payload['status'], 'insufficient_evidence')
        self.assertIn('本次检索没有找到', message.content)

    def test_expired_pending_turn_is_released(self):
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        PaperChatMessage.objects.create(conversation=conversation, request_id='old', sequence=0,
            role=PaperChatMessage.Role.USER, content='old')
        pending = PaperChatMessage.objects.create(conversation=conversation, request_id='old', sequence=1,
            role=PaperChatMessage.Role.ASSISTANT, content='处理中', status=PaperChatMessage.Status.PENDING,
            lease_expires_at=timezone.now() - timedelta(seconds=1))
        message = ask_conversation(conversation, self.user, '你好', request_id='new', provider=self.provider)
        pending.refresh_from_db()
        self.assertEqual(pending.error_code, 'lease_expired')
        self.assertEqual(message.status, PaperChatMessage.Status.SUCCEEDED)
