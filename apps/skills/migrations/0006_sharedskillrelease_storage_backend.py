from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("skills", "0005_skillpurpose_featuredskill_sharedskill_purpose")]

    operations = [
        migrations.AddField(
            model_name="sharedskillrelease",
            name="storage_backend",
            field=models.CharField(
                choices=[("nju_box", "NJU Box"), ("nas_webdav", "NAS WebDAV")],
                default="nju_box",
                max_length=20,
            ),
        ),
    ]
