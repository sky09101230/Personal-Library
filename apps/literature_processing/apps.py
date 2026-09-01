from django.apps import AppConfig


class LiteratureProcessingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.literature_processing"

    def ready(self):
        from . import signals  # noqa: F401
