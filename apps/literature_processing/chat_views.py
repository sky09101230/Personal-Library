import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .chat import ChatError, ask_conversation, create_conversation
from .models import PaperConversation
from .llm import complete


@login_required
@require_POST
def conversation_create(request, document_id):
    body = json.loads(request.body or "{}")
    conversation = create_conversation(request.user, document_id, parse_id=body.get("parse_id"), title=body.get("title", ""))
    return JsonResponse({"conversation_id": str(conversation.pk), "parse_id": conversation.document_parse_id})


@login_required
@require_POST
def conversation_ask(request, conversation_id):
    conversation = get_object_or_404(PaperConversation, pk=conversation_id, user=request.user)
    body = json.loads(request.body or "{}")
    try:
        message = ask_conversation(conversation, request.user, body.get("question", ""), request_id=body.get("request_id"), provider=complete)
    except ChatError as exc:
        return JsonResponse({"ok": False, "code": exc.code, "message": str(exc)}, status=409 if exc.code == "busy" else 400)
    return JsonResponse({"ok": message.status == message.Status.SUCCEEDED, "message_id": message.pk,
                         "status": message.status, "answer": message.content,
                         "payload": message.structured_payload})


@login_required
@require_GET
def conversation_messages(request, conversation_id):
    conversation = get_object_or_404(PaperConversation, pk=conversation_id, user=request.user)
    return JsonResponse({"conversation_id": str(conversation.pk), "parse_id": conversation.document_parse_id,
                         "messages": list(conversation.messages.order_by("sequence").values(
                             "id", "role", "content", "structured_payload", "status", "created_at"))})
