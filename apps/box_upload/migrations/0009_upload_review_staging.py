from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("box_upload", "0008_uploadeddocument_file_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UploadReviewBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending confirmation"), ("committed", "Committed")], db_index=True, default="pending", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("uploader", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="upload_review_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="UploadReviewItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_name", models.CharField(max_length=500)),
                ("remote_path", models.CharField(max_length=1000)),
                ("storage_backend", models.CharField(choices=[("nas_webdav", "NAS WebDAV")], default="nas_webdav", max_length=32)),
                ("sha256", models.CharField(db_index=True, max_length=64)),
                ("size", models.BigIntegerField()),
                ("content_type", models.CharField(default="application/pdf", max_length=255)),
                ("metadata", models.JSONField(default=dict)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("commit_result", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="box_upload.uploadreviewbatch")),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
    ]
