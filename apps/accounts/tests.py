from django.contrib.auth.models import User
from django.test import TestCase


class AccountTests(TestCase):
    def test_registration_logs_user_in(self):
        response = self.client.post("/accounts/register/", {
            "username": "member",
            "email": "member@example.com",
            "password1": "Strong-pass-1234",
            "password2": "Strong-pass-1234",
        })
        self.assertRedirects(response, "/")
        self.assertTrue(User.objects.filter(username="member").exists())

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
