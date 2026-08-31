from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import RegistrationInvitation


INVALID_INVITATION_MESSAGE = "邀请码无效、已使用或已过期。"


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=False)
    invitation_code = forms.CharField(
        label="邀请码",
        help_text="请输入管理员提供的一次性邀请码。",
    )

    class Meta:
        model = User
        fields = ("username", "email", "invitation_code", "password1", "password2")

    def clean_invitation_code(self):
        invitation_code = self.cleaned_data["invitation_code"].strip()
        if not RegistrationInvitation.available_for(invitation_code).exists():
            raise forms.ValidationError(INVALID_INVITATION_MESSAGE)
        return invitation_code
