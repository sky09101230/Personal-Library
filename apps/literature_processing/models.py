import uuid

from django.db import models


class DocumentProcessingJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class Stage(models.TextChoices):
        QUEUED = "queued", "Queued"
        DOWNLOAD = "download", "Download PDF"
        PARSE = "parse", "Parse PDF"
        CHUNK = "chunk", "Create chunks"
        OVERVIEW = "overview", "Generate overview"
        COMPLETE = "complete", "Complete"

    run_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    uploaded_document = models.ForeignKey(
        "box_upload.UploadedDocument",
        on_delete=models.CASCADE,
        related_name="processing_jobs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.QUEUED)
    parser_name = models.CharField(max_length=64, default="pypdf")
    pipeline_version = models.CharField(max_length=64)
    parser_version = models.CharField(max_length=64)
    chunker_version = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=64)
    attempt_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("uploaded_document",),
                condition=models.Q(status__in=("queued", "running")),
                name="lp_unique_active_job",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "created_at"), name="lp_job_queue_idx"),
        ]

    def __str__(self):
        return f"Processing job {self.pk} ({self.status})"


class DocumentParse(models.Model):
    job = models.OneToOneField(
        DocumentProcessingJob,
        on_delete=models.CASCADE,
        related_name="document_parse",
    )
    parser_name = models.CharField(max_length=64)
    parser_version = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=64)
    page_count = models.PositiveIntegerField()
    artifact_storage_backend = models.CharField(max_length=32)
    artifact_path = models.CharField(max_length=1000)
    artifact_sha256 = models.CharField(max_length=64)
    artifact_content_type = models.CharField(max_length=255, default="application/json")
    artifact_size = models.PositiveBigIntegerField()
    warnings = models.JSONField(default=list, blank=True)
    runtime_info = models.JSONField(default=dict, blank=True)
    raw_artifact_storage_backend = models.CharField(max_length=32, blank=True)
    raw_artifact_path = models.CharField(max_length=1000, blank=True)
    raw_artifact_sha256 = models.CharField(max_length=64, blank=True)
    raw_artifact_content_type = models.CharField(max_length=255, blank=True)
    raw_artifact_size = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    @property
    def uploaded_document(self):
        return self.job.uploaded_document

    @property
    def canonical_document(self):
        return self.job.uploaded_document.canonical_document

    def __str__(self):
        return f"Parse {self.pk} for job {self.job_id}"


class LiteratureChunk(models.Model):
    document_parse = models.ForeignKey(
        DocumentParse,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_key = models.CharField(max_length=128)
    sequence = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField()
    end_page_number = models.PositiveIntegerField(null=True, blank=True)
    page_sequence = models.PositiveIntegerField()
    start_offset = models.PositiveIntegerField()
    end_offset = models.PositiveIntegerField()
    text = models.TextField()
    content_sha256 = models.CharField(max_length=64)
    section_path = models.JSONField(default=list, blank=True)
    source_spans = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("document_parse_id", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("document_parse", "chunk_key"),
                name="lp_unique_chunk_key",
            ),
            models.UniqueConstraint(
                fields=("document_parse", "sequence"),
                name="lp_unique_chunk_sequence",
            ),
            models.UniqueConstraint(
                fields=("document_parse", "page_number", "page_sequence"),
                name="lp_unique_page_chunk",
            ),
            models.CheckConstraint(
                condition=models.Q(page_number__gte=1),
                name="lp_chunk_page_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(end_offset__gt=models.F("start_offset")),
                name="lp_chunk_offsets_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(end_page_number__isnull=True)
                    | models.Q(end_page_number__gte=models.F("page_number"))
                ),
                name="lp_chunk_page_range_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("document_parse", "page_number"), name="lp_chunk_page_idx"),
        ]

    @property
    def uploaded_document(self):
        return self.document_parse.uploaded_document

    @property
    def canonical_document(self):
        return self.document_parse.canonical_document

    def __str__(self):
        return self.chunk_key


class DocumentAnalysis(models.Model):
    class AnalysisType(models.TextChoices):
        OVERVIEW = "overview", "Overview"

    document_parse = models.ForeignKey(
        DocumentParse,
        on_delete=models.CASCADE,
        related_name="analyses",
    )
    analysis_type = models.CharField(max_length=32, choices=AnalysisType.choices)
    schema_version = models.CharField(max_length=64)
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    prompt_version = models.CharField(max_length=64)
    input_fingerprint = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("document_parse", "analysis_type", "prompt_version", "input_fingerprint"),
                name="lp_unique_analysis_input",
            ),
        ]

    @property
    def job(self):
        return self.document_parse.job

    @property
    def uploaded_document(self):
        return self.document_parse.uploaded_document

    @property
    def canonical_document(self):
        return self.document_parse.canonical_document

    def __str__(self):
        return f"{self.analysis_type} analysis {self.pk}"

    def clean(self):
        super().clean()
        if self.analysis_type == self.AnalysisType.OVERVIEW:
            from .overview_validation import validate_overview_payload

            validate_overview_payload(self.payload, self.document_parse_id)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
