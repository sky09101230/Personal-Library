from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("skills", "0006_sharedskillrelease_storage_backend"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharedskill",
            name="ai_summary_commit",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="sharedskill",
            name="ai_summary_model",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="sharedskill",
            name="ai_summary_prompt_version",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
