from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..models import DocumentParse, DocumentProcessingJob
from ..storage_layout import migrate_literature_layout


class FakeLayoutStorage:
    name = "nas_webdav"
    root = "/Literature"

    def __init__(self, objects=()):
        self.objects = set(objects)
        self.moves = []
        self.fail_move = False

    def path_for(self, namespace, basename):
        if not basename or "/" in basename or "\\" in basename:
            raise ValueError("invalid basename")
        return f"{self.root}/{namespace}/{basename}"

    def exists(self, remote_path):
        return remote_path in self.objects

    def move(self, source_path, destination_path):
        if self.fail_move:
            raise RuntimeError("remote move failed")
        if source_path not in self.objects or destination_path in self.objects:
            raise RuntimeError("unsafe move")
        self.objects.remove(source_path)
        self.objects.add(destination_path)
        self.moves.append((source_path, destination_path))


class LiteratureStorageLayoutMigrationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="layout-test")
        canonical = CanonicalDocument.objects.create(title="Layout paper")
        self.upload = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=user,
            original_name="paper.pdf",
            remote_path="/Literature/paper.pdf",
            sha256="1" * 64,
            size=100,
        )
        job = DocumentProcessingJob.objects.create(
            uploaded_document=self.upload,
            status=DocumentProcessingJob.Status.SUCCEEDED,
            stage=DocumentProcessingJob.Stage.COMPLETE,
            pipeline_version="pipeline-v1",
            parser_version="parser-v1",
            chunker_version="chunker-v1",
            prompt_version="prompt-v1",
        )
        self.document_parse = DocumentParse.objects.create(
            job=job,
            parser_name="test",
            parser_version="parser-v1",
            schema_version="plab.parse.v1",
            page_count=1,
            artifact_storage_backend="nas_webdav",
            artifact_path="/Literature/parse.json",
            artifact_sha256="2" * 64,
            artifact_size=100,
        )

    def run_migration(self, storage, *, dry_run=False):
        return migrate_literature_layout(
            dry_run=dry_run,
            storage_factory=lambda backend: storage,
        )

    def test_dry_run_plans_moves_without_changing_remote_or_database(self):
        storage = FakeLayoutStorage({"/Literature/paper.pdf", "/Literature/parse.json"})

        result = self.run_migration(storage, dry_run=True)

        self.assertEqual(result.counts, {"would_move": 2})
        self.assertEqual(storage.moves, [])
        self.upload.refresh_from_db()
        self.document_parse.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/paper.pdf")
        self.assertEqual(self.document_parse.artifact_path, "/Literature/parse.json")

    def test_move_succeeds_before_database_paths_are_updated(self):
        storage = FakeLayoutStorage({"/Literature/paper.pdf", "/Literature/parse.json"})

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"moved": 2})
        self.upload.refresh_from_db()
        self.document_parse.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/originals/paper.pdf")
        self.assertEqual(self.document_parse.artifact_path, "/Literature/derived/parses/parse.json")
        self.assertEqual(
            storage.moves,
            [
                ("/Literature/paper.pdf", "/Literature/originals/paper.pdf"),
                ("/Literature/parse.json", "/Literature/derived/parses/parse.json"),
            ],
        )

    def test_repeated_run_reports_existing_targets_without_remote_writes(self):
        storage = FakeLayoutStorage({"/Literature/paper.pdf", "/Literature/parse.json"})
        self.run_migration(storage)
        storage.moves.clear()

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"already": 2})
        self.assertEqual(storage.moves, [])

    def test_source_missing_destination_present_recovers_database_only(self):
        storage = FakeLayoutStorage(
            {
                "/Literature/originals/paper.pdf",
                "/Literature/derived/parses/parse.json",
            }
        )

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"recovered": 2})
        self.assertEqual(storage.moves, [])
        self.upload.refresh_from_db()
        self.document_parse.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/originals/paper.pdf")
        self.assertEqual(self.document_parse.artifact_path, "/Literature/derived/parses/parse.json")

    def test_both_paths_present_reports_conflict_without_changes(self):
        storage = FakeLayoutStorage(
            {
                "/Literature/paper.pdf",
                "/Literature/originals/paper.pdf",
                "/Literature/parse.json",
                "/Literature/derived/parses/parse.json",
            }
        )

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"conflict": 2})
        self.assertEqual(storage.moves, [])
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/paper.pdf")

    def test_both_paths_missing_reports_conflict_without_changes(self):
        storage = FakeLayoutStorage()

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"conflict": 2})
        self.assertFalse(result.dry_run)
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/paper.pdf")

    def test_remote_move_failure_does_not_update_database(self):
        storage = FakeLayoutStorage({"/Literature/paper.pdf", "/Literature/parse.json"})
        storage.fail_move = True

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"error": 2})
        self.upload.refresh_from_db()
        self.document_parse.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/paper.pdf")
        self.assertEqual(self.document_parse.artifact_path, "/Literature/parse.json")

    def test_different_sources_with_same_destination_are_conflicts(self):
        second = UploadedDocument.objects.create(
            canonical_document=self.upload.canonical_document,
            uploader=self.upload.uploader,
            original_name="other.pdf",
            remote_path="/Literature/legacy/paper.pdf",
            sha256="3" * 64,
            size=100,
        )
        storage = FakeLayoutStorage(
            {
                "/Literature/paper.pdf",
                "/Literature/legacy/paper.pdf",
                "/Literature/parse.json",
            }
        )

        result = self.run_migration(storage)

        upload_actions = [action for action in result.actions if action.record_type == "upload"]
        self.assertTrue(all(action.status == "conflict" for action in upload_actions))
        self.upload.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "/Literature/paper.pdf")
        self.assertEqual(second.remote_path, "/Literature/legacy/paper.pdf")

    def test_invalid_record_path_reports_error_and_continues(self):
        self.upload.remote_path = ""
        self.upload.save(update_fields=("remote_path",))
        storage = FakeLayoutStorage({"/Literature/parse.json"})

        result = self.run_migration(storage)

        self.assertEqual(result.counts, {"error": 1, "moved": 1})
        self.upload.refresh_from_db()
        self.document_parse.refresh_from_db()
        self.assertEqual(self.upload.remote_path, "")
        self.assertEqual(self.document_parse.artifact_path, "/Literature/derived/parses/parse.json")
