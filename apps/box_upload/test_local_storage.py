import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.skills.candidate_services import create_uploaded_candidate, publish_candidate
from apps.skills.models import SkillPurpose
from apps.skills.storage import get_nas_skill_candidate_storage, get_nas_skill_storage, open_skill_stream
from apps.skills.test_candidates import skill_zip
from .services import LiteratureStorageError
from .ingestion import prepare_pdf, save_pdf_upload
from .models import CanonicalDocument
from .storage import get_literature_storage, store_literature


class LocalStorageTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, {"LITERATURE_STORAGE_BACKEND": "local", "LOCAL_STORAGE_ROOT": self.directory.name})
        env.start()
        self.addCleanup(env.stop)
        self.storage = get_literature_storage()

    def test_literature_lifecycle_ranges_and_no_overwrite(self):
        stored = store_literature(SimpleUploadedFile("paper.pdf", b"0123456789"))
        self.assertEqual(stored.backend, "local")
        self.assertTrue(stored.remote_path.startswith("originals/"))
        self.assertEqual(b"".join(self.storage.open_stream(stored.remote_path).iter_chunks()), b"0123456789")
        for value, status, content in [("bytes=2-5", 206, b"2345"), ("bytes=-3", 206, b"789"), ("bytes=7-", 206, b"789"), ("bytes=99-", 416, b""), ("bytes=-0", 416, b"")]:
            with self.subTest(value=value):
                stream = self.storage.open_stream(stored.remote_path, value)
                self.assertEqual(stream.status, status)
                self.assertEqual(b"".join(stream.iter_chunks()), content)
        other = self.storage.upload(SimpleUploadedFile("other.pdf", b"other"))
        with self.assertRaises(LiteratureStorageError):
            self.storage.move(stored.remote_path, other)
        self.assertTrue(self.storage.exists(stored.remote_path))
        derived = self.storage.upload(SimpleUploadedFile("parse.json", b"{}"), namespace="derived/parses")
        self.assertTrue(derived.startswith("derived/parses/"))
        destination = self.storage.path_for("originals", "moved.pdf")
        self.storage.move(stored.remote_path, destination)
        self.assertFalse(self.storage.exists(stored.remote_path))
        self.storage.delete(destination)
        self.assertFalse(self.storage.exists(destination))

    def test_rejects_unsafe_paths_and_symlink_escape(self):
        for value in ("../secret", "/absolute", "C:/secret", "dir\\secret", "x/../y", "x//y", "x:stream", "NUL.txt", "dir./x", ""):
            with self.subTest(value=value), self.assertRaises(LiteratureStorageError):
                self.storage.open_stream(value)
        self.storage.ensure_root()
        link = self.storage.root / "escape"
        try:
            link.symlink_to(Path(self.directory.name), target_is_directory=True)
        except OSError:
            return  # Windows may require Developer Mode to create symlinks.
        with self.assertRaises(LiteratureStorageError):
            self.storage.open_stream("escape/outside.pdf")

    def test_saved_document_download_requires_login_and_reads_local_bytes(self):
        user = User.objects.create_user(username="local-reader")
        canonical = CanonicalDocument.objects.create(title="Local PDF")
        payload = b"%PDF-1.4\nlocal storage smoke test"
        document = save_pdf_upload(canonical, user, prepare_pdf(SimpleUploadedFile("local.pdf", payload)))
        self.assertEqual(document.storage_backend, "local")
        url = f"/library/download/{document.pk}/"
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), payload)
        response = self.client.get(url, HTTP_RANGE="bytes=0-3")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF")

    def test_skill_candidate_publication_uses_local_backend(self):
        user = User.objects.create_user(username="local-reviewer")
        archive = skill_zip({"demo/SKILL.md": "---\nname: local-demo\ndescription: Local test skill\n---\n# Demo"})
        candidate, created = create_uploaded_candidate(archive, user)
        self.assertTrue(created)
        candidate.description = "Local skill description."
        candidate.purpose = SkillPurpose.objects.get(slug="literature-read")
        candidate.save()
        candidate_path = candidate.archive_remote_path
        skill = publish_candidate(candidate, user)
        release = skill.releases.get()
        self.assertEqual(release.storage_backend, "local")
        self.assertTrue(b"".join(open_skill_stream(release).iter_chunks()).startswith(b"PK"))
        self.assertFalse(get_nas_skill_candidate_storage().exists(candidate_path))
        self.assertNotEqual(get_nas_skill_storage().root, self.storage.root)
