import os
import ssl
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .services import LiteratureStorageError
from .storage import NAS_WEBDAV, NJU_BOX, NasWebDavLiteratureStorage, get_literature_storage
from .metadata_jobs import _download_source_pdf


class NasWebDavLiteratureStorageTests(SimpleTestCase):
    config = {
        "NAS_WEBDAV_BASE_URL": "https://nas.example.test:5006",
        "NAS_WEBDAV_USERNAME": "service-user",
        "NAS_WEBDAV_PASSWORD": "service-password",
        "NAS_WEBDAV_LITERATURE_ROOT": "/public/PLAB_KnowledgeBase/Literature",
    }

    @patch.dict(os.environ, config, clear=False)
    def test_default_backend_is_nas_webdav(self):
        self.assertEqual(get_literature_storage().name, NAS_WEBDAV)

    @patch.dict(os.environ, {"LITERATURE_STORAGE_BACKEND": NJU_BOX}, clear=False)
    def test_nju_box_requires_explicit_selection(self):
        self.assertEqual(get_literature_storage().name, NJU_BOX)

    def test_rejects_missing_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(LiteratureStorageError, "NAS_WEBDAV_BASE_URL"):
                NasWebDavLiteratureStorage()

    def test_rejects_root_traversal(self):
        with self.assertRaisesMessage(LiteratureStorageError, "safe absolute path"):
            NasWebDavLiteratureStorage(
                "https://nas.example.test:5006",
                "user",
                "password",
                "/public/../private",
            )

    @patch.dict(os.environ, config, clear=False)
    @patch("apps.box_upload.storage.http.client.HTTPSConnection")
    def test_connection_only_disables_nas_certificate_verification(self, connection_class):
        NasWebDavLiteratureStorage()._connection()

        context = connection_class.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)
        default_context = ssl.create_default_context()
        self.assertEqual(default_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(default_context.check_hostname)

    @patch.dict(os.environ, config, clear=False)
    @patch("apps.box_upload.storage.http.client.HTTPSConnection")
    def test_ensure_root_creates_missing_directory(self, connection_class):
        first = MagicMock(status=404)
        second = MagicMock(status=201)
        connection_class.return_value.getresponse.side_effect = [first, second]

        NasWebDavLiteratureStorage(root="/public/PLAB_KnowledgeBase/Skills").ensure_root()

        self.assertEqual(connection_class.return_value.request.call_args_list[0].args[:2], ("PROPFIND", "/public/PLAB_KnowledgeBase/Skills"))
        self.assertEqual(connection_class.return_value.request.call_args_list[1].args[:2], ("MKCOL", "/public/PLAB_KnowledgeBase/Skills"))

    @patch.dict(os.environ, config, clear=False)
    @patch("apps.box_upload.storage.http.client.HTTPSConnection")
    def test_upload_streams_to_unique_object(self, connection_class):
        response = MagicMock(status=201)
        connection_class.return_value.getresponse.return_value = response
        uploaded_file = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\ncontent", content_type="application/pdf")

        path = NasWebDavLiteratureStorage().upload(uploaded_file)

        self.assertTrue(path.startswith("/public/PLAB_KnowledgeBase/Literature/"))
        self.assertTrue(path.endswith(".pdf"))
        connection = connection_class.return_value
        connection.putrequest.assert_called_once_with("PUT", path)
        connection.putheader.assert_any_call("Content-Length", str(uploaded_file.size))
        connection.putheader.assert_any_call("Content-Type", "application/pdf")
        connection.send.assert_called_once_with(b"%PDF-1.7\ncontent")
        response.read.assert_called_once_with()
        connection.close.assert_called_once_with()

    @patch.dict(os.environ, config, clear=False)
    @patch("apps.box_upload.storage.http.client.HTTPSConnection")
    def test_range_get_encodes_path_and_closes_connection(self, connection_class):
        connection = connection_class.return_value
        response = MagicMock(status=206)
        response.getheaders.return_value = [
            ("Content-Length", "8"),
            ("Content-Range", "bytes 0-7/100"),
        ]
        response.read.side_effect = [b"%PDF-1.", b""]
        connection.getresponse.return_value = response
        storage = NasWebDavLiteratureStorage()

        stream = storage.open_stream(
            "/public/PLAB_KnowledgeBase/Literature/测试 paper.pdf",
            byte_range="bytes=0-7",
        )

        self.assertEqual(b"".join(stream.iter_chunks()), b"%PDF-1.")
        connection.request.assert_called_once_with(
            "GET",
            "/public/PLAB_KnowledgeBase/Literature/%E6%B5%8B%E8%AF%95%20paper.pdf",
            headers={
                "Authorization": storage._authorization,
                "Accept": "*/*",
                "Range": "bytes=0-7",
            },
        )
        self.assertEqual(stream.get_header("Content-Range"), "bytes 0-7/100")
        response.close.assert_called_once_with()
        connection.close.assert_called_once_with()

    @patch.dict(os.environ, config, clear=False)
    @patch("apps.box_upload.storage.http.client.HTTPSConnection")
    def test_delete_uses_encoded_path(self, connection_class):
        response = MagicMock(status=204)
        connection_class.return_value.getresponse.return_value = response
        storage = NasWebDavLiteratureStorage()

        storage.delete("/public/PLAB_KnowledgeBase/Literature/a paper.pdf")

        connection_class.return_value.request.assert_called_once_with(
            "DELETE",
            "/public/PLAB_KnowledgeBase/Literature/a%20paper.pdf",
            headers={"Authorization": storage._authorization},
        )
        response.read.assert_called_once_with()

    @patch.dict(os.environ, config, clear=False)
    @patch("apps.box_upload.storage.http.client.HTTPSConnection")
    def test_remote_http_error_is_controlled(self, connection_class):
        connection_class.return_value.getresponse.return_value = MagicMock(status=403)
        storage = NasWebDavLiteratureStorage()

        with self.assertRaisesMessage(LiteratureStorageError, "HTTP 403"):
            storage.delete("/public/PLAB_KnowledgeBase/Literature/paper.pdf")

    @patch("apps.box_upload.metadata_jobs.open_literature_stream")
    def test_metadata_source_pdf_uses_record_storage(self, open_stream):
        stream = MagicMock()
        stream.iter_chunks.return_value = iter((b"%PDF-1.7", b"\ncontent"))
        open_stream.return_value = stream
        upload = MagicMock()

        pdf_file = _download_source_pdf(upload)

        self.assertEqual(pdf_file.read(), b"%PDF-1.7\ncontent")
        open_stream.assert_called_once_with(upload)
        stream.close.assert_called_once_with()
