from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import CanonicalDocument, UploadedDocument, UploadReviewBatch, UploadReviewItem
from .services import LiteratureStorageError
from .storage import NAS_WEBDAV, StoredLiteratureObject


class UploadReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="Strong-pass-1234")
        self.client.force_login(self.user)

    def create_batch(self):
        response = self.client.post("/upload/batches/")
        self.assertEqual(response.status_code, 200)
        return UploadReviewBatch.objects.get(pk=response.json()["batch_id"])

    def create_item(self, metadata=None, batch=None, filename="paper.pdf", digest="a" * 64):
        return UploadReviewItem.objects.create(
            batch=batch or self.create_batch(),
            original_name=filename,
            remote_path=f"/staged/{filename}",
            storage_backend=NAS_WEBDAV,
            sha256=digest,
            size=100,
            metadata=metadata or {"title": "Paper", "journal": "Journal", "doi": "10.1000/paper"},
            evidence={"pdf": {"title": "Paper"}},
        )

    def test_upload_page_shows_four_channels_and_review_table(self):
        response = self.client.get("/upload/")

        self.assertContains(response, "const MAX_CHANNELS = 4")
        self.assertContains(response, "本批 metadata 审核")
        self.assertContains(response, "missing-title")
        self.assertContains(response, "missing-journal")
        self.assertContains(response, "重新解析")
        self.assertContains(response, "review.scrollIntoView({behavior: 'smooth', block: 'start'})")
        self.assertContains(response, 'window.location.assign("/library/")')

    @patch(
        "apps.box_upload.upload_review.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/staged/no-title.pdf"),
    )
    @patch("apps.box_upload.upload_review.extract_pdf_evidence", return_value={
        "title": "",
        "authors": [],
        "doi": "",
        "doi_candidates": [],
    })
    def test_staging_returns_missing_title_without_formal_database_writes(self, extract, store):
        batch = self.create_batch()

        response = self.client.post(
            f"/upload/batches/{batch.pk}/files/",
            data={"file": SimpleUploadedFile("no-title.pdf", b"%PDF-1.7\nbody")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["issue"], "missing_title")
        self.assertEqual(UploadReviewItem.objects.count(), 1)
        self.assertEqual(CanonicalDocument.objects.count(), 0)
        self.assertEqual(UploadedDocument.objects.count(), 0)
        extract.assert_called_once()
        store.assert_called_once()

    @patch("apps.box_upload.upload_review.fetch_doi_bibtex", return_value=(
        "@article{fixed, title={Resolved Paper}, author={Lovelace, Ada}, "
        "journal={Journal of Tests}, year={2026}, doi={10.1000/fixed}}"
    ))
    def test_uploader_can_save_title_and_reparse_doi(self, fetch):
        item = self.create_item(metadata={"title": "", "journal": "", "doi": ""})

        title_response = self.client.post(
            f"/upload/review-items/{item.pk}/",
            data={"action": "save_title", "title": "  Manual   title  "},
        )
        doi_response = self.client.post(
            f"/upload/review-items/{item.pk}/",
            data={"action": "reparse_doi", "doi": "https://doi.org/10.1000/FIXED"},
        )

        self.assertEqual(title_response.json()["item"]["metadata"]["title"], "Manual title")
        self.assertEqual(doi_response.status_code, 200)
        self.assertEqual(doi_response.json()["item"]["metadata"]["title"], "Resolved Paper")
        self.assertEqual(doi_response.json()["item"]["metadata"]["journal"], "Journal of Tests")
        self.assertEqual(doi_response.json()["item"]["metadata"]["doi"], "10.1000/fixed")
        fetch.assert_called_once_with("10.1000/fixed")
        self.assertFalse(CanonicalDocument.objects.exists())

    def test_invalid_doi_reparse_keeps_pending_item_unchanged(self):
        item = self.create_item(metadata={"title": "Manual", "journal": "", "doi": ""})

        response = self.client.post(
            f"/upload/review-items/{item.pk}/",
            data={"action": "reparse_doi", "doi": "not-a-doi"},
        )

        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.metadata["title"], "Manual")
        self.assertEqual(item.metadata["doi"], "")

    def test_other_user_cannot_access_pending_batch_or_item(self):
        item = self.create_item()
        other = User.objects.create_user(username="other", password="Strong-pass-1234")
        self.client.force_login(other)

        self.assertEqual(self.client.post(f"/upload/review-items/{item.pk}/", data={"action": "save_title"}).status_code, 404)
        self.assertEqual(self.client.post(f"/upload/batches/{item.batch_id}/confirm/").status_code, 404)
        self.assertEqual(self.client.post(f"/upload/batches/{item.batch_id}/cancel/").status_code, 404)

    def test_missing_title_blocks_entire_confirmation(self):
        batch = self.create_batch()
        self.create_item(batch=batch, filename="valid.pdf")
        self.create_item(batch=batch, filename="missing.pdf", digest="b" * 64, metadata={"title": "", "journal": "Journal"})

        response = self.client.post(f"/upload/batches/{batch.pk}/confirm/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("missing.pdf", response.json()["message"])
        self.assertFalse(CanonicalDocument.objects.exists())
        self.assertFalse(UploadedDocument.objects.exists())
        batch.refresh_from_db()
        self.assertEqual(batch.status, UploadReviewBatch.Status.PENDING)

    def test_confirmed_warning_item_creates_published_formal_records(self):
        item = self.create_item(metadata={
            "title": "Confirmed preprint",
            "journal": "",
            "doi": "10.1000/preprint",
            "authors": [{"name": "Ada Lovelace"}],
            "publication_year": 2026,
            "metadata_source": "bibtex",
        })

        response = self.client.post(f"/upload/batches/{item.batch_id}/confirm/")

        self.assertEqual(response.status_code, 200)
        canonical = CanonicalDocument.objects.get()
        upload = UploadedDocument.objects.get()
        self.assertEqual(canonical.title, "Confirmed preprint")
        self.assertEqual(canonical.journal, "")
        self.assertEqual(canonical.metadata_status, CanonicalDocument.MetadataStatus.VERIFIED)
        self.assertEqual(canonical.index_status, CanonicalDocument.IndexStatus.PUBLISHED)
        self.assertEqual(upload.remote_path, item.remote_path)
        item.batch.refresh_from_db()
        self.assertEqual(item.batch.status, UploadReviewBatch.Status.COMMITTED)

    @patch("apps.box_upload.upload_review.UploadedDocument.objects.create", side_effect=RuntimeError("db failed"))
    def test_formal_database_failure_rolls_back_and_keeps_staging(self, create_upload):
        item = self.create_item()

        with self.assertRaises(RuntimeError):
            self.client.post(f"/upload/batches/{item.batch_id}/confirm/")

        self.assertFalse(CanonicalDocument.objects.exists())
        self.assertFalse(UploadedDocument.objects.exists())
        item.batch.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.batch.status, UploadReviewBatch.Status.PENDING)
        self.assertEqual(item.remote_path, "/staged/paper.pdf")
        self.assertEqual(item.commit_result, {})
        create_upload.assert_called_once()

    @patch("apps.box_upload.upload_review.delete_literature")
    def test_existing_document_is_associated_and_redundant_stage_is_deleted(self, delete):
        owner = User.objects.create_user(username="owner", password="Strong-pass-1234")
        canonical = CanonicalDocument.objects.create(
            title="Existing",
            doi="10.1000/paper",
            index_status=CanonicalDocument.IndexStatus.PUBLISHED,
        )
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=owner,
            original_name="existing.pdf",
            remote_path="/existing.pdf",
            sha256="c" * 64,
            size=1,
        )
        item = self.create_item(digest="d" * 64)

        response = self.client.post(f"/upload/batches/{item.batch_id}/confirm/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["state"], "merged")
        self.assertEqual(UploadedDocument.objects.count(), 1)
        self.assertTrue(canonical.uploaders.filter(pk=self.user.pk).exists())
        delete.assert_called_once()

    @patch("apps.box_upload.upload_review.delete_literature")
    def test_uploader_can_cancel_pending_batch(self, delete):
        item = self.create_item()

        response = self.client.post(f"/upload/batches/{item.batch_id}/cancel/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(UploadReviewBatch.objects.exists())
        self.assertFalse(UploadReviewItem.objects.exists())
        delete.assert_called_once()

    @patch("apps.box_upload.upload_review.delete_literature", side_effect=LiteratureStorageError("offline"))
    def test_cancel_failure_keeps_staging_tracking(self, delete):
        item = self.create_item()

        response = self.client.post(f"/upload/batches/{item.batch_id}/cancel/")

        self.assertEqual(response.status_code, 502)
        self.assertTrue(UploadReviewItem.objects.filter(pk=item.pk).exists())
        self.assertTrue(UploadReviewBatch.objects.filter(pk=item.batch_id).exists())
        delete.assert_called_once()

    @override_settings(MCP_MAX_UPLOAD_BYTES=12)
    @patch("apps.box_upload.upload_review.store_literature")
    def test_invalid_or_oversized_pdf_never_reaches_storage(self, store):
        batch = self.create_batch()

        wrong_type = self.client.post(
            f"/upload/batches/{batch.pk}/files/",
            data={"file": SimpleUploadedFile("notes.txt", b"not pdf")},
        )
        too_large = self.client.post(
            f"/upload/batches/{batch.pk}/files/",
            data={"file": SimpleUploadedFile("large.pdf", b"%PDF-1.7\nlarge")},
        )

        self.assertEqual(wrong_type.status_code, 400)
        self.assertEqual(too_large.status_code, 400)
        self.assertFalse(UploadReviewItem.objects.exists())
        store.assert_not_called()
