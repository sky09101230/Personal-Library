import re
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import RegistrationInvitation


class AccountTests(TestCase):
    def setUp(self):
        self.inviter = User.objects.create_superuser(
            username="inviter",
            email="inviter@example.com",
            password="Strong-pass-1234",
        )

    def issue_invitation(self, note="Test invitation"):
        invitation, plaintext = RegistrationInvitation.issue(
            created_by=self.inviter,
            note=note,
        )
        invitation.save()
        return invitation, plaintext

    @staticmethod
    def registration_data(username, invitation_code, password="Strong-pass-1234"):
        return {
            "username": username,
            "email": f"{username}@example.com",
            "invitation_code": invitation_code,
            "password1": password,
            "password2": password,
        }

    def test_registration_uses_invitation_once_and_logs_user_in(self):
        invitation, plaintext = self.issue_invitation()

        response = self.client.post(
            "/accounts/register/",
            self.registration_data("member", plaintext),
        )

        self.assertRedirects(response, "/")
        member = User.objects.get(username="member")
        invitation.refresh_from_db()
        self.assertEqual(int(self.client.session["_auth_user_id"]), member.pk)
        self.assertEqual(invitation.used_by, member)
        self.assertIsNotNone(invitation.used_at)
        self.assertFalse(invitation.is_active)

        self.client.logout()
        retry = self.client.post(
            "/accounts/register/",
            self.registration_data("second-member", plaintext),
        )
        self.assertEqual(retry.status_code, 200)
        self.assertContains(retry, "邀请码无效、已使用或已过期")
        self.assertFalse(User.objects.filter(username="second-member").exists())

    def test_registration_page_explains_invitation_requirement(self):
        response = self.client.get("/accounts/register/")

        self.assertContains(response, 'name="invitation_code"')
        self.assertContains(response, "使用管理员提供的一次性邀请码")

    def test_registration_rejects_missing_or_unknown_invitation(self):
        for username, code in (("missing-code", ""), ("unknown-code", "not-a-real-code")):
            with self.subTest(code=code):
                response = self.client.post(
                    "/accounts/register/",
                    self.registration_data(username, code),
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(User.objects.filter(username=username).exists())

    def test_registration_rejects_expired_or_disabled_invitation(self):
        expired, expired_code = self.issue_invitation("Expired")
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])
        disabled, disabled_code = self.issue_invitation("Disabled")
        disabled.is_active = False
        disabled.save(update_fields=["is_active"])

        for username, code in (("expired-member", expired_code), ("disabled-member", disabled_code)):
            with self.subTest(username=username):
                response = self.client.post(
                    "/accounts/register/",
                    self.registration_data(username, code),
                )
                self.assertContains(response, "邀请码无效、已使用或已过期")
                self.assertFalse(User.objects.filter(username=username).exists())

    def test_invalid_registration_does_not_consume_invitation(self):
        invitation, plaintext = self.issue_invitation()
        data = self.registration_data("member", plaintext)
        data["password2"] = "different-password"

        response = self.client.post("/accounts/register/", data)

        self.assertEqual(response.status_code, 200)
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_valid())
        self.assertIsNone(invitation.used_by)
        self.assertFalse(User.objects.filter(username="member").exists())

    @patch.object(RegistrationInvitation, "available_for")
    def test_lost_invitation_claim_rolls_back_created_user(self, available_for):
        valid_query = Mock()
        valid_query.exists.return_value = True
        lost_claim = Mock()
        lost_claim.update.return_value = 0
        available_for.side_effect = (valid_query, lost_claim)

        response = self.client.post(
            "/accounts/register/",
            self.registration_data("racing-member", "initially-valid"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "邀请码无效、已使用或已过期")
        self.assertFalse(User.objects.filter(username="racing-member").exists())

    def test_admin_reveals_new_invitation_once_with_30_day_expiry(self):
        self.client.force_login(self.inviter)

        response = self.client.post("/admin/accounts/registrationinvitation/add/", {
            "note": "New colleague",
            "is_active": "on",
            "_save": "保存",
        })

        self.assertContains(response, "注册邀请码已生成")
        self.assertContains(response, "离开此页面后无法再次查看该邀请码")
        self.assertContains(response, "返回邀请码设置")
        invitation = RegistrationInvitation.objects.get(note="New colleague")
        match = re.search(r">(plab_invite_[A-Za-z0-9_-]+)</textarea>", response.content.decode())
        self.assertIsNotNone(match)
        self.assertEqual(invitation.token_digest, RegistrationInvitation.digest(match.group(1)))
        self.assertNotContains(response, invitation.token_digest)
        self.assertAlmostEqual(
            (invitation.expires_at - invitation.created_at).total_seconds(),
            30 * 24 * 60 * 60,
            delta=2,
        )

    def test_home_requires_login(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_logout_returns_to_user_login(self):
        user = User.objects.create_user(username="member", password="Strong-pass-1234")
        self.client.force_login(user)
        response = self.client.post("/accounts/logout/")
        self.assertRedirects(response, "/accounts/login/")

    def test_admin_login_uses_workspace_template(self):
        response = self.client.get("/admin/login/")
        self.assertContains(response, "Welcome back")
        self.assertContains(response, 'name="next"')

    def test_login_honors_safe_next_url(self):
        User.objects.create_user(username="member", password="Strong-pass-1234")
        response = self.client.post("/accounts/login/?next=/uploads/", {
            "username": "member",
            "password": "Strong-pass-1234",
            "next": "/uploads/",
        })
        self.assertRedirects(response, "/uploads/")
