from django.core.management.base import BaseCommand

from apps.literature_processing.worker import run_worker


class Command(BaseCommand):
    help = "Process queued literature parsing jobs with one database-backed worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Exit when the queue is empty.")
        parser.add_argument("--max-jobs", type=int, default=0, help="Maximum jobs before exit; zero means unlimited.")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options):
        def report(job):
            self.stdout.write(f"job={job.pk} status={job.status} stage={job.stage}")

        result = run_worker(
            once=options["once"],
            max_jobs=options["max_jobs"],
            poll_interval=options["poll_interval"],
            on_job=report,
        )
        self.stdout.write(self.style.SUCCESS(f"Processed {result.processed} literature processing job(s)."))

