from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("box_upload", "0006_zoteroconnection")]

    operations = [
        migrations.AlterField(
            model_name="uploadeddocument",
            name="storage_backend",
            field=models.CharField(
                choices=[("nas_webdav", "NAS WebDAV")],
                db_index=True,
                default="nas_webdav",
                max_length=32,
            ),
        ),
    ]
