import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("skills", "0004_skillsyncjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="SkillPurpose",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="subpurposes", to="skills.skillpurpose")),
            ],
            options={"ordering": ("parent_id", "sort_order", "name")},
        ),
        migrations.AddField(
            model_name="sharedskill",
            name="purpose",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="skills", to="skills.skillpurpose"),
        ),
        migrations.CreateModel(
            name="FeaturedSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recommendation", models.CharField(max_length=240)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("skill", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="featured_entry", to="skills.sharedskill")),
            ],
            options={"ordering": ("sort_order", "skill__name")},
        ),
    ]
