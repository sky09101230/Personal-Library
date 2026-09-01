from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.box_upload.models import CanonicalDocument, UploadedDocument

from ..artifacts import ArtifactReference, PARSE_ARTIFACT_CONTENT_TYPE
from ..jobs import backfill_processing, enqueue_processing, processing_status
from ..models import DocumentParse, DocumentProcessingJob, LiteratureChunk
from ..parsers import ParsedDocument, ParsedPage
from ..persistence import persist_parsed_document
from ..pipeline import SourcePdfTooLarge, download_source_pdf, process_next_job
from ..versions import PARSER_VERSION, current_versions


class ProcessingJobTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="job-test")
        self.upload = self.create_upload("first.pdf", "1")

    def create_upload(self, name, digest, *, file_role=UploadedDocument.FileRole.PRIMARY):
        canonical = CanonicalDocument.objects.create(title=name)
        return UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name=name,
            remote_path=f"/Literature/{name}",
            sha256=digest * 64,
            size=128,
            file_role=file_role,
        )

    def parsed_document(self, text="Worker page text."):
        return ParsedDocument(
            parser_name="pypdf",
            parser_version=PARSER_VERSION,
            pages=(ParsedPage(number=1, text=text),),
        )

    @staticmethod
    def artifact_writer(upload, job, parsed):
        return ArtifactReference(
            storage_backend=upload.storage_backend,
            path=f"/Literature/{job.run_id}.json",
            sha256="a" * 64,
            content_type=PARSE_ARTIFACT_CONTENT_TYPE,
            size=100,
        )

    def test_enqueue_reuses_active_and_current_success_but_force_appends(self):
        first, created = enqueue_processing(self.upload)
        active, active_created = enqueue_processing(self.upload)
        first.status = DocumentProcessingJob.Status.SUCCEEDED
        first.stage = DocumentProcessingJob.Stage.COMPLETE
        first.save(update_fields=("status", "stage", "updated_at"))
        succeeded, succeeded_created = enqueue_processing(self.upload)
        forced, forced_created = enqueue_processing(self.upload, force=True)
        forced_again, forced_again_created = enqueue_processing(self.upload, force=True)

        self.assertTrue(created)
        self.assertEqual(active.pk, first.pk)
        self.assertFalse(active_created)
        self.assertEqual(succeeded.pk, first.pk)
        self.assertFalse(succeeded_created)
        self.assertTrue(forced_created)
        self.assertNotEqual(forced.pk, first.pk)
        self.assertEqual(forced_again.pk, forced.pk)
        self.assertFalse(forced_again_created)
        self.assertEqual(DocumentProcessingJob.objects.count(), 2)

    def test_enqueue_does_not_reuse_success_from_an_older_pipeline_version(self):
        legacy = DocumentProcessingJob.objects.create(
            uploaded_document=self.upload,
            status=DocumentProcessingJob.Status.SUCCEEDED,
            stage=DocumentProcessingJob.Stage.COMPLETE,
            pipeline_version="literature-parse-v1",
            parser_version=PARSER_VERSION,
            chunker_version="page-chars-v1",
            prompt_version="overview-v1",
        )

        current, created = enqueue_processing(self.upload)

        self.assertTrue(created)
        self.assertNotEqual(current.pk, legacy.pk)
        self.assertEqual(current.pipeline_version, current_versions()["pipeline_version"])

    def test_worker_success_persists_parse_and_traceable_chunks(self):
        job, _ = enqueue_processing(self.upload)
        source = BytesIO(b"source")

        processed = process_next_job(
            downloader=lambda upload: source,
            parser=lambda file_obj, parser_name: self.parsed_document(),
            persister=lambda claimed_job, parsed: persist_parsed_document(
                claimed_job,
                parsed,
                artifact_writer=self.artifact_writer,
            ),
            overview_processor=lambda document_parse: None,
        )

        processed.refresh_from_db()
        document_parse = DocumentParse.objects.get(job=job)
        chunk = LiteratureChunk.objects.get(document_parse=document_parse)
        self.assertEqual(processed.status, DocumentProcessingJob.Status.SUCCEEDED)
        self.assertEqual(processed.stage, DocumentProcessingJob.Stage.COMPLETE)
        self.assertEqual(processed.attempt_count, 1)
        self.assertEqual(chunk.uploaded_document, self.upload)
        self.assertEqual(chunk.canonical_document, self.upload.canonical_document)
        self.assertTrue(source.closed)

    def test_worker_failure_keeps_upload_and_next_job_can_succeed(self):
        first_job, _ = enqueue_processing(self.upload)
        second_upload = self.create_upload("second.pdf", "2")
        second_job, _ = enqueue_processing(second_upload)

        with self.assertLogs("apps.literature_processing.pipeline", level="ERROR"):
            failed = process_next_job(
                downloader=lambda upload: BytesIO(b"source"),
                parser=lambda file_obj, parser_name: (_ for _ in ()).throw(
                    RuntimeError("secret backend detail")
                ),
            )
        succeeded = process_next_job(
            downloader=lambda upload: BytesIO(b"source"),
            parser=lambda file_obj, parser_name: self.parsed_document("Second job text."),
            persister=lambda claimed_job, parsed: persist_parsed_document(
                claimed_job,
                parsed,
                artifact_writer=self.artifact_writer,
            ),
            overview_processor=lambda document_parse: None,
        )

        failed.refresh_from_db()
        succeeded.refresh_from_db()
        self.assertEqual(failed.pk, first_job.pk)
        self.assertEqual(failed.status, DocumentProcessingJob.Status.FAILED)
        self.assertEqual(failed.error_code, "parse_failed")
        self.assertNotIn("secret", failed.error_message)
        self.assertTrue(UploadedDocument.objects.filter(pk=self.upload.pk).exists())
        self.assertEqual(succeeded.pk, second_job.pk)
        self.assertEqual(succeeded.status, DocumentProcessingJob.Status.SUCCEEDED)

    def test_backfill_is_bounded_idempotent_and_advances_past_covered_uploads(self):
        second_upload = self.create_upload("second.pdf", "2")
        self.create_upload("supplement.pdf", "3", file_role=UploadedDocument.FileRole.SUPPLEMENTARY)

        first = backfill_processing(limit=1)
        first_job = DocumentProcessingJob.objects.get(uploaded_document=self.upload)
        first_job.status = DocumentProcessingJob.Status.SUCCEEDED
        first_job.stage = DocumentProcessingJob.Stage.COMPLETE
        first_job.save(update_fields=("status", "stage", "updated_at"))
        second = backfill_processing(limit=1)
        repeated = backfill_processing(limit=1)

        self.assertEqual(first, {"created": 1, "reused": 0})
        self.assertEqual(second, {"created": 1, "reused": 0})
        self.assertEqual(repeated, {"created": 0, "reused": 0})
        self.assertTrue(DocumentProcessingJob.objects.filter(uploaded_document=second_upload).exists())
        self.assertEqual(DocumentProcessingJob.objects.count(), 2)

    def test_new_primary_upload_enqueues_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            upload = self.create_upload("signal.pdf", "4")

        job = DocumentProcessingJob.objects.get(uploaded_document=upload)
        self.assertEqual(job.status, DocumentProcessingJob.Status.QUEUED)
        for field, value in current_versions().items():
            self.assertEqual(getattr(job, field), value)

    def test_enqueue_failure_after_commit_does_not_fail_upload(self):
        with self.assertLogs("apps.literature_processing.jobs", level="ERROR"):
            with patch("apps.literature_processing.jobs.enqueue_processing", side_effect=RuntimeError("boom")):
                with self.captureOnCommitCallbacks(execute=True):
                    upload = self.create_upload("safe-signal.pdf", "5")

        self.assertTrue(UploadedDocument.objects.filter(pk=upload.pk).exists())
        self.assertFalse(DocumentProcessingJob.objects.filter(uploaded_document=upload).exists())

    def test_supplementary_upload_is_not_automatically_enqueued(self):
        with self.captureOnCommitCallbacks(execute=True):
            upload = self.create_upload(
                "supplement.csv",
                "6",
                file_role=UploadedDocument.FileRole.SUPPLEMENTARY,
            )

        self.assertFalse(DocumentProcessingJob.objects.filter(uploaded_document=upload).exists())

    def test_processing_status_uses_current_pipeline_coverage(self):
        initial = processing_status()
        job, _ = enqueue_processing(self.upload)
        queued = processing_status()
        job.status = DocumentProcessingJob.Status.FAILED
        job.save(update_fields=("status", "updated_at"))
        failed = processing_status()

        self.assertEqual(initial["uploads"], 1)
        self.assertEqual(initial["uncovered"], 1)
        self.assertEqual(queued["uncovered"], 0)
        self.assertEqual(queued["jobs"]["queued"], 1)
        self.assertEqual(failed["uncovered"], 1)
        self.assertEqual(failed["jobs"]["failed"], 1)


class SourcePdfDownloadTests(SimpleTestCase):
    class FakeStream:
        def __init__(self, chunks):
            self._chunks = chunks
            self.closed = False

        def iter_chunks(self):
            yield from self._chunks

        def close(self):
            self.closed = True

    def test_download_returns_seekable_file_and_closes_remote_stream(self):
        stream = self.FakeStream([b"pdf-", b"bytes"])

        result = download_source_pdf(object(), max_bytes=20, stream_opener=lambda upload: stream)

        self.assertEqual(result.read(), b"pdf-bytes")
        self.assertTrue(stream.closed)
        result.close()

    def test_download_limit_closes_remote_stream(self):
        stream = self.FakeStream([b"too", b"large"])

        with self.assertRaises(SourcePdfTooLarge):
            download_source_pdf(object(), max_bytes=5, stream_opener=lambda upload: stream)

        self.assertTrue(stream.closed)
