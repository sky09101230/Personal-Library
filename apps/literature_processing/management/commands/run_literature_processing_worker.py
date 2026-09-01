import time

from django.core.management.base import BaseCommand

from apps.literature_processing.pipeline import process_next_job


class Command(BaseCommand):
    help = "Process queued literature parsing jobs with one database-backed worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Exit when the queue is empty.")
        parser.add_argument("--max-jobs", type=int, default=0, help="Maximum jobs before exit; zero means unlimited.")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options):
        processed = 0
        max_jobs = max(0, options["max_jobs"])
        while True:
            job = process_next_job()
            if job is None:
                if options["once"] or (max_jobs and processed >= max_jobs):
                    break
                time.sleep(max(0.2, options["poll_interval"]))
                continue
            processed += 1
            self.stdout.write(f"job={job.pk} status={job.status} stage={job.stage}")
            if max_jobs and processed >= max_jobs:
                break
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} literature processing job(s)."))

