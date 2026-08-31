from django.contrib import admin
from django.contrib import messages
from django.shortcuts import render

from .models import CanonicalDocument, ExternalReference, MetadataProposal, UploadedDocument
from .metadata_jobs import enqueue_metadata_proposal
from .storage import delete_literature


def _delete_canonical_if_orphaned(canonical):
    if not canonical.uploads.exists() and not canonical.external_references.exists():
        canonical.delete()


class LibraryAdminBase(admin.ModelAdmin):
    """Treat Django staff accounts as library database administrators."""

    def _is_library_admin(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return self._is_library_admin(request)

    def has_add_permission(self, request):
        return self._is_library_admin(request)

    def has_change_permission(self, request, obj=None):
        return self._is_library_admin(request)

    def has_delete_permission(self, request, obj=None):
        return self._is_library_admin(request)


@admin.register(CanonicalDocument)
class CanonicalDocumentAdmin(LibraryAdminBase):
    list_display = ("title", "doi", "metadata_status", "metadata_source", "index_status", "created_at")
    list_filter = ("metadata_status", "metadata_source", "index_status")
    search_fields = ("sha256", "title", "doi", "journal")
    actions = ("queue_deepseek_metadata",)

    @admin.action(description="Queue selected literature for DeepSeek metadata proposals")
    def queue_deepseek_metadata(self, request, queryset):
        selected = list(queryset.select_related()[:100])
        created = 0
        for canonical in selected:
            existing = canonical.metadata_proposals.filter(
                status__in=(MetadataProposal.Status.QUEUED, MetadataProposal.Status.RUNNING)
            ).first()
            proposal = enqueue_metadata_proposal(canonical, requested_by=request.user, force=True)
            if proposal and (existing is None or proposal.pk != existing.pk):
                created += 1
        self.message_user(request, f"Queued {created} metadata proposal(s); selection is limited to 100 records.")


@admin.register(ExternalReference)
class ExternalReferenceAdmin(LibraryAdminBase):
    list_display = ("provider", "library_id", "external_item_id", "external_version", "canonical_document")
    list_filter = ("provider",)
    search_fields = ("library_id", "external_item_id", "canonical_document__title", "canonical_document__doi")

    def delete_model(self, request, obj):
        canonical = obj.canonical_document
        super().delete_model(request, obj)
        _delete_canonical_if_orphaned(canonical)

    def delete_queryset(self, request, queryset):
        canonicals = {
            reference.canonical_document_id: reference.canonical_document
            for reference in queryset.select_related("canonical_document")
        }
        super().delete_queryset(request, queryset)
        for canonical in canonicals.values():
            _delete_canonical_if_orphaned(canonical)


@admin.register(MetadataProposal)
class MetadataProposalAdmin(LibraryAdminBase):
    list_display = ("canonical_document", "status", "provider", "model", "requested_by", "reviewed_by", "requested_at")
    list_filter = ("status", "provider", "model")
    search_fields = ("canonical_document__title", "canonical_document__doi", "error_code")
    readonly_fields = (
        "canonical_document",
        "source_upload",
        "status",
        "provider",
        "model",
        "prompt_version",
        "input_fingerprint",
        "evidence_snapshot",
        "proposal",
        "validation_warnings",
        "error_code",
        "error_message",
        "attempt_count",
        "canonical_updated_at",
        "requested_by",
        "reviewed_by",
        "accepted_before",
        "accepted_after",
        "requested_at",
        "started_at",
        "completed_at",
        "reviewed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UploadedDocument)
class UploadedDocumentAdmin(LibraryAdminBase):
    list_display = ("id", "original_name", "storage_backend", "remote_path", "uploader", "duplicate_type", "status", "uploaded_at")
    list_display_links = ("id", "original_name")
    list_filter = ("storage_backend", "duplicate_type", "status")
    search_fields = ("original_name", "sha256", "remote_path", "uploader__username")
    actions = ("delete_from_box",)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.action(description="Delete selected files from object storage and database")
    def delete_from_box(self, request, queryset):
        if request.POST.get("confirm") != "yes":
            return render(request, "admin/box_upload/confirm_delete.html", {
                "documents": queryset,
                "selected_ids": list(queryset.values_list("pk", flat=True)),
                "action_url": request.get_full_path(),
            })

        deleted = 0
        failed = 0
        for document in queryset:
            try:
                delete_literature(document)
            except Exception as exc:
                failed += 1
                self.message_user(
                    request,
                    f"{document.original_name}: storage deletion failed ({exc})",
                    level=messages.ERROR,
                )
                continue

            canonical = document.canonical_document
            document.delete()
            _delete_canonical_if_orphaned(canonical)
            deleted += 1

        if deleted:
            self.message_user(request, f"Deleted {deleted} file(s) from object storage and the database.")
        if failed:
            self.message_user(request, f"{failed} file(s) were kept in the database because storage deletion failed.", level=messages.WARNING)

    def delete_model(self, request, obj):
        """Keep the single-record delete page consistent with the bulk action."""
        try:
            delete_literature(obj)
        except Exception as exc:
            self.message_user(request, f"{obj.original_name}: storage deletion failed ({exc})", level=messages.ERROR)
            return

        canonical = obj.canonical_document
        super().delete_model(request, obj)
        _delete_canonical_if_orphaned(canonical)
