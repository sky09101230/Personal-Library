from django.contrib import admin

from .models import DocumentAnalysis, DocumentParse, DocumentProcessingJob, LiteratureChunk


class ReadOnlyDerivedDataAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DocumentProcessingJob)
class DocumentProcessingJobAdmin(ReadOnlyDerivedDataAdmin):
    list_display = (
        "id",
        "uploaded_document",
        "parser_name",
        "status",
        "stage",
        "pipeline_version",
        "created_at",
    )
    list_filter = ("parser_name", "status", "stage", "pipeline_version")
    search_fields = ("run_id", "uploaded_document__original_name", "error_code")


@admin.register(DocumentParse)
class DocumentParseAdmin(ReadOnlyDerivedDataAdmin):
    list_display = ("id", "job", "parser_name", "parser_version", "page_count", "created_at")
    list_filter = ("parser_name", "parser_version", "schema_version", "artifact_storage_backend")
    search_fields = ("artifact_path", "artifact_sha256", "job__uploaded_document__original_name")


@admin.register(LiteratureChunk)
class LiteratureChunkAdmin(ReadOnlyDerivedDataAdmin):
    list_display = (
        "chunk_key",
        "document_parse",
        "sequence",
        "page_number",
        "end_page_number",
        "page_sequence",
    )
    list_filter = ("page_number",)
    search_fields = ("chunk_key", "content_sha256", "text")


@admin.register(DocumentAnalysis)
class DocumentAnalysisAdmin(ReadOnlyDerivedDataAdmin):
    list_display = ("id", "document_parse", "analysis_type", "provider", "model", "prompt_version", "created_at")
    list_filter = ("analysis_type", "provider", "prompt_version")
    search_fields = ("input_fingerprint", "document_parse__job__uploaded_document__original_name")
