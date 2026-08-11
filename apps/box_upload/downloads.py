from django.conf import settings
from django.core import signing
from django.urls import reverse


_DOWNLOAD_SALT = "apps.box_upload.literature-download"


def build_literature_download_url(document):
    token = signing.dumps({"upload_id": document.pk}, salt=_DOWNLOAD_SALT, compress=True)
    return f"{settings.MCP_PUBLIC_BASE_URL}{reverse('signed-download-document', kwargs={'token': token})}"


def load_literature_download_token(token):
    payload = signing.loads(
        token,
        salt=_DOWNLOAD_SALT,
        max_age=settings.LITERATURE_DOWNLOAD_LINK_MAX_AGE,
    )
    upload_id = payload.get("upload_id") if isinstance(payload, dict) else None
    if not isinstance(upload_id, int) or upload_id < 1:
        raise signing.BadSignature("Invalid literature download token.")
    return upload_id
