import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env():
    """Load a simple local .env file without adding a runtime dependency."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "django-insecure-local-development-only"
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [
    host
    for host in (
        os.environ.get("ALLOWED_HOSTS")
        or "localhost,127.0.0.1,propose-reduction-units-confidentiality.trycloudflare.com"
    ).split(",")
    if host
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.box_upload",
    "apps.mcp_gateway",
    "apps.skills",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

database_engine = os.environ.get("AGENTSYS_DB_ENGINE", "sqlite").strip().lower()
if database_engine == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
elif database_engine == "postgresql":
    postgres_settings = {
        "NAME": os.environ.get("AGENTSYS_DB_NAME", "").strip(),
        "USER": os.environ.get("AGENTSYS_DB_USER", "").strip(),
        "PASSWORD": os.environ.get("AGENTSYS_DB_PASSWORD", ""),
        "HOST": os.environ.get("AGENTSYS_DB_HOST", "").strip(),
        "PORT": os.environ.get("AGENTSYS_DB_PORT", "").strip(),
    }
    missing_settings = [name for name, value in postgres_settings.items() if not value]
    if missing_settings:
        raise ImproperlyConfigured(
            "PostgreSQL requires these AgentSys database settings: " + ", ".join(missing_settings)
        )
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", **postgres_settings}}
else:
    raise ImproperlyConfigured(f"Unsupported AGENTSYS_DB_ENGINE: {database_engine}")
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
MCP_PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MCP_MAX_UPLOAD_BYTES = int(os.environ.get("MCP_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
LITERATURE_DOWNLOAD_LINK_MAX_AGE = int(os.environ.get("LITERATURE_DOWNLOAD_LINK_MAX_AGE", "300"))
SKILL_DOWNLOAD_LINK_MAX_AGE = int(os.environ.get("SKILL_DOWNLOAD_LINK_MAX_AGE", "300"))
DOI_RESOLVER_URL = os.environ.get("DOI_RESOLVER_URL", "https://doi.org").rstrip("/")
CROSSREF_API_URL = os.environ.get("CROSSREF_API_URL", "https://api.crossref.org").rstrip("/")
CROSSREF_MAILTO = os.environ.get("CROSSREF_MAILTO", "")
ZOTERO_API_URL = os.environ.get("ZOTERO_API_URL", "https://api.zotero.org").rstrip("/")
METADATA_HTTP_TIMEOUT = float(os.environ.get("METADATA_HTTP_TIMEOUT", "5"))
