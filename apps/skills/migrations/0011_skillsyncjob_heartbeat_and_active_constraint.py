from django.db import migrations, models
from django.utils import timezone


def close_duplicate_active_jobs(apps, schema_editor):
    SkillSyncJob = apps.get_model("skills", "SkillSyncJob")
    active_jobs = list(
        SkillSyncJob.objects.filter(status__in=("queued", "running"))
        .order_by("-created_at", "-pk")
        .values_list("pk", flat=True)
    )
    if len(active_jobs) > 1:
        now = timezone.now()
        SkillSyncJob.objects.filter(pk__in=active_jobs[1:]).update(
            status="failed",
            error="部署单活动任务约束时关闭了重复任务。",
            heartbeat_at=now,
            finished_at=now,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("skills", "0010_skill_candidates_and_research_taxonomy"),
    ]

    operations = [
        migrations.AddField(
            model_name="skillsyncjob",
            name="heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="skillsyncjob",
            name="operation",
            field=models.CharField(
                choices=[
                    ("sync", "GitHub sync"),
                    ("scan", "GitHub candidate scan"),
                    ("enrichment", "Summary and classification"),
                ],
                default="scan",
                max_length=20,
            ),
        ),
        migrations.RunPython(close_duplicate_active_jobs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="skillsyncjob",
            constraint=models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(status__in=("queued", "running")),
                name="unique_active_skill_job",
            ),
        ),
    ]
