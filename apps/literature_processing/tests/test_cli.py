from io import StringIO
from types import SimpleNamespace
from unittest.mock import ANY, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..models import DocumentProcessingJob
from ..operations import ProcessExistingResult, process_existing
from ..storage_layout import LayoutAction, LayoutMigrationResult
from ..worker import WorkerResult, run_worker
from ..parsers.mineru.client import MinerUConfig


class WorkerServiceTests(SimpleTestCase):
    def test_worker_counts_results_and_reports_each_job(self):
        jobs = iter(
            (
                SimpleNamespace(status=DocumentProcessingJob.Status.SUCCEEDED),
                SimpleNamespace(status=DocumentProcessingJob.Status.FAILED),
                None,
            )
        )
        reported = []

        result = run_worker(
            once=True,
            process_func=lambda: next(jobs),
            on_job=reported.append,
        )

        self.assertEqual(result, WorkerResult(processed=2, succeeded=1, failed=1))
        self.assertEqual(len(reported), 2)

    def test_worker_honors_max_jobs(self):
        calls = []

        result = run_worker(
            max_jobs=1,
            process_func=lambda: calls.append(1) or SimpleNamespace(
                status=DocumentProcessingJob.Status.SUCCEEDED
            ),
        )

        self.assertEqual(result.processed, 1)
        self.assertEqual(calls, [1])

    def test_worker_passes_lane_and_channel_to_process_service(self):
        calls = []

        result = run_worker(
            once=True,
            queue_lane=DocumentProcessingJob.QueueLane.BACKFILL,
            worker_channel="backfill-2",
            process_func=lambda **kwargs: calls.append(kwargs) or None,
        )

        self.assertEqual(result, WorkerResult(processed=0, succeeded=0, failed=0))
        self.assertEqual(calls, [{
            "queue_lane": DocumentProcessingJob.QueueLane.BACKFILL,
            "worker_channel": "backfill-2",
        }])

    @patch.dict("os.environ", {}, clear=True)
    def test_worker_scopes_mineru_token_without_mutating_environment(self):
        tokens = []

        run_worker(
            once=True,
            mineru_api_token="thread-token",
            process_func=lambda: tokens.append(MinerUConfig.from_environment().token) or None,
        )

        self.assertEqual(tokens, ["thread-token"])

    def test_process_existing_composes_backfill_and_worker(self):
        backfill_calls = []
        worker_calls = []

        result = process_existing(
            limit=7,
            force=True,
            max_jobs=3,
            backfill=lambda **kwargs: backfill_calls.append(kwargs) or {"created": 2, "reused": 1},
            worker=lambda **kwargs: worker_calls.append(kwargs)
            or WorkerResult(processed=2, succeeded=2, failed=0),
        )

        self.assertEqual(result.created, 2)
        self.assertEqual(result.reused, 1)
        self.assertEqual(backfill_calls, [{"limit": 7, "force": True}])
        self.assertEqual(worker_calls[0]["once"], True)
        self.assertEqual(worker_calls[0]["max_jobs"], 3)


class PlabCommandTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="cli-test")
        canonical = CanonicalDocument.objects.create(title="CLI paper")
        self.upload = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=user,
            original_name="cli.pdf",
            remote_path="/Literature/cli.pdf",
            sha256="9" * 64,
            size=100,
        )

    @patch("apps.literature_processing.management.commands.plab.backfill_processing")
    def test_literature_backfill_delegates_to_service(self, backfill):
        backfill.return_value = {"created": 3, "reused": 2}
        output = StringIO()

        call_command(
            "plab",
            "literature",
            "backfill",
            "--limit",
            "7",
            "--force",
            stdout=output,
        )

        backfill.assert_called_once_with(limit=7, force=True)
        self.assertIn("Queued 3; reused/skipped 2", output.getvalue())

    @patch("apps.literature_processing.management.commands.plab.enqueue_processing")
    def test_literature_enqueue_delegates_to_service(self, enqueue):
        enqueue.return_value = (SimpleNamespace(pk=12, status="queued"), True)
        output = StringIO()

        call_command(
            "plab",
            "literature",
            "enqueue",
            "--upload-id",
            str(self.upload.pk),
            stdout=output,
        )

        enqueue.assert_called_once_with(self.upload, force=False, parser_name="pypdf")
        self.assertIn("job=12 parser=pypdf status=queued created=yes", output.getvalue())

    @patch("apps.literature_processing.management.commands.plab.enqueue_processing")
    def test_literature_enqueue_accepts_explicit_mineru_parser(self, enqueue):
        enqueue.return_value = (SimpleNamespace(pk=13, status="queued"), True)

        call_command(
            "plab",
            "literature",
            "enqueue",
            "--upload-id",
            str(self.upload.pk),
            "--parser",
            "mineru",
            stdout=StringIO(),
        )

        enqueue.assert_called_once_with(self.upload, force=False, parser_name="mineru")

    @patch("apps.literature_processing.management.commands.plab.run_worker")
    def test_literature_worker_delegates_to_shared_loop(self, worker):
        worker.return_value = WorkerResult(processed=2, succeeded=1, failed=1)
        output = StringIO()

        call_command(
            "plab",
            "literature",
            "worker",
            "--once",
            "--max-jobs",
            "4",
            "--poll-interval",
            "0.5",
            stdout=output,
        )

        worker.assert_called_once_with(
            once=True,
            max_jobs=4,
            poll_interval=0.5,
            on_job=ANY,
        )
        self.assertIn("Processed 2; succeeded 1; failed 1", output.getvalue())

    @patch("apps.literature_processing.management.commands.plab.processing_status")
    def test_literature_status_delegates_to_service(self, status):
        status.return_value = {
            "uploads": 10,
            "uncovered": 2,
            "jobs": {"queued": 1, "running": 2, "succeeded": 3, "failed": 4},
        }
        output = StringIO()

        call_command("plab", "literature", "status", stdout=output)

        self.assertIn("uploads=10 uncovered=2 queued=1 running=2 succeeded=3 failed=4", output.getvalue())

    @patch("apps.literature_processing.management.commands.plab.process_existing")
    def test_process_existing_delegates_to_composed_service(self, process):
        process.return_value = ProcessExistingResult(
            created=2,
            reused=1,
            worker=WorkerResult(processed=2, succeeded=2, failed=0),
        )
        output = StringIO()

        call_command(
            "plab",
            "literature",
            "process-existing",
            "--limit",
            "8",
            "--max-jobs",
            "5",
            stdout=output,
        )

        process.assert_called_once_with(
            limit=8,
            force=False,
            max_jobs=5,
            on_job=ANY,
        )
        self.assertIn("Queued 2; reused/skipped 1", output.getvalue())

    @patch("apps.literature_processing.management.commands.plab.migrate_literature_layout")
    def test_storage_dry_run_delegates_and_reports_actions(self, migrate):
        migrate.return_value = LayoutMigrationResult(
            dry_run=True,
            actions=(
                LayoutAction(
                    record_type="upload",
                    record_id=1,
                    status="would_move",
                    source_path="/Literature/a.pdf",
                    destination_path="/Literature/originals/a.pdf",
                ),
            ),
        )
        output = StringIO()

        call_command(
            "plab",
            "storage",
            "migrate-literature-layout",
            "--dry-run",
            stdout=output,
        )

        migrate.assert_called_once_with(dry_run=True)
        self.assertIn("would_move upload:1", output.getvalue())
        self.assertIn("dry_run=yes would_move=1", output.getvalue())

    @patch("apps.literature_processing.management.commands.plab.migrate_literature_layout")
    def test_storage_conflict_returns_command_error_after_report(self, migrate):
        migrate.return_value = LayoutMigrationResult(
            dry_run=True,
            actions=(
                LayoutAction(
                    record_type="upload",
                    record_id=1,
                    status="conflict",
                    source_path="/Literature/a.pdf",
                    destination_path="/Literature/originals/a.pdf",
                    message="both exist",
                ),
            ),
        )
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "plab",
                "storage",
                "migrate-literature-layout",
                "--dry-run",
                stdout=output,
            )

        self.assertIn("conflict upload:1", output.getvalue())

    @patch("apps.literature_processing.management.commands.run_literature_processing_worker.run_worker")
    def test_legacy_worker_uses_shared_loop(self, worker):
        worker.return_value = WorkerResult(processed=0, succeeded=0, failed=0)

        call_command("run_literature_processing_worker", "--once", stdout=StringIO())

        worker.assert_called_once_with(
            once=True,
            max_jobs=0,
            poll_interval=2.0,
            on_job=ANY,
        )
