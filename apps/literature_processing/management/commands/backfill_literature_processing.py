from django.core.management.base import BaseCommand

from apps.literature_processing.jobs import backfill_processing


class Command(BaseCommand):
    help = "Queue a bounded batch of historical primary PDFs for literature processing."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        result = backfill_processing(limit=options["limit"], force=options["force"])
        self.stdout.write(
            self.style.SUCCESS(f"Queued {result['created']}; reused/skipped {result['reused']}.")
        )
