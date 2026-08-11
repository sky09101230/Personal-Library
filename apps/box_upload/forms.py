from django import forms

from .metadata import normalize_doi


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            files = [super().clean(item, initial) for item in data]
        else:
            files = [super().clean(data, initial)]
        if any(not uploaded_file.name.lower().endswith(".pdf") for uploaded_file in files):
            raise forms.ValidationError("仅允许上传 PDF 文件。")
        return files


class BoxUploadForm(forms.Form):
    files = MultipleFileField(label="选择文件")


class ZoteroImportForm(forms.Form):
    LIBRARY_TYPES = (("users", "个人文献库"), ("groups", "群组文献库"))

    library_type = forms.ChoiceField(label="文献库类型", choices=LIBRARY_TYPES)
    library_id = forms.CharField(label="Zotero Library ID", max_length=255)
    collection_key = forms.CharField(label="Collection Key（可选）", required=False, max_length=255)
    api_key = forms.CharField(label="Zotero API Key", widget=forms.PasswordInput)


class MetadataReviewForm(forms.Form):
    title = forms.CharField(label="标题", max_length=500)
    authors = forms.CharField(label="作者（每行一位，可写“姓名 | ORCID”）", widget=forms.Textarea(attrs={"rows": 6}))
    abstract = forms.CharField(label="摘要", required=False, widget=forms.Textarea(attrs={"rows": 8}))
    journal = forms.CharField(label="期刊", required=False, max_length=500)
    publication_year = forms.IntegerField(label="年份", required=False, min_value=1800, max_value=2100)
    doi = forms.CharField(label="DOI", required=False, max_length=255)
    ai_tags = forms.CharField(label="AI 标签（逗号分隔）", required=False)

    def clean_authors(self):
        authors = []
        for line in self.cleaned_data["authors"].splitlines():
            name_part, separator, orcid_part = line.partition("|")
            name = " ".join(name_part.split()).strip()
            if name:
                author = {"name": name[:300]}
                orcid = orcid_part.strip().removeprefix("https://orcid.org/") if separator else ""
                if orcid:
                    author["orcid"] = orcid[:64]
                authors.append(author)
        if not authors:
            raise forms.ValidationError("请至少保留一位作者。")
        return authors

    def clean_doi(self):
        return normalize_doi(self.cleaned_data["doi"])

    def clean_ai_tags(self):
        return list(dict.fromkeys(
            tag.strip()[:100]
            for tag in self.cleaned_data["ai_tags"].replace("，", ",").split(",")
            if tag.strip()
        ))[:30]
