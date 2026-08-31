from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


PURPOSES = (
    ("literature-knowledge", "文献与知识", 10, (
        ("literature-search", "文献检索"),
        ("literature-read", "文献阅读"),
        ("citation-management", "引用管理"),
        ("knowledge-synthesis", "综述与知识整理"),
    )),
    ("data-analysis-visualization", "数据分析与可视化", 20, (
        ("data-cleaning", "数据清洗"),
        ("statistics-fitting", "统计与拟合"),
        ("visualization-reporting", "可视化与报告"),
    )),
    ("modeling-simulation-ml", "建模、仿真与机器学习", 30, (
        ("numerical-computing", "数值计算"),
        ("physical-modeling", "物理建模与仿真"),
        ("optimization", "优化"),
        ("machine-learning", "机器学习"),
    )),
    ("experiment-instrument-hardware", "实验、仪器与硬件", 40, (
        ("instrument-control", "仪器控制"),
        ("data-acquisition", "数据采集"),
        ("calibration", "校准"),
        ("experiment-automation", "实验自动化"),
    )),
    ("research-writing-communication", "科研写作与成果表达", 50, (
        ("academic-writing", "学术写作"),
        ("figure-production", "科研图表"),
        ("presentation", "演示与汇报"),
        ("publication-reproducibility", "投稿与复现材料"),
    )),
    ("research-workflow-integration", "科研工作流与工具集成", 60, (
        ("file-conversion", "文件转换"),
        ("batch-automation", "批处理自动化"),
        ("api-integration", "API 集成"),
        ("research-tool-integration", "科研工具集成"),
    )),
)


def create_taxonomy(apps, schema_editor):
    SkillPurpose = apps.get_model("skills", "SkillPurpose")
    for parent_slug, parent_name, sort_order, children in PURPOSES:
        parent, _ = SkillPurpose.objects.update_or_create(
            slug=parent_slug,
            defaults={"name": parent_name, "parent": None, "sort_order": sort_order},
        )
        for child_order, (slug, name) in enumerate(children, start=1):
            SkillPurpose.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "parent": parent, "sort_order": child_order},
            )


def remove_taxonomy(apps, schema_editor):
    SkillPurpose = apps.get_model("skills", "SkillPurpose")
    preserved = {"literature-search", "literature-read"}
    SkillPurpose.objects.filter(slug__in=preserved).update(parent=None)
    created = {parent_slug for parent_slug, _, _, _ in PURPOSES}
    created.update(slug for _, _, _, children in PURPOSES for slug, _ in children)
    SkillPurpose.objects.filter(slug__in=created - preserved).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("skills", "0009_sharedskill_manual_description"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="skillsyncjob",
            name="operation",
            field=models.CharField(
                choices=[
                    ("sync", "GitHub sync"),
                    ("scan", "GitHub candidate scan"),
                    ("enrichment", "Summary and classification"),
                ],
                default="sync",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="SkillCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(choices=[("upload", "用户 ZIP"), ("github", "GitHub 扫描")], max_length=16)),
                ("status", models.CharField(choices=[("pending", "待审核"), ("published", "已发布"), ("rejected", "已拒绝")], default="pending", max_length=16)),
                ("purpose_is_manual", models.BooleanField(default=False)),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("ai_generated_description", models.TextField(blank=True)),
                ("ai_summary_model", models.CharField(blank=True, max_length=120)),
                ("ai_summary_prompt_version", models.CharField(blank=True, max_length=80)),
                ("original_name", models.CharField(blank=True, max_length=255)),
                ("source_path", models.CharField(blank=True, max_length=500)),
                ("source_commit", models.CharField(blank=True, max_length=64)),
                ("content_sha256", models.CharField(db_index=True, max_length=64)),
                ("archive_remote_path", models.CharField(blank=True, max_length=1000)),
                ("archive_size", models.BigIntegerField(default=0)),
                ("validation_errors", models.JSONField(blank=True, default=list)),
                ("validation_warnings", models.JSONField(blank=True, default=list)),
                ("rejection_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("published_skill", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidate_snapshots", to="skills.sharedskill")),
                ("purpose", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidates", to="skills.skillpurpose")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_skill_candidates", to=settings.AUTH_USER_MODEL)),
                ("source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidates", to="skills.githubskillsource")),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="skill_candidates", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-updated_at",),
                "constraints": [models.UniqueConstraint(condition=models.Q(("source__isnull", False)), fields=("source", "source_path"), name="unique_github_skill_candidate_path")],
            },
        ),
        migrations.RunPython(create_taxonomy, remove_taxonomy),
    ]
