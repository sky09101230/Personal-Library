from django.db import migrations, models
import django.db.models.deletion


def assign_existing_skills(apps, schema_editor):
    GitHubSkillSource = apps.get_model("skills", "GitHubSkillSource")
    SharedSkill = apps.get_model("skills", "SharedSkill")
    if not SharedSkill.objects.filter(source__isnull=True).exists():
        return
    source, _ = GitHubSkillSource.objects.get_or_create(
        slug="plab-shared-skills",
        defaults={
            "name": "PLAB Shared Skills",
            "repository_url": "https://github.com/sky09101230/PLAB-Shared-Skills.git",
        },
    )
    SharedSkill.objects.filter(source__isnull=True).update(source=source)


class Migration(migrations.Migration):

    dependencies = [
        ("skills", "0002_remove_sharedskillrelease_unique_skill_release_commit_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="GitHubSkillSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("repository_url", models.URLField(max_length=500)),
                ("branch", models.CharField(blank=True, max_length=120)),
                ("is_enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("name",),
                "verbose_name": "GitHub skill source",
                "verbose_name_plural": "GitHub skill sources",
            },
        ),
        migrations.AlterField(
            model_name="sharedskill",
            name="slug",
            field=models.SlugField(max_length=100),
        ),
        migrations.AddField(
            model_name="sharedskill",
            name="source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="skills",
                to="skills.githubskillsource",
            ),
        ),
        migrations.RunPython(assign_existing_skills, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="sharedskill",
            constraint=models.UniqueConstraint(fields=("source", "slug"), name="unique_skill_source_slug"),
        ),
    ]
