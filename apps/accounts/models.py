import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class RegistrationInvitation(models.Model):
    LIFETIME_DAYS = 30

    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    note = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(editable=False)
    used_at = models.DateTimeField(null=True, blank=True, editable=False)
    used_by = models.OneToOneField(
        User,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="registration_invitation",
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="created_registration_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "注册邀请码"
        verbose_name_plural = "注册邀请码"

    @classmethod
    def issue(cls, *, created_by, note=""):
        plaintext = f"plab_invite_{secrets.token_urlsafe(24)}"
        invitation = cls(
            token_digest=cls.digest(plaintext),
            note=note,
            created_by=created_by,
            expires_at=timezone.now() + timedelta(days=cls.LIFETIME_DAYS),
        )
        return invitation, plaintext

    @staticmethod
    def digest(plaintext):
        return hashlib.sha256(plaintext.strip().encode("utf-8")).hexdigest()

    @classmethod
    def available_for(cls, plaintext):
        return cls.objects.filter(
            token_digest=cls.digest(plaintext),
            is_active=True,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        )

    def is_valid(self):
        return self.is_active and self.used_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return self.note or f"邀请码 #{self.pk or 'new'}"
