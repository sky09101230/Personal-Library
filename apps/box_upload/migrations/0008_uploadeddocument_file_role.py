from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("box_upload", "0007_retire_nju_box_storage")]

    operations = [
        migrations.AddField(
            model_name="uploadeddocument",
            name="file_role",
            field=models.CharField(
                choices=[("primary", "Primary PDF"), ("supplementary", "Supplementary material")],
                db_index=True,
                default="primary",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="uploadeddocument",
            name="relationship_evidence",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
