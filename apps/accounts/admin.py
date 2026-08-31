from django.contrib import admin
from django.shortcuts import render
from django.urls import reverse

from .models import RegistrationInvitation


@admin.register(RegistrationInvitation)
class RegistrationInvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "note", "available", "expires_at", "used_by", "created_by", "created_at")
    list_filter = ("is_active", "used_at")
    search_fields = ("note", "used_by__username", "created_by__username")
    readonly_fields = ("expires_at", "used_at", "used_by", "created_by", "created_at")
    fields = ("note", "is_active", "expires_at", "used_at", "used_by", "created_by", "created_at")

    @admin.display(boolean=True, description="可使用")
    def available(self, obj):
        return obj.is_valid()

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        issued, plaintext = RegistrationInvitation.issue(created_by=request.user, note=obj.note)
        obj.token_digest = issued.token_digest
        obj.created_by = request.user
        obj.expires_at = issued.expires_at
        super().save_model(request, obj, form, change)
        obj._plaintext_invitation = plaintext

    def response_add(self, request, obj, post_url_continue=None):
        plaintext = getattr(obj, "_plaintext_invitation", None)
        if plaintext:
            return render(request, "admin/mcp_gateway/mcpaccesstoken/token_revealed.html", {
                **self.admin_site.each_context(request),
                "title": "注册邀请码已生成",
                "token": plaintext,
                "secret_name": "邀请码",
                "return_label": "返回邀请码设置",
                "change_url": reverse("admin:accounts_registrationinvitation_change", args=[obj.pk]),
            })
        return super().response_add(request, obj, post_url_continue)
