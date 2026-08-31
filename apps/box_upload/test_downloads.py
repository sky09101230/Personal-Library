from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .downloads import build_literature_download_url
from .models import CanonicalDocument, UploadedDocument


@override_settings(
    MCP_PUBLIC_BASE_URL="https://plab.example.test",
    LITERATURE_DOWNLOAD_LINK_MAX_AGE=300,
)
class SignedLiteratureDownloadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="download-owner", password="Strong-pass-1234")
        self.canonical = CanonicalDocument.objects.create(
            sha256="f" * 64,
            index_status=CanonicalDocument.IndexStatus.PUBLISHED,
        )
        self.document = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=self.user,
            original_name="signed-paper.pdf",
            remote_path="/public/PLAB_KnowledgeBase/Literature/signed-paper.pdf",
            storage_backend=UploadedDocument.StorageBackend.NAS_WEBDAV,
            sha256="f" * 64,
            size=8,
            content_type="application/pdf",
        )

    @patch("apps.box_upload.views.open_literature_stream")
    def test_valid_signed_link_streams_published_document_without_login(self, open_stream):
        upstream = MagicMock(status=200)
        upstream.iter_chunks.return_value = iter((b"%PDF-1.7",))
        upstream.get_header.return_value = None
        open_stream.return_value = upstream
        path = urlsplit(build_literature_download_url(self.document)).path

        response = self.client.get(path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.7")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        open_stream.assert_called_once()
        self.assertEqual(open_stream.call_args.args[0].pk, self.document.pk)

    @patch("apps.box_upload.views.open_literature_stream")
    def test_signed_link_rechecks_publication_status(self, open_stream):
        path = urlsplit(build_literature_download_url(self.document)).path
        self.canonical.index_status = CanonicalDocument.IndexStatus.PENDING
        self.canonical.save(update_fields=["index_status"])

        response = self.client.get(path)

        self.assertEqual(response.status_code, 404)
        open_stream.assert_not_called()

    @patch("apps.box_upload.views.open_literature_stream")
    def test_tampered_signed_link_does_not_access_storage(self, open_stream):
        path = urlsplit(build_literature_download_url(self.document)).path
        token = path.rstrip("/").rsplit("/", 1)[-1]
        tampered_path = path.replace(token, f"{token}x")

        response = self.client.get(tampered_path)

        self.assertEqual(response.status_code, 404)
        open_stream.assert_not_called()

    @override_settings(LITERATURE_DOWNLOAD_LINK_MAX_AGE=-1)
    @patch("apps.box_upload.views.open_literature_stream")
    def test_expired_signed_link_does_not_access_storage(self, open_stream):
        path = urlsplit(build_literature_download_url(self.document)).path

        response = self.client.get(path)

        self.assertEqual(response.status_code, 404)
        open_stream.assert_not_called()
