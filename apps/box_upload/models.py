from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import Lower


class CanonicalDocument(models.Model):
    class MetadataStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        INCOMPLETE = "incomplete", "Incomplete"
        NEEDS_REVIEW = "needs_review", "Needs review"
        VERIFIED = "verified", "Verified"
        CONFLICT = "conflict", "Conflict"

    class IndexStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        PUBLISHED = "published", "Published"

    sha256 = models.CharField(max_length=64, unique=True, null=True, blank=True)
    title = models.CharField(max_length=500, blank=True)
    authors = models.JSONField(default=list, blank=True)
    abstract = models.TextField(blank=True)
    journal = models.CharField(max_length=500, blank=True)
    doi = models.CharField(max_length=255, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    identifiers = models.JSONField(default=dict, blank=True)
    user_tags = models.JSONField(default=list, blank=True)
    source_tags = models.JSONField(default=list, blank=True)
    ai_tags = models.JSONField(default=list, blank=True)
    metadata_source = models.CharField(max_length=64, blank=True)
    metadata_status = models.CharField(
        max_length=32,
        choices=MetadataStatus.choices,
        default=MetadataStatus.PENDING,
    )
    metadata_confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    metadata_evidence = models.JSONField(default=dict, blank=True)
    metadata_candidates = models.JSONField(default=dict, blank=True)
    index_status = models.CharField(
        max_length=32,
        choices=IndexStatus.choices,
        default=IndexStatus.PENDING,
    )
    uploaders = models.ManyToManyField(User, related_name="uploaded_literature", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("doi"),
                condition=~models.Q(doi=""),
                name="unique_canonical_doi_ci",
            )
        ]

    def __str__(self):
        return self.title or self.doi or self.sha256 or f"Literature {self.pk}"


class ExternalReference(models.Model):
    class Provider(models.TextChoices):
        ZOTERO = "zotero", "Zotero"

    canonical_document = models.ForeignKey(
        CanonicalDocument,
        on_delete=models.CASCADE,
        related_name="external_references",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    library_id = models.CharField(max_length=255)
    external_item_id = models.CharField(max_length=255)
    external_version = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "library_id", "external_item_id"),
                name="unique_external_literature_reference",
            )
        ]

    def __str__(self):
        return f"{self.provider}:{self.library_id}:{self.external_item_id}"


class ZoteroConnection(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="zotero_connection")
    library_type = models.CharField(max_length=16, choices=(("users", "User"), ("groups", "Group")))
    library_id = models.CharField(max_length=255)
    api_key_ciphertext = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)


class UploadedDocument(models.Model):
    class StorageBackend(models.TextChoices):
        NJU_BOX = "nju_box", "NJU Box"
        NAS_WEBDAV = "nas_webdav", "NAS WebDAV"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        FAILED = "failed", "Failed"

    class DuplicateType(models.TextChoices):
        NEW = "new", "New content"
        EXACT = "exact", "Exact content duplicate"
        POSSIBLE = "possible", "Possible metadata duplicate"

    canonical_document = models.ForeignKey(CanonicalDocument, on_delete=models.PROTECT, related_name="uploads")
    uploader = models.ForeignKey(User, on_delete=models.PROTECT, related_name="document_uploads")
    original_name = models.CharField(max_length=500)
    remote_path = models.CharField(max_length=1000, blank=True)
    storage_backend = models.CharField(
        max_length=32,
        choices=StorageBackend.choices,
        default=StorageBackend.NJU_BOX,
        db_index=True,
    )
    sha256 = models.CharField(max_length=64, db_index=True)
    size = models.BigIntegerField()
    content_type = models.CharField(max_length=255, blank=True)
    duplicate_type = models.CharField(max_length=16, choices=DuplicateType.choices, default=DuplicateType.NEW)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    error_message = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.canonical_document.uploaders.add(self.uploader_id)


class MetadataProposal(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        STALE = "stale", "Stale"

    canonical_document = models.ForeignKey(
        CanonicalDocument,
        on_delete=models.CASCADE,
        related_name="metadata_proposals",
    )
    source_upload = models.ForeignKey(
        UploadedDocument,
        on_delete=models.SET_NULL,
        related_name="metadata_proposals",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    provider = models.CharField(max_length=32, default="deepseek")
    model = models.CharField(max_length=128, blank=True)
    prompt_version = models.CharField(max_length=64, blank=True)
    input_fingerprint = models.CharField(max_length=64, blank=True)
    evidence_snapshot = models.JSONField(default=dict, blank=True)
    proposal = models.JSONField(default=dict, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    canonical_updated_at = models.DateTimeField()
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="requested_metadata_proposals",
        null=True,
        blank=True,
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="reviewed_metadata_proposals",
        null=True,
        blank=True,
    )
    accepted_before = models.JSONField(default=dict, blank=True)
    accepted_after = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-requested_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("canonical_document",),
                condition=models.Q(status__in=("queued", "running")),
                name="unique_active_metadata_proposal",
            )
        ]

    def __str__(self):
        return f"{self.canonical_document} · {self.status}"
