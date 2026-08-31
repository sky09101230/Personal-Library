from django.db import migrations, models


def mark_existing_purposes_manual(apps, schema_editor):
    SharedSkill = apps.get_model("skills", "SharedSkill")
    SharedSkill.objects.filter(purpose__isnull=False).update(purpose_is_manual=True)


class Migration(migrations.Migration):

    dependencies = [
        ("skills", "0007_sharedskill_ai_summary_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharedskill",
            name="purpose_is_manual",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="skillsyncjob",
            name="enriched_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="skillsyncjob",
            name="operation",
            field=models.CharField(
                choices=[("sync", "GitHub sync"), ("enrichment", "Summary and classification")],
                default="sync",
                max_length=20,
            ),
        ),
        migrations.RunPython(mark_existing_purposes_manual, migrations.RunPython.noop),
    ]
