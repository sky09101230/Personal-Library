from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.skills.models import SkillSyncJob
from apps.skills.services import enrich_shared_skills


class Command(BaseCommand):
    help = "Regenerate Skill summaries and classifications without accessing archive storage."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--source-id", type=int)

    def handle(self, *args, **options):
        job = SkillSyncJob.objects.get(pk=options["job_id"])
        try:
            enrich_shared_skills(job=job, source_id=options["source_id"])
        except Exception as exc:
            if job.status != SkillSyncJob.FAILED:
                job.status = SkillSyncJob.FAILED
                job.error = str(exc)
                job.finished_at = timezone.now()
                job.save(update_fields=["status", "error", "finished_at"])
