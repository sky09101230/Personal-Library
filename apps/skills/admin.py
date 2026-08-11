from django.contrib import admin

from .models import FeaturedSkill, GitHubSkillSource, SharedSkill, SharedSkillRelease, SkillPurpose, SkillSyncJob


@admin.register(SkillSyncJob)
class SkillSyncJobAdmin(admin.ModelAdmin):
    list_display = ("id", "operation", "status", "current_source", "uploaded_count", "enriched_count", "skipped_count", "created_at", "finished_at")
    list_filter = ("operation", "status")
    readonly_fields = [field.name for field in SkillSyncJob._meta.fields]


@admin.register(GitHubSkillSource)
class GitHubSkillSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "repository_url", "branch", "is_enabled", "updated_at")
    list_filter = ("is_enabled",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug", "repository_url")


@admin.register(SkillPurpose)
class SkillPurposeAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order")
    list_filter = ("parent",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(SharedSkill)
class SharedSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "purpose", "purpose_is_manual", "description_is_manual", "source", "slug", "ai_summary_model", "last_synced_commit", "updated_at")
    list_filter = ("purpose", "purpose_is_manual", "description_is_manual", "source")
    search_fields = ("name", "slug", "description", "source__name")

    def save_model(self, request, obj, form, change):
        if "purpose" in form.changed_data:
            obj.purpose_is_manual = True
        if "description" in form.changed_data:
            obj.description_is_manual = True
        super().save_model(request, obj, form, change)


@admin.register(FeaturedSkill)
class FeaturedSkillAdmin(admin.ModelAdmin):
    list_display = ("skill", "recommendation", "sort_order")
    autocomplete_fields = ("skill",)
    search_fields = ("skill__name", "recommendation")


@admin.register(SharedSkillRelease)
class SharedSkillReleaseAdmin(admin.ModelAdmin):
    list_display = ("skill", "git_commit", "storage_backend", "repository_id", "archive_name", "synced_at")
    list_filter = ("storage_backend",)
    search_fields = ("skill__name", "git_commit", "archive_name")
