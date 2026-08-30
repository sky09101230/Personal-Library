from django import forms

from .models import SkillPurpose


class GitHubSkillSearchForm(forms.Form):
    q = forms.CharField(
        label="关键词",
        min_length=2,
        max_length=80,
        strip=True,
        error_messages={
            "required": "请输入关键词。",
            "min_length": "关键词至少需要 2 个字符。",
            "max_length": "关键词最多 80 个字符。",
        },
        widget=forms.SearchInput(attrs={"placeholder": "例如 literature review"}),
    )


class GitHubSkillImportForm(forms.Form):
    owner = forms.CharField(max_length=100, widget=forms.HiddenInput)
    repository = forms.CharField(max_length=100, widget=forms.HiddenInput)
    path = forms.CharField(max_length=500, widget=forms.HiddenInput)
    q = forms.CharField(max_length=80, required=False, widget=forms.HiddenInput)


class SkillDescriptionForm(forms.Form):
    description = forms.CharField(
        label="展示描述",
        max_length=400,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="可基于 DeepSeek 原始摘要修改，最多 400 个字符。",
    )


class SkillCandidateUploadForm(forms.Form):
    archive = forms.FileField(
        label="Skill ZIP",
        help_text="一个 ZIP 只能包含一个 Skill，最大 800 MiB；系统会自动检查格式并建议分类。",
        widget=forms.ClearableFileInput(attrs={"accept": ".zip,application/zip"}),
    )

    def clean_archive(self):
        archive = self.cleaned_data["archive"]
        if not archive.name.lower().endswith(".zip"):
            raise forms.ValidationError("请选择 ZIP 文件。")
        return archive


class SkillCandidateReviewForm(forms.Form):
    description = forms.CharField(label="展示摘要", max_length=400, widget=forms.Textarea(attrs={"rows": 5}))
    purpose = forms.ModelChoiceField(label="科研任务分类", queryset=SkillPurpose.objects.none())
    rejection_reason = forms.CharField(label="拒绝原因", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["purpose"].queryset = SkillPurpose.objects.filter(subpurposes__isnull=True).select_related("parent")
