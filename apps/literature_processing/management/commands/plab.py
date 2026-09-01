from django.core.management.base import BaseCommand, CommandError

from apps.box_upload.models import UploadedDocument
from apps.literature_processing.jobs import (
    backfill_processing,
    enqueue_processing,
    processing_status,
)
from apps.literature_processing.models import DocumentProcessingJob
from apps.literature_processing.operations import process_existing
from apps.literature_processing.storage_layout import migrate_literature_layout
from apps.literature_processing.worker import run_worker
from apps.literature_processing.worker_pool import (
    WorkerPoolConfigurationError,
    WorkerPoolError,
    resolve_worker_token,
    run_worker_pool,
)


class Command(BaseCommand):
    help = "Unified PLAB literature and storage operations."

    def add_arguments(self, parser):
        areas = parser.add_subparsers(dest="area", required=True)
        literature = areas.add_parser("literature", help="Literature processing operations.")
        literature_commands = literature.add_subparsers(dest="operation", required=True)

        backfill = literature_commands.add_parser("backfill", help="Queue historical primary PDFs.")
        backfill.add_argument("--limit", type=int, default=100)
        backfill.add_argument("--force", action="store_true")
        backfill.add_argument("--parser", choices=("pypdf", "mineru"), default="mineru")

        enqueue = literature_commands.add_parser("enqueue", help="Queue one uploaded primary PDF.")
        enqueue.add_argument("--upload-id", type=int, required=True)
        enqueue.add_argument("--force", action="store_true")
        enqueue.add_argument("--parser", choices=("pypdf", "mineru"), default="pypdf")
        enqueue.add_argument(
            "--lane",
            choices=DocumentProcessingJob.QueueLane.values,
            default=DocumentProcessingJob.QueueLane.BACKFILL,
        )

        worker = literature_commands.add_parser("worker", help="Run the database-backed worker.")
        _add_worker_arguments(worker)
        worker.add_argument("--lane", choices=("all", *DocumentProcessingJob.QueueLane.values), default="all")
        worker.add_argument("--token-slot", type=int)

        worker_pool = literature_commands.add_parser(
            "worker-pool",
            help="Run one realtime and four backfill MinerU worker channels.",
        )
        worker_pool.add_argument("--poll-interval", type=float, default=2.0)

        literature_commands.add_parser("status", help="Show processing coverage and job counts.")

        process = literature_commands.add_parser(
            "process-existing",
            help="Queue uncovered historical PDFs and process the queue.",
        )
        process.add_argument("--limit", type=int, default=100)
        process.add_argument("--force", action="store_true")
        process.add_argument("--max-jobs", type=int, default=0)
        process.add_argument("--parser", choices=("pypdf", "mineru"), default="pypdf")
        process.add_argument(
            "--lane",
            choices=DocumentProcessingJob.QueueLane.values,
            default=DocumentProcessingJob.QueueLane.BACKFILL,
        )

        storage = areas.add_parser("storage", help="Literature storage operations.")
        storage_commands = storage.add_subparsers(dest="operation", required=True)
        migrate = storage_commands.add_parser(
            "migrate-literature-layout",
            help="Move legacy literature objects into originals/ and derived/parses/.",
        )
        migrate.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["area"] == "literature":
            return self._handle_literature(options)
        if options["area"] == "storage":
            return self._handle_storage(options)
        raise CommandError("Unsupported PLAB command area.")

    def _handle_literature(self, options):
        operation = options["operation"]
        if operation == "backfill":
            result = backfill_processing(
                limit=options["limit"],
                force=options["force"],
                parser_name=options["parser"],
                queue_lane=DocumentProcessingJob.QueueLane.BACKFILL,
            )
            self.stdout.write(self.style.SUCCESS(_queue_summary(result)))
            return
        if operation == "enqueue":
            try:
                upload = UploadedDocument.objects.get(pk=options["upload_id"])
            except UploadedDocument.DoesNotExist as exc:
                raise CommandError(f"Upload {options['upload_id']} does not exist.") from exc
            job, created = enqueue_processing(
                upload,
                force=options["force"],
                parser_name=options["parser"],
                queue_lane=options["lane"],
            )
            if job is None:
                raise CommandError(f"Upload {upload.pk} is not an eligible primary PDF.")
            self.stdout.write(
                self.style.SUCCESS(
                    f"job={job.pk} parser={options['parser']} status={job.status} "
                    f"created={'yes' if created else 'no'}"
                )
            )
            return
        if operation == "worker":
            queue_lane = None if options["lane"] == "all" else options["lane"]
            try:
                token, worker_channel = resolve_worker_token(
                    queue_lane,
                    options["token_slot"],
                )
            except WorkerPoolConfigurationError as exc:
                raise CommandError(str(exc)) from exc
            result = run_worker(
                once=options["once"],
                max_jobs=options["max_jobs"],
                poll_interval=options["poll_interval"],
                on_job=self._report_job,
                queue_lane=queue_lane,
                worker_channel=worker_channel,
                mineru_api_token=token,
            )
            self.stdout.write(self.style.SUCCESS(_worker_summary(result)))
            return
        if operation == "worker-pool":
            try:
                run_worker_pool(
                    poll_interval=options["poll_interval"],
                    on_job=self._report_job,
                )
            except (WorkerPoolConfigurationError, WorkerPoolError) as exc:
                raise CommandError(str(exc)) from exc
            return
        if operation == "status":
            result = processing_status()
            jobs = result["jobs"]
            lanes = result["lanes"]
            self.stdout.write(
                " ".join(
                    (
                        f"uploads={result['uploads']}",
                        f"uncovered={result['uncovered']}",
                        f"queued={jobs['queued']}",
                        f"running={jobs['running']}",
                        f"succeeded={jobs['succeeded']}",
                        f"failed={jobs['failed']}",
                        f"realtime_queued={lanes[DocumentProcessingJob.QueueLane.REALTIME][DocumentProcessingJob.Status.QUEUED]}",
                        f"realtime_running={lanes[DocumentProcessingJob.QueueLane.REALTIME][DocumentProcessingJob.Status.RUNNING]}",
                        f"backfill_queued={lanes[DocumentProcessingJob.QueueLane.BACKFILL][DocumentProcessingJob.Status.QUEUED]}",
                        f"backfill_running={lanes[DocumentProcessingJob.QueueLane.BACKFILL][DocumentProcessingJob.Status.RUNNING]}",
                    )
                )
            )
            return
        if operation == "process-existing":
            result = process_existing(
                limit=options["limit"],
                force=options["force"],
                max_jobs=options["max_jobs"],
                on_job=self._report_job,
                parser_name=options["parser"],
                queue_lane=options["lane"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued {result.created}; reused/skipped {result.reused}. "
                    + _worker_summary(result.worker)
                )
            )
            return
        raise CommandError("Unsupported literature operation.")

    def _handle_storage(self, options):
        if options["operation"] != "migrate-literature-layout":
            raise CommandError("Unsupported storage operation.")
        result = migrate_literature_layout(dry_run=options["dry_run"])
        for action in result.actions:
            detail = f" message={action.message}" if action.message else ""
            self.stdout.write(
                f"{action.status} {action.record_type}:{action.record_id} "
                f"{action.source_path} -> {action.destination_path}{detail}"
            )
        counts = " ".join(
            f"{status}={count}"
            for status, count in sorted(result.counts.items())
        ) or "records=0"
        self.stdout.write(self.style.SUCCESS(f"dry_run={'yes' if result.dry_run else 'no'} {counts}"))
        if result.has_failures:
            raise CommandError("Literature layout migration completed with conflicts or errors.")

    def _report_job(self, job):
        self.stdout.write(
            f"job={job.pk} parser={job.parser_name} status={job.status} stage={job.stage}"
        )


def _add_worker_arguments(parser):
    parser.add_argument("--once", action="store_true", help="Exit when the queue is empty.")
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--poll-interval", type=float, default=2.0)


def _queue_summary(result):
    return f"Queued {result['created']}; reused/skipped {result['reused']}."


def _worker_summary(result):
    return (
        f"Processed {result.processed}; succeeded {result.succeeded}; "
        f"failed {result.failed}."
    )
