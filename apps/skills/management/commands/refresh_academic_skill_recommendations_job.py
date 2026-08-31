from django.core.management.base import BaseCommand

from apps.skills.models import SkillSyncJob
from apps.skills.recommendations import run_academic_recommendation_job


class Command(BaseCommand):
    help = "Refresh the administrator-only academic GitHub Skill recommendation snapshot."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)

    def handle(self, *args, **options):
        job = SkillSyncJob.objects.get(pk=options["job_id"])
        run_academic_recommendation_job(job)
