from django import forms


class SkillDescriptionForm(forms.Form):
    description = forms.CharField(
        label="展示描述",
        max_length=400,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="可基于 DeepSeek 原始摘要修改，最多 400 个字符。",
    )
