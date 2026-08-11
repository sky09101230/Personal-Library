from django.db import models
from django.contrib.auth.models import User


class GitHubSkillSource(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=100, unique=True)
    repository_url = models.URLField(max_length=500)
    branch = models.CharField(max_length=120, blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "GitHub skill source"
        verbose_name_plural = "GitHub skill sources"

    def __str__(self):
        return self.name


class SkillSyncJob(models.Model):
    SYNC = "sync"
    ENRICHMENT = "enrichment"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STATUS_CHOICES = (
        (QUEUED, "Queued"),
        (RUNNING, "Running"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    )
    OPERATION_CHOICES = (
        (SYNC, "GitHub sync"),
        (ENRICHMENT, "Summary and classification"),
    )

    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES, default=SYNC)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=QUEUED)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    current_source = models.CharField(max_length=120, blank=True)
    current_skill = models.CharField(max_length=200, blank=True)
    sources_total = models.PositiveIntegerField(default=0)
    sources_completed = models.PositiveIntegerField(default=0)
    skills_total = models.PositiveIntegerField(default=0)
    skills_processed = models.PositiveIntegerField(default=0)
    uploaded_count = models.PositiveIntegerField(default=0)
    enriched_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_sources = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def percent(self):
        if not self.skills_total:
            return 0
        return min(100, round(self.skills_processed * 100 / self.skills_total))

    def __str__(self):
        return f"Skill sync #{self.pk} ({self.status})"


class SkillPurpose(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="subpurposes",
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("parent_id", "sort_order", "name")

    def __str__(self):
        return f"{self.parent.name} / {self.name}" if self.parent else self.name


class SharedSkill(models.Model):
    source = models.ForeignKey(
        GitHubSkillSource,
        on_delete=models.CASCADE,
        related_name="skills",
        null=True,
        blank=True,
    )
    purpose = models.ForeignKey(
        SkillPurpose,
        on_delete=models.SET_NULL,
        related_name="skills",
        null=True,
        blank=True,
    )
    purpose_is_manual = models.BooleanField(default=False)
    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=200)
    description = models.TextField()
    description_is_manual = models.BooleanField(default=False)
    ai_generated_description = models.TextField(blank=True)
    source_path = models.CharField(max_length=500)
    last_synced_commit = models.CharField(max_length=64, blank=True)
    ai_summary_commit = models.CharField(max_length=64, blank=True)
    ai_summary_model = models.CharField(max_length=120, blank=True)
    ai_summary_prompt_version = models.CharField(max_length=80, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("source", "slug"), name="unique_skill_source_slug"),
        ]

    def __str__(self):
        return self.name


class FeaturedSkill(models.Model):
    skill = models.OneToOneField(SharedSkill, on_delete=models.CASCADE, related_name="featured_entry")
    recommendation = models.CharField(max_length=240)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "skill__name")

    def __str__(self):
        return self.skill.name


class SharedSkillRelease(models.Model):
    skill = models.ForeignKey(SharedSkill, on_delete=models.CASCADE, related_name="releases")
    git_commit = models.CharField(max_length=64)
    storage_backend = models.CharField(
        max_length=20,
        choices=(("nju_box", "NJU Box"), ("nas_webdav", "NAS WebDAV")),
        default="nju_box",
    )
    repository_id = models.CharField(max_length=36, blank=True)
    archive_name = models.CharField(max_length=255)
    archive_remote_path = models.CharField(max_length=1000)
    archive_size = models.BigIntegerField()
    synced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("skill", "git_commit", "repository_id"), name="unique_skill_release_commit_repository")]
        ordering = ("-synced_at",)

    def __str__(self):
        return f"{self.skill.name} @ {self.git_commit[:12]}"
