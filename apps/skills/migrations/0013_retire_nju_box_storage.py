from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("skills", "0012_academicskillrecommendation_and_more")]

    operations = [
        migrations.AlterField(
            model_name="sharedskillrelease",
            name="storage_backend",
            field=models.CharField(
                choices=[("nas_webdav", "NAS WebDAV")],
                default="nas_webdav",
                max_length=20,
            ),
        ),
    ]
