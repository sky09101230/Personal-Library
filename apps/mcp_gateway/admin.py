from django.contrib import admin
from django.shortcuts import render
from django.urls import reverse

from .forms import McpAccessTokenForm
from .models import McpAccessToken


@admin.register(McpAccessToken)
class McpAccessTokenAdmin(admin.ModelAdmin):
    form = McpAccessTokenForm
    change_form_template = "admin/mcp_gateway/mcpaccesstoken/change_form.html"
    list_display = ("label", "owner", "is_active", "expires_at", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("label", "owner__username")
    readonly_fields = ("last_used_at", "created_at")
    fields = ("owner", "label", "scopes", "is_active", "expires_at", "last_used_at", "created_at")

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        _, plaintext = McpAccessToken.issue(owner=obj.owner, label=obj.label, scopes=obj.scopes, expires_at=obj.expires_at)
        obj.token_digest = McpAccessToken.digest(plaintext)
        super().save_model(request, obj, form, change)
        obj._plaintext_token = plaintext

    def response_add(self, request, obj, post_url_continue=None):
        plaintext = getattr(obj, "_plaintext_token", None)
        if plaintext:
            return self._render_token_reveal(request, obj, plaintext)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_regenerate_token" in request.POST:
            _, plaintext = McpAccessToken.issue(
                owner=obj.owner,
                label=obj.label,
                scopes=obj.scopes,
                expires_at=obj.expires_at,
            )
            obj.token_digest = McpAccessToken.digest(plaintext)
            obj.save(update_fields=["token_digest"])
            return self._render_token_reveal(request, obj, plaintext, regenerated=True)
        return super().response_change(request, obj)

    def _render_token_reveal(self, request, obj, plaintext, regenerated=False):
        return render(request, "admin/mcp_gateway/mcpaccesstoken/token_revealed.html", {
            **self.admin_site.each_context(request),
            "title": "MCP 访问令牌已生成",
            "token": plaintext,
            "regenerated": regenerated,
            "change_url": reverse("admin:mcp_gateway_mcpaccesstoken_change", args=[obj.pk]),
        })
