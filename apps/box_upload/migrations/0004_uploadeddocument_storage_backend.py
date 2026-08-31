from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("box_upload", "0003_metadataproposal"),
    ]

    operations = [
        migrations.AddField(
            model_name="uploadeddocument",
            name="storage_backend",
            field=models.CharField(
                choices=[("nju_box", "NJU Box"), ("nas_webdav", "NAS WebDAV")],
                db_index=True,
                default="nju_box",
                max_length=32,
            ),
        ),
    ]
