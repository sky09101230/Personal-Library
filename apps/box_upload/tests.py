from io import BytesIO
from unittest.mock import MagicMock, patch
import hashlib
import json

from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase

from .services import (
    LiteratureStorageError,
    NjuBoxUploadError,
    delete_from_nju_box,
    ensure_nju_box_directory,
    stream_from_nju_box,
    upload_to_nju_box,
)
from .storage import NAS_WEBDAV, StoredLiteratureObject
from .metadata import MetadataResolutionError, extract_pdf_evidence, parse_bibtex_metadata, resolve_pdf_metadata
from .models import CanonicalDocument, ExternalReference, UploadedDocument
from .zotero import import_zotero_library


class UploadPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="Strong-pass-1234")
        self.client.force_login(self.user)

    def test_upload_page_loads(self):
        response = self.client.get("/upload/")
        self.assertContains(response, "PLAB Literature")
        self.assertContains(response, 'multiple')
        self.assertContains(response, "window.alert(result.message)")
        self.assertContains(response, "progress.classList.remove('error')")

    @patch.dict("os.environ", {
        "NJU_BOX_API_TOKEN": "env-token",
        "NJU_BOX_LIBRARY_PASSWORD": "env-password",
    }, clear=False)
    def test_configured_credentials_are_not_shown(self):
        response = self.client.get("/upload/")
        self.assertNotContains(response, "NJU Box Web API Token")
        self.assertNotContains(response, "PLAB Literature 加密密码")

    @patch("apps.box_upload.views.store_literature", side_effect=[
        StoredLiteratureObject(NAS_WEBDAV, "/public/PLAB_KnowledgeBase/Literature/one.pdf"),
        StoredLiteratureObject(NAS_WEBDAV, "/public/PLAB_KnowledgeBase/Literature/two.pdf"),
    ])
    def test_post_uploads_all_selected_files(self, upload_file):
        response = self.client.post("/upload/", data={
            "files": [
                SimpleUploadedFile("one.pdf", b"one"),
                SimpleUploadedFile("two.pdf", b"two"),
            ],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(upload_file.call_count, 2)
        self.assertEqual(UploadedDocument.objects.filter(storage_backend=NAS_WEBDAV).count(), 2)
        self.assertFalse(CanonicalDocument.objects.exclude(index_status=CanonicalDocument.IndexStatus.PUBLISHED).exists())

    @patch(
        "apps.box_upload.views.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/public/PLAB_KnowledgeBase/Literature/progress.pdf"),
    )
    def test_ajax_upload_returns_progress_result(self, upload_file):
        response = self.client.post(
            "/upload/",
            data={"files": [SimpleUploadedFile("progress.pdf", b"pdf")]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    @patch("apps.box_upload.views.store_literature")
    @patch("apps.box_upload.views.fetch_doi_bibtex", side_effect=[
        "@article{one, title={One}, doi={10.1000/one}}",
        MetadataResolutionError("DOI BibTeX lookup failed."),
    ])
    @patch("apps.box_upload.views.extract_pdf_evidence", side_effect=[
        {"doi": "10.1000/one"},
        {"doi": "10.1000/two"},
    ])
    def test_bibtex_preflight_failure_stops_batch_before_storage(self, extract_evidence, fetch_bibtex, store):
        response = self.client.post(
            "/upload/",
            data={"files": [
                SimpleUploadedFile("one.pdf", b"one"),
                SimpleUploadedFile("two.pdf", b"two"),
            ]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "doi_bibtex_preflight_failed")
        self.assertIn("已停止上传", response.json()["message"])
        self.assertEqual(extract_evidence.call_count, 2)
        self.assertEqual(fetch_bibtex.call_count, 2)
        store.assert_not_called()
        self.assertEqual(UploadedDocument.objects.count(), 0)

    @patch("apps.box_upload.views.resolve_pdf_metadata_safely")
    @patch("apps.box_upload.views.store_literature", return_value=StoredLiteratureObject(
        NAS_WEBDAV,
        "/public/PLAB_KnowledgeBase/Literature/doi.pdf",
    ))
    @patch("apps.box_upload.views.fetch_doi_bibtex", return_value="@article{doi, title={DOI}, doi={10.1000/doi}}")
    @patch("apps.box_upload.views.extract_pdf_evidence", return_value={"doi": "10.1000/doi"})
    def test_successful_bibtex_preflight_is_reused(self, extract_evidence, fetch_bibtex, store, resolve_metadata):
        response = self.client.post(
            "/upload/",
            data={"files": [SimpleUploadedFile("doi.pdf", b"doi")]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        store.assert_called_once()
        fetch_bibtex.assert_called_once_with("10.1000/doi")
        bibtex_fetcher = resolve_metadata.call_args.kwargs["bibtex_fetcher"]
        self.assertEqual(bibtex_fetcher("10.1000/doi"), "@article{doi, title={DOI}, doi={10.1000/doi}}")

    @patch("apps.box_upload.views.fetch_doi_bibtex")
    @patch("apps.box_upload.views.extract_pdf_evidence", return_value={"doi": None})
    @patch("apps.box_upload.views.store_literature", return_value=StoredLiteratureObject(
        NAS_WEBDAV,
        "/public/PLAB_KnowledgeBase/Literature/no-doi.pdf",
    ))
    def test_pdf_without_doi_skips_bibtex_preflight(self, store, extract_evidence, fetch_bibtex):
        response = self.client.post(
            "/upload/",
            data={"files": [SimpleUploadedFile("no-doi.pdf", b"no doi")]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        store.assert_called_once()
        fetch_bibtex.assert_not_called()

    def test_browser_upload_rejects_non_pdf_files(self):
        response = self.client.post(
            "/upload/",
            data={"files": [SimpleUploadedFile("notes.txt", b"not a pdf")]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("PDF", response.json()["message"])

    @patch("apps.box_upload.views.store_literature", side_effect=[
        StoredLiteratureObject(NAS_WEBDAV, "/public/PLAB_KnowledgeBase/Literature/duplicate-1.pdf"),
        StoredLiteratureObject(NAS_WEBDAV, "/public/PLAB_KnowledgeBase/Literature/duplicate-2.pdf"),
    ])
    def test_same_content_reuses_canonical_document(self, upload_file):
        response = self.client.post("/upload/", data={
            "files": [
                SimpleUploadedFile("first.pdf", b"same-content"),
                SimpleUploadedFile("second.pdf", b"same-content"),
            ],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CanonicalDocument.objects.count(), 1)
        self.assertEqual(UploadedDocument.objects.count(), 2)
        self.assertEqual(CanonicalDocument.objects.get().index_status, CanonicalDocument.IndexStatus.PUBLISHED)
        self.assertEqual(
            UploadedDocument.objects.filter(duplicate_type=UploadedDocument.DuplicateType.EXACT).count(),
            1,
        )

    @patch(
        "apps.box_upload.views.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/public/PLAB_KnowledgeBase/Literature/existing.pdf"),
    )
    def test_duplicate_upload_publishes_existing_canonical(self, store):
        content = b"existing-content"
        canonical = CanonicalDocument.objects.create(sha256=hashlib.sha256(content).hexdigest())

        response = self.client.post(
            "/upload/",
            data={"files": [SimpleUploadedFile("existing.pdf", content)]},
        )
        canonical.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(canonical.index_status, CanonicalDocument.IndexStatus.PUBLISHED)

    def test_home_shows_workspace_entries_without_upload_form(self):
        response = self.client.get("/")

        self.assertContains(response, "功能区")
        self.assertContains(response, 'href="/library/"')
        self.assertContains(response, 'href="/upload/"')
        self.assertContains(response, 'href="/uploads/"')
        self.assertContains(response, 'href="/skills/"')
        self.assertNotContains(response, "进入管理后台")
        self.assertNotContains(response, 'type="file"')

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.assertContains(self.client.get("/"), "进入管理后台")

    def test_upload_history_only_shows_current_user_records(self):
        canonical = CanonicalDocument.objects.create(sha256="a" * 64)
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="mine.pdf",
            remote_path="/mine.pdf",
            sha256="a" * 64,
            size=1,
        )
        other_user = User.objects.create_user(username="other", password="Strong-pass-1234")
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=other_user,
            original_name="other.pdf",
            remote_path="/other.pdf",
            sha256="a" * 64,
            size=1,
            duplicate_type=UploadedDocument.DuplicateType.EXACT,
        )

        response = self.client.get("/uploads/")

        self.assertTemplateUsed(response, "box_upload/library.html")
        self.assertContains(response, "我的上传")
        self.assertContains(response, "mine.pdf")
        self.assertNotContains(response, "other.pdf")
        self.assertContains(response, '<div class="file-meta">上传者：member</div>', html=True)
        self.assertNotContains(response, '<div class="file-meta">mine.pdf · 上传者：member</div>', html=True)
        self.assertContains(response, f'/uploads/{UploadedDocument.objects.get(original_name="mine.pdf").pk}/delete/')

    def test_library_is_paginated(self):
        for index in range(21):
            digest = f"{index:064x}"
            canonical = CanonicalDocument.objects.create(sha256=digest)
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=self.user,
                original_name=f"paper-{index}.pdf",
                remote_path=f"/paper-{index}.pdf",
                sha256=digest,
                size=1,
            )

        first_page = self.client.get("/library/")
        second_page = self.client.get("/library/?page=2")

        self.assertEqual(len(first_page.context["page"].object_list), 20)
        self.assertEqual(len(second_page.context["page"].object_list), 1)

    def test_library_searches_document_name_and_preserves_query_for_pagination(self):
        for index in range(21):
            digest = f"{index:064x}"
            canonical = CanonicalDocument.objects.create(
                sha256=digest,
                journal="Optics Journal",
                publication_year=2026,
            )
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=self.user,
                original_name=f"optical-paper-{index}.pdf",
                remote_path=f"/optical-paper-{index}.pdf",
                sha256=digest,
                size=1,
            )

        response = self.client.get(
            f"/library/?q=optical-paper&journal=Optics+Journal&year=2026&uploader={self.user.pk}"
        )

        self.assertEqual(response.context["record_count"], 21)
        self.assertEqual(
            response.context["pagination_query"],
            f"q=optical-paper&journal=Optics+Journal&year=2026&uploader={self.user.pk}",
        )
        self.assertContains(response, "page=2")

    def test_library_filters_by_journal_year_and_uploader_and_shows_uploader(self):
        other_user = User.objects.create_user(username="other", password="Strong-pass-1234")
        cases = (
            ("target", "Target Journal", 2026, other_user),
            ("wrong-journal", "Other Journal", 2026, other_user),
            ("wrong-year", "Target Journal", 2025, other_user),
            ("wrong-uploader", "Target Journal", 2026, self.user),
        )
        for index, (title, journal, year, uploader) in enumerate(cases, start=1):
            digest = f"{index:064x}"
            canonical = CanonicalDocument.objects.create(
                sha256=digest,
                title=title,
                journal=journal,
                publication_year=year,
            )
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=uploader,
                original_name=f"{title}.pdf",
                remote_path=f"/{title}.pdf",
                sha256=digest,
                size=1,
            )

        response = self.client.get(
            f"/library/?journal=Target+Journal&year=2026&uploader={other_user.pk}"
        )

        self.assertEqual(response.context["record_count"], 1)
        self.assertContains(response, '<div class="file-name">target</div>', html=True)
        self.assertContains(response, "上传者：other")
        self.assertNotContains(response, "wrong-journal.pdf")
        self.assertNotContains(response, "wrong-year.pdf")
        self.assertNotContains(response, "wrong-uploader.pdf")

    @patch("apps.box_upload.views.delete_literature")
    def test_user_can_delete_only_own_upload_with_post(self, delete_file):
        canonical = CanonicalDocument.objects.create(sha256="6" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="mine-to-delete.pdf",
            remote_path="/mine-to-delete.pdf",
            sha256="6" * 64,
            size=1,
        )

        self.assertEqual(self.client.get(f"/uploads/{document.pk}/delete/").status_code, 405)
        response = self.client.post(f"/uploads/{document.pk}/delete/")

        self.assertRedirects(response, "/uploads/")
        delete_file.assert_called_once()
        self.assertFalse(UploadedDocument.objects.filter(pk=document.pk).exists())
        self.assertFalse(CanonicalDocument.objects.filter(pk=canonical.pk).exists())

    @patch("apps.box_upload.views.delete_literature")
    def test_user_cannot_delete_another_users_upload(self, delete_file):
        other_user = User.objects.create_user(username="other", password="Strong-pass-1234")
        document = UploadedDocument.objects.create(
            canonical_document=CanonicalDocument.objects.create(sha256="8" * 64),
            uploader=other_user,
            original_name="not-mine.pdf",
            remote_path="/not-mine.pdf",
            sha256="8" * 64,
            size=1,
        )

        response = self.client.post(f"/uploads/{document.pk}/delete/")

        self.assertEqual(response.status_code, 404)
        delete_file.assert_not_called()
        self.assertTrue(UploadedDocument.objects.filter(pk=document.pk).exists())

    @patch("apps.box_upload.views.delete_literature", side_effect=LiteratureStorageError("offline"))
    def test_failed_user_delete_keeps_upload_record(self, delete_file):
        document = UploadedDocument.objects.create(
            canonical_document=CanonicalDocument.objects.create(sha256="a" * 64),
            uploader=self.user,
            original_name="keep-mine.pdf",
            remote_path="/keep-mine.pdf",
            sha256="a" * 64,
            size=1,
        )

        response = self.client.post(f"/uploads/{document.pk}/delete/", follow=True)

        self.assertContains(response, "存储文件和记录均已保留")
        self.assertTrue(UploadedDocument.objects.filter(pk=document.pk).exists())

    def test_library_shows_zotero_only_literature_without_pdf(self):
        CanonicalDocument.objects.create(
            title="Zotero-only paper",
            metadata_source="zotero",
            metadata_status=CanonicalDocument.MetadataStatus.NEEDS_REVIEW,
        )

        response = self.client.get("/library/")

        self.assertContains(response, "Zotero-only paper")
        self.assertContains(response, "无 PDF")

    def test_library_shows_complete_metadata_columns_and_values(self):
        canonical = CanonicalDocument.objects.create(
            sha256="7" * 64,
            title="Complete metadata paper",
            authors=[
                {"name": "Author One"},
                {"name": "Author Two"},
                {"name": "Author Three"},
                {"name": "Author Four", "orcid": "0000-0000-0000-0001"},
            ],
            abstract="Complete abstract text.",
            journal="Complete Journal",
            publication_year=2026,
            doi="10.1000/complete",
            identifiers={"doi": "10.1000/complete", "pmid": "123456"},
            user_tags=["user-tag"],
            source_tags=["source-tag"],
            ai_tags=["ai-tag"],
            metadata_source="crossref",
            metadata_status=CanonicalDocument.MetadataStatus.VERIFIED,
            metadata_confidence=1,
            metadata_evidence={"crossref": {"doi": "10.1000/complete"}},
        )
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="complete.pdf",
            remote_path="/complete.pdf",
            sha256="7" * 64,
            size=1024,
            content_type="application/pdf",
        )

        response = self.client.get("/library/")

        for heading in ("标题", "作者", "期刊与年份", "摘要", "状态", "操作"):
            self.assertContains(response, heading)
        for value in ("Complete metadata paper", "Author Four", "Complete abstract text.", "10.1000/complete", "Complete Journal", "2026", "在线打开", "下载"):
            self.assertContains(response, value)
        for removed in ("user-tag", "source-tag", "ai-tag", "/complete.pdf", "123456", "查看完整证据", "外部引用"):
            self.assertNotContains(response, removed)
        self.assertContains(response, "元数据需处理")
        self.assertContains(response, "不完整、待复核或冲突")
        self.assertContains(response, "Agent 可检索")
        self.assertContains(response, "查看并处理")
        self.assertContains(response, "PDF 上传成功即发布")
        self.assertContains(response, "PDF 上传成功后会立即向 Agent 发布")
        html = response.content.decode()
        self.assertLess(html.index(">摘要</th>"), html.index(">状态</th>"))
        self.assertLess(html.index(">状态</th>"), html.index(">操作</th>"))

    def test_library_workflow_filters_and_staff_action_link(self):
        needs_review = CanonicalDocument.objects.create(
            title="Needs metadata work",
            metadata_status=CanonicalDocument.MetadataStatus.NEEDS_REVIEW,
        )
        CanonicalDocument.objects.create(
            title="Published record",
            metadata_status=CanonicalDocument.MetadataStatus.VERIFIED,
            index_status=CanonicalDocument.IndexStatus.PUBLISHED,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        review_response = self.client.get("/library/?workflow=review")
        unpublished_response = self.client.get("/library/?workflow=unpublished")

        self.assertContains(review_response, "Needs metadata work")
        self.assertNotContains(review_response, "Published record")
        self.assertContains(unpublished_response, "Needs metadata work")
        self.assertNotContains(unpublished_response, "Published record")
        self.assertContains(review_response, "编辑文献")
        self.assertContains(
            review_response,
            f"/admin/box_upload/canonicaldocument/{needs_review.pk}/change/",
        )

    @patch("apps.box_upload.views.import_zotero_library", return_value={
        "created": 2,
        "reused": 1,
        "skipped": 3,
        "pdf_imported": 1,
        "pdf_reused": 0,
        "pdf_skipped": 2,
        "pdf_failed": 0,
    })
    def test_zotero_import_uses_request_scoped_credentials(self, import_library):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.post("/zotero/import/", data={
            "library_type": "users",
            "library_id": "123",
            "collection_key": "ABC",
            "api_key": "secret-key",
        })

        self.assertRedirects(response, "/library/")
        import_library.assert_called_once_with(
            "users", "123", "secret-key", collection_key="ABC", uploader=self.user
        )

    def test_external_reference_admin_delete_removes_orphan_canonical(self):
        canonical = CanonicalDocument.objects.create(title="Zotero orphan", metadata_source="zotero")
        reference = ExternalReference.objects.create(
            canonical_document=canonical,
            provider=ExternalReference.Provider.ZOTERO,
            library_id="123",
            external_item_id="ITEM123",
        )

        admin.site._registry[ExternalReference].delete_model(MagicMock(), reference)

        self.assertFalse(CanonicalDocument.objects.filter(pk=canonical.pk).exists())

    def test_external_reference_admin_bulk_delete_keeps_canonical_with_pdf(self):
        orphan = CanonicalDocument.objects.create(title="Zotero orphan", metadata_source="zotero")
        attached = CanonicalDocument.objects.create(title="Attached", sha256="9" * 64)
        ExternalReference.objects.create(
            canonical_document=orphan,
            provider=ExternalReference.Provider.ZOTERO,
            library_id="123",
            external_item_id="ORPHAN",
        )
        ExternalReference.objects.create(
            canonical_document=attached,
            provider=ExternalReference.Provider.ZOTERO,
            library_id="123",
            external_item_id="ATTACHED",
        )
        UploadedDocument.objects.create(
            canonical_document=attached,
            uploader=self.user,
            original_name="attached.pdf",
            remote_path="/attached.pdf",
            sha256="9" * 64,
            size=1,
        )

        admin.site._registry[ExternalReference].delete_queryset(
            MagicMock(), ExternalReference.objects.filter(library_id="123")
        )

        self.assertFalse(CanonicalDocument.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(CanonicalDocument.objects.filter(pk=attached.pk).exists())

    @patch("apps.box_upload.views.import_zotero_library")
    def test_zotero_import_is_upgrade_only_for_members(self, import_library):
        page = self.client.get("/zotero/import/")
        post = self.client.post("/zotero/import/", data={
            "library_type": "users",
            "library_id": "123",
            "api_key": "secret-key",
        })

        self.assertContains(page, "正在测试升级当中")
        self.assertNotContains(page, "zotero-import-form")
        self.assertEqual(post.status_code, 403)
        import_library.assert_not_called()

    @patch("apps.box_upload.views.iter_zotero_import_library", return_value=iter((
        {"progress": 5, "message": "正在连接 Zotero"},
        {"progress": 100, "message": "导入完成", "result": {"created": 1, "reused": 0, "skipped": 0}, "done": True},
    )))
    def test_staff_zotero_import_streams_progress(self, import_library):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.post("/zotero/import/", data={
            "library_type": "users",
            "library_id": "123",
            "api_key": "secret-key",
        }, HTTP_ACCEPT="application/x-ndjson")

        events = [json.loads(line) for line in b"".join(response.streaming_content).decode().splitlines()]
        self.assertEqual([event["progress"] for event in events], [5, 100])
        self.assertTrue(events[-1]["done"])
        self.assertEqual(response["X-Accel-Buffering"], "no")
        import_library.assert_called_once_with(
            "users", "123", "secret-key", collection_key="", uploader=self.user
        )

    @patch("apps.box_upload.views.open_literature_stream")
    def test_download_is_proxied_as_attachment(self, open_stream):
        canonical = CanonicalDocument.objects.create(sha256="b" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="paper.pdf",
            remote_path="/paper.pdf",
            sha256="b" * 64,
            size=1,
        )

        upstream = MagicMock(status=200)
        upstream.iter_chunks.return_value = iter((b"pdf",))
        upstream.get_header.return_value = None
        open_stream.return_value = upstream

        response = self.client.get(f"/library/download/{document.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"pdf")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        open_stream.assert_called_once_with(document, byte_range=None)

    @patch("apps.box_upload.views.open_literature_stream")
    def test_inline_pdf_forwards_range_and_security_headers(self, open_stream):
        canonical = CanonicalDocument.objects.create(sha256="1" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="测试 paper.pdf",
            remote_path="/测试 paper.pdf",
            sha256="1" * 64,
            size=8,
        )
        upstream = MagicMock()
        upstream.status = 206
        upstream.iter_chunks.return_value = iter((b"%PDF", b"-1.7"))
        upstream.get_header.side_effect = {
            "Accept-Ranges": "bytes",
            "Content-Length": "8",
            "Content-Range": "bytes 0-7/100",
            "ETag": '"pdf-etag"',
            "Last-Modified": None,
        }.get
        open_stream.return_value = upstream

        response = self.client.get(f"/library/view/{document.pk}/", HTTP_RANGE="bytes=0-7")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.7")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        self.assertEqual(response["Content-Range"], "bytes 0-7/100")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        open_stream.assert_called_once_with(document, byte_range="bytes=0-7")

    @patch("apps.box_upload.views.open_literature_stream")
    def test_inline_pdf_rejects_invalid_range_before_box_request(self, open_stream):
        document = UploadedDocument.objects.create(
            canonical_document=CanonicalDocument.objects.create(sha256="2" * 64),
            uploader=self.user,
            original_name="paper.pdf",
            remote_path="/paper.pdf",
            sha256="2" * 64,
            size=1,
        )

        response = self.client.get(f"/library/view/{document.pk}/", HTTP_RANGE="bytes=0-1,4-5")

        self.assertEqual(response.status_code, 416)
        open_stream.assert_not_called()

    @patch("apps.box_upload.views.open_literature_stream", side_effect=LiteratureStorageError("secret upstream URL"))
    def test_inline_pdf_returns_controlled_error(self, open_stream):
        document = UploadedDocument.objects.create(
            canonical_document=CanonicalDocument.objects.create(sha256="3" * 64),
            uploader=self.user,
            original_name="paper.pdf",
            remote_path="/paper.pdf",
            sha256="3" * 64,
            size=1,
        )

        response = self.client.get(f"/library/view/{document.pk}/")

        self.assertEqual(response.status_code, 502)
        self.assertNotContains(response, "secret upstream URL", status_code=502)

    @patch("apps.box_upload.views.open_literature_stream")
    def test_inline_pdf_requires_login_before_box_request(self, open_stream):
        document = UploadedDocument.objects.create(
            canonical_document=CanonicalDocument.objects.create(sha256="4" * 64),
            uploader=self.user,
            original_name="paper.pdf",
            remote_path="/paper.pdf",
            sha256="4" * 64,
            size=1,
        )
        self.client.logout()

        response = self.client.get(f"/library/view/{document.pk}/")

        self.assertRedirects(response, f"/accounts/login/?next=/library/view/{document.pk}/")
        open_stream.assert_not_called()

    def test_online_open_links_appear_on_literature_surfaces(self):
        document = UploadedDocument.objects.create(
            canonical_document=CanonicalDocument.objects.create(title="Previewable paper", sha256="5" * 64),
            uploader=self.user,
            original_name="preview.pdf",
            remote_path="/preview.pdf",
            sha256="5" * 64,
            size=1,
        )

        for path in ("/", "/library/", "/uploads/"):
            response = self.client.get(path)
            self.assertContains(response, f'/library/view/{document.pk}/')
            self.assertContains(response, "在线打开")

    @patch("apps.box_upload.services.get_download_link", return_value="https://box.nju.edu.cn/seafhttp/files/token/paper.pdf?x=1")
    @patch("apps.box_upload.services.http.client.HTTPSConnection")
    def test_stream_from_nju_box_forwards_range_and_closes_connection(self, connection_class, get_link):
        connection = connection_class.return_value
        upstream_response = MagicMock()
        upstream_response.status = 206
        upstream_response.getheaders.return_value = [
            ("Content-Length", "8"),
            ("Content-Range", "bytes 0-7/100"),
        ]
        upstream_response.read.side_effect = [b"%PDF-1.7", b""]
        connection.getresponse.return_value = upstream_response

        stream = stream_from_nju_box("/paper.pdf", byte_range="bytes=0-7")

        self.assertEqual(b"".join(stream.iter_chunks()), b"%PDF-1.7")
        connection.request.assert_called_once_with(
            "GET",
            "/seafhttp/files/token/paper.pdf?x=1",
            headers={"Accept": "application/pdf", "Range": "bytes=0-7"},
        )
        self.assertEqual(stream.status, 206)
        self.assertEqual(stream.get_header("Content-Range"), "bytes 0-7/100")
        upstream_response.close.assert_called_once_with()
        connection.close.assert_called_once_with()

    @patch("apps.box_upload.admin.delete_literature")
    def test_staff_user_can_delete_upload_record_from_admin(self, delete_file):
        canonical = CanonicalDocument.objects.create(sha256="c" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="remove-metadata.pdf",
            remote_path="/remove-metadata.pdf",
            sha256="c" * 64,
            size=1,
        )
        document_pk = document.pk
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.client.post(
            reverse("admin:box_upload_uploadeddocument_delete", args=[document.pk]),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 302)
        delete_file.assert_called_once()
        self.assertEqual(delete_file.call_args.args[0].remote_path, "/remove-metadata.pdf")
        self.assertFalse(UploadedDocument.objects.filter(pk=document_pk).exists())

    def test_uploaded_document_admin_shows_id_and_only_safe_bulk_delete(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.client.get(reverse("admin:box_upload_uploadeddocument_changelist"))

        model_admin = admin.site._registry[UploadedDocument]
        self.assertEqual(model_admin.list_display[:2], ("id", "original_name"))
        self.assertEqual(model_admin.list_display_links, ("id", "original_name"))
        actions = model_admin.get_actions(response.wsgi_request)
        self.assertIn("delete_from_box", actions)
        self.assertNotIn("delete_selected", actions)

    @patch("apps.box_upload.admin.delete_literature")
    def test_staff_admin_action_deletes_box_file_before_record(self, delete_file):
        canonical = CanonicalDocument.objects.create(sha256="d" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="remove-from-box.pdf",
            remote_path="/remove-from-box.pdf",
            sha256="d" * 64,
            size=1,
        )
        document_pk = document.pk
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.client.post(
            reverse("admin:box_upload_uploadeddocument_changelist"),
            {"action": "delete_from_box", "confirm": "yes", "_selected_action": [document.pk]},
        )

        self.assertEqual(response.status_code, 302)
        delete_file.assert_called_once()
        self.assertEqual(delete_file.call_args.args[0].remote_path, "/remove-from-box.pdf")
        self.assertFalse(UploadedDocument.objects.filter(pk=document_pk).exists())
        self.assertFalse(CanonicalDocument.objects.filter(pk=canonical.pk).exists())

    def test_staff_admin_action_requires_confirmation(self):
        canonical = CanonicalDocument.objects.create(sha256="f" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="confirm-delete.pdf",
            remote_path="/confirm-delete.pdf",
            sha256="f" * 64,
            size=1,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.client.post(
            reverse("admin:box_upload_uploadeddocument_changelist"),
            {"action": "delete_from_box", "_selected_action": [document.pk]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "确认删除文献文件")
        self.assertTrue(UploadedDocument.objects.filter(pk=document.pk).exists())

    @patch("apps.box_upload.admin.delete_literature", side_effect=LiteratureStorageError("offline"))
    def test_staff_admin_action_keeps_record_when_box_delete_fails(self, delete_file):
        canonical = CanonicalDocument.objects.create(sha256="e" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="keep-on-failure.pdf",
            remote_path="/keep-on-failure.pdf",
            sha256="e" * 64,
            size=1,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        self.client.post(
            reverse("admin:box_upload_uploadeddocument_changelist"),
            {"action": "delete_from_box", "confirm": "yes", "_selected_action": [document.pk]},
        )

        delete_file.assert_called_once()
        self.assertEqual(delete_file.call_args.args[0].remote_path, "/keep-on-failure.pdf")
        self.assertTrue(UploadedDocument.objects.filter(pk=document.pk).exists())

    @patch("apps.box_upload.services._upload_file")
    @patch("apps.box_upload.services._request")
    @patch.dict("os.environ", {
        "NJU_BOX_API_URL": "https://box.nju.edu.cn",
        "NJU_BOX_REPOSITORY_ID": "e2304051-022d-43bd-b3f9-d4d34051a040",
        "NJU_BOX_TARGET_DIRECTORY": "/",
    }, clear=False)
    def test_upload_unlocks_repository_before_upload(self, request, upload_file):
        request.side_effect = [
            type("Response", (), {"status": 200, "body": b'"success"'})(),
            type("Response", (), {"status": 200, "body": b'"https://box.nju.edu.cn/upload-api/token"'})(),
        ]
        upload_file.return_value = type(
            "Response",
            (),
            {"status": 200, "body": b'[{"name":"test file.pdf","id":"file-id","size":3}]'},
        )()
        uploaded = SimpleUploadedFile("test file.pdf", b"pdf", content_type="application/pdf")

        remote_path = upload_to_nju_box(uploaded, "api-token", "library-password")

        self.assertEqual(remote_path, "/test file.pdf")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(upload_file.call_count, 1)
        self.assertIn("ret-json=1", upload_file.call_args.args[0])

    @patch("apps.box_upload.services._upload_file")
    @patch("apps.box_upload.services._request")
    @patch.dict("os.environ", {
        "NJU_BOX_API_URL": "https://box.nju.edu.cn",
        "NJU_BOX_REPOSITORY_ID": "repo-id",
        "NJU_BOX_TARGET_DIRECTORY": "/",
    }, clear=False)
    def test_upload_uses_server_returned_name_after_collision(self, request, upload_file):
        request.side_effect = [
            type("Response", (), {"status": 200, "body": b'"success"'})(),
            type("Response", (), {"status": 200, "body": b'"https://box.nju.edu.cn/upload-api/token?existing=1"'})(),
        ]
        upload_file.return_value = type(
            "Response",
            (),
            {"status": 200, "body": b'[{"name":"paper (1).pdf","id":"file-id","size":3}]'},
        )()

        remote_path = upload_to_nju_box(
            SimpleUploadedFile("paper.pdf", b"pdf"),
            "api-token",
            "library-password",
        )

        self.assertEqual(remote_path, "/paper (1).pdf")
        self.assertIn("existing=1", upload_file.call_args.args[0])
        self.assertIn("ret-json=1", upload_file.call_args.args[0])

    @patch("apps.box_upload.services._upload_file")
    @patch("apps.box_upload.services._request")
    @patch.dict("os.environ", {
        "NJU_BOX_API_URL": "https://box.nju.edu.cn",
        "NJU_BOX_REPOSITORY_ID": "e2304051-022d-43bd-b3f9-d4d34051a040",
        "NJU_BOX_TARGET_DIRECTORY": "/",
        "NJU_BOX_API_TOKEN": "env-token",
        "NJU_BOX_LIBRARY_PASSWORD": "env-password",
    }, clear=False)
    def test_upload_uses_env_credentials_when_form_is_empty(self, request, upload_file):
        request.side_effect = [
            type("Response", (), {"status": 200, "body": b'"success"'})(),
            type("Response", (), {"status": 200, "body": b'"https://box.nju.edu.cn/upload-api/token"'})(),
        ]
        upload_file.return_value = type(
            "Response",
            (),
            {"status": 200, "body": b'[{"name":"env.pdf","id":"file-id","size":3}]'},
        )()

        upload_to_nju_box(SimpleUploadedFile("env.pdf", b"pdf"))

        self.assertIn("Token env-token", request.call_args_list[0].args[2]["Authorization"])
        self.assertIn(b"password=env-password", request.call_args_list[0].args[3])

    @patch.dict("os.environ", {}, clear=True)
    def test_upload_requires_repository_configuration(self):
        with self.assertRaises(NjuBoxUploadError):
            upload_to_nju_box(SimpleUploadedFile("test.pdf", b"pdf"), "api-token", "library-password")

    @patch("apps.box_upload.services._request")
    @patch.dict("os.environ", {
        "NJU_BOX_API_URL": "https://box.nju.edu.cn",
        "NJU_BOX_REPOSITORY_ID": "repo-id",
    }, clear=False)
    def test_delete_unlocks_then_deletes_encoded_path(self, request):
        request.side_effect = [
            type("Response", (), {"status": 200, "body": b"ok"})(),
            type("Response", (), {"status": 200, "body": b"{}"})(),
            type("Response", (), {"status": 204, "body": b""})(),
        ]

        delete_from_nju_box("/folder/a paper.pdf", "api-token", "library-password")

        self.assertEqual(request.call_count, 3)
        delete_call = request.call_args_list[2]
        self.assertEqual(delete_call.args[1], "DELETE")
        self.assertIn("p=%2Ffolder%2Fa+paper.pdf", delete_call.args[0])

    @patch("apps.box_upload.services._request")
    @patch.dict("os.environ", {
        "NJU_BOX_API_URL": "https://box.nju.edu.cn",
        "NJU_BOX_REPOSITORY_ID": "repo-id",
    }, clear=False)
    def test_delete_continues_when_repository_is_already_unlocked(self, request):
        request.side_effect = [
            type("Response", (), {"status": 409, "body": b"already unlocked"})(),
            type("Response", (), {"status": 200, "body": b"{}"})(),
            type("Response", (), {"status": 200, "body": b'"success"'})(),
        ]

        delete_from_nju_box("/paper.pdf", "api-token", "library-password")
        self.assertEqual(request.call_args_list[2].args[1], "DELETE")

    @patch("apps.box_upload.services._request")
    @patch.dict("os.environ", {"NJU_BOX_API_URL": "https://box.nju.edu.cn", "NJU_BOX_REPOSITORY_ID": "repo-id"}, clear=False)
    def test_ensure_directory_creates_missing_path(self, request):
        request.side_effect = [
            type("Response", (), {"status": 200, "body": b"ok"})(),
            type("Response", (), {"status": 404, "body": b""})(),
            type("Response", (), {"status": 201, "body": b'"success"'})(),
        ]

        ensure_nju_box_directory("/PLAB Skills/", "api-token", "library-password")
        self.assertEqual(request.call_args_list[2].args[1], "POST")


class MetadataResolutionTests(TestCase):
    @patch("apps.box_upload.metadata.PdfReader")
    def test_doi_scan_reads_first_two_and_last_two_pages(self, pdf_reader):
        class Page:
            def __init__(self, text):
                self.text = text
                self.calls = 0

            def extract_text(self):
                self.calls += 1
                return self.text

        pages = [
            Page("first"),
            Page("second"),
            Page("middle three"),
            Page("middle four"),
            Page("doi 10.1126/science.aat8084"),
            Page("last"),
        ]
        pdf_reader.return_value = type("Reader", (), {"metadata": {}, "pages": pages})()
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\nmock content")

        evidence = extract_pdf_evidence(uploaded)

        self.assertEqual(evidence["doi"], "10.1126/science.aat8084")
        self.assertEqual(evidence["pages_scanned"], 4)
        self.assertEqual(evidence["page_numbers_scanned"], [1, 2, 5, 6])
        self.assertEqual([page.calls for page in pages], [1, 1, 0, 0, 1, 1])
        self.assertEqual(evidence["doi_source"], {"source": "pdf_page", "page": 5})

    @patch("apps.box_upload.metadata.PdfReader")
    def test_title_page_doi_wins_over_later_page_and_raw_bytes(self, pdf_reader):
        class Page:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        pages = [
            Page("Article DOI 10.1000/TITLE.1"),
            Page("second"),
            Page("middle"),
            Page("Reference DOI 10.1000/REFERENCE.2"),
        ]
        pdf_reader.return_value = type("Reader", (), {"metadata": {}, "pages": pages})()
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n10.1000/RAW.3")

        evidence = extract_pdf_evidence(uploaded)

        self.assertEqual(evidence["doi"], "10.1000/title.1")
        self.assertEqual(evidence["doi_source"], {"source": "pdf_page", "page": 1})
        self.assertEqual(
            [candidate["doi"] for candidate in evidence["doi_candidates"]],
            ["10.1000/title.1", "10.1000/reference.2", "10.1000/raw.3"],
        )

    def test_bibtex_is_primary_and_crossref_fills_missing_abstract(self):
        canonical = CanonicalDocument.objects.create(sha256="9" * 64)
        uploaded = SimpleUploadedFile(
            "paper.pdf",
            b"%PDF-1.7\nhttps://doi.org/10.1000/TEST.1\n",
            content_type="application/pdf",
        )

        resolve_pdf_metadata(
            canonical,
            uploaded,
            bibtex_fetcher=lambda doi: """@article{primary,
                title={Evidence-based metadata},
                author={Lovelace, Ada},
                journal={Journal of Tests},
                year={2026},
                doi={10.1000/test.1},
                keywords={optics; metadata}
            }""",
            crossref_fetcher=lambda doi: {
                "DOI": "10.1000/test.1",
                "title": ["Evidence-based metadata"],
                "author": [{"given": "Grace", "family": "Hopper"}],
                "abstract": "<jats:p>Abstract deposited with Crossref.</jats:p>",
                "container-title": ["Different Journal Name"],
                "issued": {"date-parts": [[2025, 8, 7]]},
            },
        )

        canonical.refresh_from_db()
        self.assertEqual(canonical.metadata_status, CanonicalDocument.MetadataStatus.VERIFIED)
        self.assertEqual(canonical.metadata_source, "bibtex")
        self.assertEqual(canonical.doi, "10.1000/test.1")
        self.assertEqual(canonical.title, "Evidence-based metadata")
        self.assertEqual(canonical.authors, [{"name": "Ada Lovelace"}])
        self.assertEqual(canonical.journal, "Journal of Tests")
        self.assertEqual(canonical.publication_year, 2026)
        self.assertEqual(canonical.abstract, "Abstract deposited with Crossref.")
        self.assertEqual(canonical.source_tags, ["optics", "metadata"])
        self.assertEqual(canonical.metadata_evidence["pdf"]["doi"], "10.1000/test.1")
        self.assertEqual(canonical.metadata_evidence["bibtex"]["abstract_source"], "crossref")
        self.assertIn("Abstract deposited with Crossref.", canonical.metadata_evidence["bibtex"]["enriched"])

    def test_bibtex_parser_maps_core_fields(self):
        entry, metadata = parse_bibtex_metadata("""@inproceedings{paper,
            title={A {BibTeX} Test},
            author={Lovelace, Ada and Turing, Alan},
            booktitle={Proceedings of Tests},
            year={2024},
            doi={10.1000/PARSER.1},
            abstract={Original abstract.}
        }""", expected_doi="10.1000/parser.1")

        self.assertEqual(entry["ENTRYTYPE"], "inproceedings")
        self.assertEqual(metadata["title"], "A BibTeX Test")
        self.assertEqual(metadata["authors"], [{"name": "Ada Lovelace"}, {"name": "Alan Turing"}])
        self.assertEqual(metadata["journal"], "Proceedings of Tests")
        self.assertEqual(metadata["publication_year"], 2024)
        self.assertEqual(metadata["abstract"], "Original abstract.")

    def test_bibtex_parser_accepts_doi_formatter_sept_month_alias(self):
        entry, metadata = parse_bibtex_metadata(
            "@article{paper, title={September paper}, author={Doe, Jane}, year={2024}, month=Sept, doi={10.1000/SEPT.1}}",
            expected_doi="10.1000/sept.1",
        )

        self.assertEqual(entry["month"], "September")
        self.assertEqual(metadata["title"], "September paper")

    def test_bibtex_doi_conflict_is_not_verified(self):
        canonical = CanonicalDocument.objects.create(sha256="7" * 64)
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n10.1000/PDF.1")

        resolve_pdf_metadata(
            canonical,
            uploaded,
            bibtex_fetcher=lambda doi: "@article{x, title={Wrong work}, author={Doe, Jane}, year={2024}, doi={10.1000/OTHER.2}}",
            crossref_fetcher=lambda doi: {"DOI": doi, "title": ["Expected work"]},
        )

        canonical.refresh_from_db()
        self.assertEqual(canonical.metadata_status, CanonicalDocument.MetadataStatus.CONFLICT)
        self.assertEqual(canonical.metadata_candidates["doi"][1]["source"], "bibtex")
        self.assertIn("10.1000/OTHER.2", canonical.metadata_evidence["bibtex"]["raw"])

    def test_crossref_only_fallback_remains_available(self):
        canonical = CanonicalDocument.objects.create(sha256="6" * 64)
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n10.1000/FALLBACK.1")

        def unavailable(_doi):
            raise MetadataResolutionError("DOI BibTeX lookup failed.")

        resolve_pdf_metadata(
            canonical,
            uploaded,
            bibtex_fetcher=unavailable,
            crossref_fetcher=lambda doi: {
                "DOI": doi,
                "title": ["Crossref fallback"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "container-title": ["Journal of Tests"],
                "issued": {"date-parts": [[2026, 8, 8]]},
            },
        )

        canonical.refresh_from_db()
        self.assertEqual(canonical.metadata_status, CanonicalDocument.MetadataStatus.VERIFIED)
        self.assertEqual(canonical.metadata_source, "crossref")
        self.assertEqual(canonical.metadata_evidence["provider_errors"]["bibtex"], "DOI BibTeX lookup failed.")

    def test_pdf_without_doi_is_incomplete_not_verified(self):
        canonical = CanonicalDocument.objects.create(sha256="8" * 64)
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\nno identifier")

        resolve_pdf_metadata(canonical, uploaded)

        canonical.refresh_from_db()
        self.assertEqual(canonical.metadata_status, CanonicalDocument.MetadataStatus.INCOMPLETE)
        self.assertEqual(canonical.metadata_source, "pdf")


class ZoteroImportTests(TestCase):
    def _request_page(self, url, api_key):
        self.assertEqual(api_key, "secret-key")
        return ([{
            "key": "ITEM123",
            "version": 37,
            "data": {
                "itemType": "journalArticle",
                "title": "Structured Zotero paper",
                "creators": [{"creatorType": "author", "firstName": "Grace", "lastName": "Hopper"}],
                "publicationTitle": "Computing Journal",
                "date": "2025-03-01",
                "DOI": "https://doi.org/10.1000/ZOTERO",
                "abstractNote": "Abstract from Zotero.",
                "tags": [{"tag": "source-tag"}],
            },
        }], {})

    def test_import_creates_canonical_literature_and_external_reference(self):
        result = import_zotero_library("users", "123", "secret-key", request_page=self._request_page)

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["reused"], 0)
        self.assertEqual(result["pdf_imported"], 0)
        literature = CanonicalDocument.objects.get()
        self.assertIsNone(literature.sha256)
        self.assertEqual(literature.doi, "10.1000/zotero")
        self.assertEqual(literature.metadata_status, CanonicalDocument.MetadataStatus.NEEDS_REVIEW)
        self.assertEqual(literature.source_tags, ["source-tag"])
        reference = ExternalReference.objects.get()
        self.assertEqual(reference.external_item_id, "ITEM123")
        self.assertEqual(reference.external_version, 37)

    def test_reimport_reuses_external_reference(self):
        import_zotero_library("users", "123", "secret-key", request_page=self._request_page)
        result = import_zotero_library("users", "123", "secret-key", request_page=self._request_page)

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["reused"], 1)
        self.assertEqual(CanonicalDocument.objects.count(), 1)
        self.assertEqual(ExternalReference.objects.count(), 1)

    def test_import_emits_monotonic_progress_and_current_action(self):
        from .zotero import iter_zotero_import_library

        events = list(iter_zotero_import_library(
            "users", "123", "secret-key", request_page=self._request_page
        ))

        self.assertEqual([event["progress"] for event in events], sorted(event["progress"] for event in events))
        self.assertIn("正在拉取 Zotero 第 1 页", events[1]["message"])
        self.assertIn("正在处理第 1/1 条文献", events[-2]["message"])
        self.assertTrue(events[-1]["done"])

    def test_imports_only_hosted_pdfs_and_isolates_one_failure(self):
        user = User.objects.create_user(username="zotero-admin", password="test-pass")
        valid_pdf = b"%PDF-1.7\ncontent"

        def request_page(url, api_key):
            self.assertEqual(api_key, "secret-key")
            if "/children" not in url:
                return self._request_page(url, api_key)
            if "start=100" in url:
                return ([
                    {"key": "BROKEN", "data": {
                        "itemType": "attachment", "linkMode": "imported_file",
                        "contentType": "application/pdf", "filename": "broken.pdf",
                    }},
                    {"key": "SAME", "data": {
                        "itemType": "attachment", "linkMode": "imported_file",
                        "contentType": "application/pdf", "filename": "same.pdf",
                    }},
                    {"key": "LOCAL", "data": {
                        "itemType": "attachment", "linkMode": "linked_file",
                        "contentType": "application/pdf", "filename": "local.pdf",
                    }},
                ], {})
            return ([
                {"key": "HOSTED", "data": {
                    "itemType": "attachment", "linkMode": "imported_file",
                    "contentType": "application/pdf", "filename": "hosted.pdf",
                }},
                {"key": "WEB", "data": {
                    "itemType": "attachment", "linkMode": "imported_url",
                    "contentType": "application/pdf", "filename": "web.pdf",
                }},
                {"key": "SNAPSHOT", "data": {
                    "itemType": "attachment", "linkMode": "imported_url",
                    "contentType": "text/html", "filename": "snapshot.html",
                }},
            ], {"Link": '<https://api.zotero.org/users/123/items/ITEM123/children?format=json&limit=100&start=100>; rel="next"'})

        def request_file(url, api_key):
            self.assertEqual(api_key, "secret-key")
            return BytesIO(b"not a pdf" if "/BROKEN/file" in url else valid_pdf)

        store_file = MagicMock(return_value=StoredLiteratureObject(NAS_WEBDAV, "/zotero/hosted.pdf"))
        result = import_zotero_library(
            "users",
            "123",
            "secret-key",
            uploader=user,
            request_page=request_page,
            request_file=request_file,
            store_file=store_file,
        )

        self.assertEqual(
            {key: result[key] for key in ("pdf_imported", "pdf_reused", "pdf_skipped", "pdf_failed")},
            {"pdf_imported": 1, "pdf_reused": 1, "pdf_skipped": 3, "pdf_failed": 1},
        )
        self.assertIn("broken.pdf", result["pdf_failures"][0])
        self.assertEqual(UploadedDocument.objects.count(), 1)
        self.assertEqual(UploadedDocument.objects.get().original_name, "hosted.pdf")
        self.assertEqual(store_file.call_count, 1)
        self.assertEqual(CanonicalDocument.objects.get().title, "Structured Zotero paper")

    def test_removes_stored_pdf_if_upload_row_creation_fails(self):
        from .zotero import _import_zotero_pdf

        user = User.objects.create_user(username="zotero-cleanup", password="test-pass")
        canonical = CanonicalDocument.objects.create(title="Cleanup")
        stored = StoredLiteratureObject(NAS_WEBDAV, "/zotero/orphan.pdf")
        storage = MagicMock()

        with (
            patch("apps.box_upload.zotero.UploadedDocument.objects.create", side_effect=RuntimeError("db failed")),
            patch("apps.box_upload.zotero.get_literature_storage", return_value=storage),
            self.assertRaises(RuntimeError),
        ):
            _import_zotero_pdf(
                canonical,
                user,
                "users",
                "123",
                "secret-key",
                {"item_key": "ATTACHMENT", "filename": "paper.pdf"},
                request_file=lambda _url, _key: BytesIO(b"%PDF-1.7\ncontent"),
                store_file=lambda _file: stored,
            )

        storage.delete.assert_called_once_with("/zotero/orphan.pdf")
