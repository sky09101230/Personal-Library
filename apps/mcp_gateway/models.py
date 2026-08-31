import hashlib
import secrets

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class McpAccessToken(models.Model):
    LITERATURE_READ = "literature:read"
    LITERATURE_WRITE = "literature:write"
    SKILLS_READ = "skills:read"
    SCOPE_CHOICES = (
        (LITERATURE_READ, "浏览和下载文献"),
        (LITERATURE_WRITE, "上传文献"),
        (SKILLS_READ, "浏览和下载 Skills"),
    )

    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="mcp_access_tokens")
    label = models.CharField(max_length=120)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "MCP 访问令牌"
        verbose_name_plural = "MCP 访问令牌"

    @classmethod
    def issue(cls, *, owner, label, scopes, expires_at=None):
        plaintext = f"plab_mcp_{secrets.token_urlsafe(32)}"
        token = cls(
            owner=owner,
            label=label,
            token_digest=cls.digest(plaintext),
            scopes=sorted(set(scopes)),
            expires_at=expires_at,
        )
        return token, plaintext

    @staticmethod
    def digest(plaintext):
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    def is_valid(self):
        return self.is_active and (self.expires_at is None or self.expires_at > timezone.now())

    def __str__(self):
        return f"{self.label} ({self.owner})"
