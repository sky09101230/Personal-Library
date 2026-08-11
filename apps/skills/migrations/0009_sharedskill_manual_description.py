from django.db import migrations, models


def preserve_existing_ai_descriptions(apps, schema_editor):
    SharedSkill = apps.get_model("skills", "SharedSkill")
    for skill in SharedSkill.objects.exclude(ai_summary_model="").iterator():
        skill.ai_generated_description = skill.description
        skill.save(update_fields=["ai_generated_description"])


class Migration(migrations.Migration):

    dependencies = [
        ("skills", "0008_skillsyncjob_operation_and_manual_purpose"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharedskill",
            name="ai_generated_description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="sharedskill",
            name="description_is_manual",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(preserve_existing_ai_descriptions, migrations.RunPython.noop),
    ]
