from django.core.management.base import BaseCommand
from apps.skills.candidate_services import scan_github_candidates
from apps.skills.models import SkillSyncJob
from apps.skills.services import InactiveSkillJob, mark_job_failed


class Command(BaseCommand):
    help = "Run a queued GitHub Skill candidate scan."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--source-id", type=int)

    def handle(self, *args, **options):
        job = SkillSyncJob.objects.get(pk=options["job_id"])
        try:
            scan_github_candidates(job=job, source_id=options["source_id"])
        except InactiveSkillJob:
            return
        except Exception as exc:
            mark_job_failed(job, exc)
