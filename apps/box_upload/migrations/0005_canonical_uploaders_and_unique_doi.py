from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower


def backfill_uploaders(apps, schema_editor):
    CanonicalDocument = apps.get_model("box_upload", "CanonicalDocument")
    UploadedDocument = apps.get_model("box_upload", "UploadedDocument")
    through = CanonicalDocument.uploaders.through
    through.objects.bulk_create(
        [
            through(canonicaldocument_id=canonical_id, user_id=uploader_id)
            for canonical_id, uploader_id in UploadedDocument.objects.values_list(
                "canonical_document_id", "uploader_id"
            ).distinct()
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("box_upload", "0004_uploadeddocument_storage_backend"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="canonicaldocument",
            name="uploaders",
            field=models.ManyToManyField(blank=True, related_name="uploaded_literature", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_uploaders, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="canonicaldocument",
            constraint=models.UniqueConstraint(
                Lower("doi"),
                condition=~models.Q(doi=""),
                name="unique_canonical_doi_ci",
            ),
        ),
    ]
