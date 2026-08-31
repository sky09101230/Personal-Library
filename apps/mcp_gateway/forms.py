from django import forms

from .models import McpAccessToken


class McpAccessTokenForm(forms.ModelForm):
    scopes = forms.MultipleChoiceField(
        label="权限范围",
        choices=McpAccessToken.SCOPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="至少选择一项权限。",
    )

    class Meta:
        model = McpAccessToken
        fields = ("owner", "label", "scopes", "is_active", "expires_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["scopes"] = self.instance.scopes

    def clean_scopes(self):
        scopes = self.cleaned_data["scopes"]
        if not scopes:
            raise forms.ValidationError("请至少选择一项权限。")
        return scopes
