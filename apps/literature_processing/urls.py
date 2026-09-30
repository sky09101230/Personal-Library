from django.urls import path

from . import views
from . import chat_views
from . import skeleton_views
from . import reader_views


urlpatterns = [
    path("<int:document_id>/evidence/<int:parse_id>/<path:evidence_id>/", reader_views.evidence_detail, name="paper-evidence-detail"),
    path("<int:document_id>/figure/<int:parse_id>/<path:evidence_id>/", reader_views.figure_asset, name="paper-figure-asset"),
    path("<int:document_id>/skeleton/", skeleton_views.skeleton_generate, name="paper-skeleton-generate"),
    path("skeleton/<int:run_id>/", skeleton_views.skeleton_status, name="paper-skeleton-status"),
    path("<int:document_id>/chat/", chat_views.conversation_create, name="paper-chat-create"),
    path("<int:document_id>/chat/history/", chat_views.conversation_list, name="paper-chat-list"),
    path("chat/<uuid:conversation_id>/ask/", chat_views.conversation_ask, name="paper-chat-ask"),
    path("chat/<uuid:conversation_id>/messages/", chat_views.conversation_messages, name="paper-chat-messages"),
    path("chat/<uuid:conversation_id>/", chat_views.conversation_delete, name="paper-chat-delete"),
    path(
        "<int:document_id>/processing-status/",
        views.literature_processing_status,
        name="literature-processing-status",
    ),
    path("<int:document_id>/", views.literature_detail, name="literature-detail"),
]
