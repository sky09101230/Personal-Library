import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..models import DocumentParse, DocumentProcessingJob, PaperChatMessage
from ..chat import create_conversation
from ..versions import PARSER_VERSION, PROMPT_VERSION


class PaperChatViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chat-view-user", password="pass")
        self.other = get_user_model().objects.create_user(username="chat-view-other", password="pass")
        self.document = CanonicalDocument.objects.create(title="Chat API paper", index_status=CanonicalDocument.IndexStatus.PUBLISHED)
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.document, uploader=self.user, original_name="chat.pdf",
            remote_path="originals/chat.pdf", sha256="a" * 64, size=10,
            storage_backend=UploadedDocument.StorageBackend.LOCAL,
        )
        job = DocumentProcessingJob.objects.create(
            uploaded_document=self.upload, status="succeeded", stage="complete",
            pipeline_version="test", parser_version=PARSER_VERSION,
            chunker_version="test", prompt_version=PROMPT_VERSION,
        )
        self.parse = DocumentParse.objects.create(
            job=job, parser_name="pypdf", parser_version=PARSER_VERSION,
            schema_version="plab.parse.v1", page_count=1,
            artifact_storage_backend="local", artifact_path="x",
            artifact_sha256="b" * 64, artifact_size=1,
        )
        self.client.force_login(self.user)

    def test_history_lists_only_owned_document_conversations_with_preview(self):
        first = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        PaperChatMessage.objects.create(
            conversation=first, request_id="q1", sequence=0,
            role=PaperChatMessage.Role.USER, content="论文的主要方法是什么？",
        )
        second = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk, title="第二个会话")
        hidden = create_conversation(self.other, self.document.pk, parse_id=self.parse.pk)

        response = self.client.get(reverse("paper-chat-list", args=[self.document.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item["conversation_id"] for item in payload["conversations"]}
        self.assertEqual(ids, {str(first.pk), str(second.pk)})
        first_item = next(item for item in payload["conversations"] if item["conversation_id"] == str(first.pk))
        self.assertEqual(first_item["title"], "论文的主要方法是什么？")
        self.assertEqual(first_item["preview"], "论文的主要方法是什么？")
        self.assertNotIn(str(hidden.pk), ids)

    def test_invalid_question_is_rejected_without_creating_messages(self):
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        url = reverse("paper-chat-ask", args=[conversation.pk])

        response = self.client.post(url, data=json.dumps({"question": "   "}), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_question")
        self.assertEqual(conversation.messages.count(), 0)

    def test_busy_response_exposes_pending_message_for_frontend_polling(self):
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk)
        pending = PaperChatMessage.objects.create(
            conversation=conversation, request_id="q-pending", sequence=0,
            role=PaperChatMessage.Role.ASSISTANT, content="处理中",
            status=PaperChatMessage.Status.PENDING,
            lease_expires_at=timezone.now() + timedelta(seconds=60),
        )
        url = reverse("paper-chat-ask", args=[conversation.pk])

        response = self.client.post(url, data=json.dumps({"question": "继续"}), content_type="application/json")

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["code"], "busy")
        self.assertEqual(payload["pending_message_id"], pending.pk)
        self.assertGreaterEqual(payload["retry_after_seconds"], 1)

    def test_messages_endpoint_returns_status_and_error_metadata(self):
        conversation = create_conversation(self.user, self.document.pk, parse_id=self.parse.pk, title="历史")
        PaperChatMessage.objects.create(
            conversation=conversation, request_id="q1", sequence=0,
            role=PaperChatMessage.Role.USER, content="问题",
        )
        PaperChatMessage.objects.create(
            conversation=conversation, request_id="q1", sequence=1,
            role=PaperChatMessage.Role.ASSISTANT, content="回答失败",
            status=PaperChatMessage.Status.FAILED, error_code="transport_error",
            error_message="接口超时",
        )

        response = self.client.get(reverse("paper-chat-messages", args=[conversation.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "历史")
        self.assertEqual(payload["messages"][1]["error_code"], "transport_error")
        self.assertEqual(payload["messages"][1]["error_message"], "接口超时")
