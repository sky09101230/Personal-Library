from django.conf import settings
from django.core import signing
from django.urls import reverse


_DOWNLOAD_SALT = "apps.skills.archive-download"


def build_skill_download_url(release):
    token = signing.dumps({"release_id": release.pk}, salt=_DOWNLOAD_SALT, compress=True)
    return f"{settings.MCP_PUBLIC_BASE_URL}{reverse('signed-download-skill', kwargs={'token': token})}"


def load_skill_download_token(token):
    payload = signing.loads(
        token,
        salt=_DOWNLOAD_SALT,
        max_age=settings.SKILL_DOWNLOAD_LINK_MAX_AGE,
    )
    release_id = payload.get("release_id") if isinstance(payload, dict) else None
    if not isinstance(release_id, int) or release_id < 1:
        raise signing.BadSignature("Invalid Skill download token.")
    return release_id
