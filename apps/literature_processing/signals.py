from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.box_upload.models import UploadedDocument

from .jobs import enqueue_processing_safely
from .models import DocumentProcessingJob


@receiver(post_save, sender=UploadedDocument, dispatch_uid="literature_processing.enqueue_uploaded_pdf")
def enqueue_uploaded_pdf(sender, instance, created, **kwargs):
    if not created:
        return
    if (
        instance.status != UploadedDocument.Status.UPLOADED
        or instance.file_role != UploadedDocument.FileRole.PRIMARY
    ):
        return
    transaction.on_commit(
        lambda upload_id=instance.pk: enqueue_processing_safely(
            upload_id,
            parser_name="mineru",
            queue_lane=DocumentProcessingJob.QueueLane.REALTIME,
        )
    )
