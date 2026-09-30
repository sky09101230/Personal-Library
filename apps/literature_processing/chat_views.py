import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .chat import ChatError, ask_conversation, create_conversation, release_expired_pending
from .models import PaperConversation
from .llm import complete


def _json_body(request):
    try:
        body = json.loads(request.body or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ChatError("invalid_json", "请求格式无效。")
    if not isinstance(body, dict):
        raise ChatError("invalid_json", "请求格式无效。")
    return body


@login_required
@require_POST
def conversation_create(request, document_id):
    try:
        body = _json_body(request)
        conversation = create_conversation(request.user, document_id, parse_id=body.get("parse_id"), title=body.get("title", ""))
    except ChatError as exc:
        return JsonResponse({"ok": False, "code": exc.code, "message": str(exc), **exc.details}, status=400)
    return JsonResponse({"conversation_id": str(conversation.pk), "parse_id": conversation.document_parse_id})


@login_required
@require_GET
def conversation_list(request, document_id):
    """List this user's conversations for a document so the reader can restore history."""
    conversations = PaperConversation.objects.filter(
        user=request.user,
        document_parse__job__uploaded_document__canonical_document_id=document_id,
    ).prefetch_related("messages")[:50]
    items = []
    for conversation in conversations:
        release_expired_pending(conversation)
        conversation._prefetched_objects_cache.pop("messages", None)
        messages = list(conversation.messages.all())
        latest_question = next((item.content for item in reversed(messages) if item.role == item.Role.USER), "")
        pending = next((item for item in reversed(messages) if item.role == item.Role.ASSISTANT and item.status == item.Status.PENDING), None)
        items.append({
            "conversation_id": str(conversation.pk),
            "parse_id": conversation.document_parse_id,
            "title": conversation.title or latest_question[:200] or "未命名对话",
            "preview": latest_question[:160],
            "message_count": len(messages),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "pending_message_id": pending.pk if pending else None,
        })
    return JsonResponse({"document_id": document_id, "conversations": items})


@login_required
@require_POST
def conversation_ask(request, conversation_id):
    conversation = get_object_or_404(PaperConversation, pk=conversation_id, user=request.user)
    try:
        body = _json_body(request)
        message = ask_conversation(conversation, request.user, body.get("question", ""), request_id=body.get("request_id"), provider=complete)
    except ChatError as exc:
        status = 409 if exc.code == "busy" else 400
        return JsonResponse({"ok": False, "code": exc.code, "message": str(exc), **exc.details}, status=status)
    return JsonResponse({"ok": message.status == message.Status.SUCCEEDED, "message_id": message.pk,
                         "status": message.status, "answer": message.content,
                         "payload": message.structured_payload})


@login_required
@require_GET
def conversation_messages(request, conversation_id):
    conversation = get_object_or_404(PaperConversation, pk=conversation_id, user=request.user)
    release_expired_pending(conversation)
    conversation.refresh_from_db(fields=("title", "updated_at"))
    return JsonResponse({"conversation_id": str(conversation.pk), "parse_id": conversation.document_parse_id,
                         "title": conversation.title,
                         "messages": list(conversation.messages.order_by("sequence").values(
                             "id", "role", "content", "structured_payload", "status", "error_code",
                             "error_message", "provider", "requested_model", "model", "created_at",
                             "started_at", "completed_at", "lease_expires_at"))})
