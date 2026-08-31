from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("box_upload", "0005_canonical_uploaders_and_unique_doi"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ZoteroConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("library_type", models.CharField(choices=[("users", "User"), ("groups", "Group")], max_length=16)),
                ("library_id", models.CharField(max_length=255)),
                ("api_key_ciphertext", models.TextField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="zotero_connection", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
