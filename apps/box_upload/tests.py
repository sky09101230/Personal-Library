from io import BytesIO
from threading import Barrier
from unittest import skip
from unittest.mock import MagicMock, patch
import hashlib
import json

from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib import admin
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .services import (
    LiteratureStorageError,
    NjuBoxUploadError,
    stream_from_nju_box,
)
from .storage import NAS_WEBDAV, StoredLiteratureObject
from .metadata import (
    MetadataResolutionError,
    extract_pdf_evidence,
    parse_bibtex_metadata,
    resolve_pdf_metadata,
    select_pdf_doi,
)
from .ingestion import prepare_pdf, save_pdf_upload
from .models import CanonicalDocument, ExternalReference, UploadedDocument, ZoteroConnection
from .zotero import ZoteroImportError, decrypt_zotero_api_key, encrypt_zotero_api_key, import_zotero_library


class UploadPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="Strong-pass-1234")
        self.client.force_login(self.user)

    def test_upload_page_loads(self):
        response = self.client.get("/upload/")
        self.assertContains(response, "PLAB Literature")
        self.assertContains(response, 'multiple')
        self.assertContains(response, "const MAX_CHANNELS = 4")
        self.assertContains(response, "本批 metadata 审核")

    def test_library_preserves_historical_supplementary_role(self):
        canonical = CanonicalDocument.objects.create(title="Existing paper", sha256="a" * 64)
        for name, digest, role in (
            ("primary.pdf", "a" * 64, UploadedDocument.FileRole.PRIMARY),
            ("supplement.pdf", "b" * 64, UploadedDocument.FileRole.SUPPLEMENTARY),
        ):
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=self.user,
                original_name=name,
                remote_path=f"/{name}",
                sha256=digest,
                size=1,
                file_role=role,
            )

        response = self.client.get("/library/")

        self.assertContains(response, "正文 PDF · 提交者：member")
        self.assertContains(response, "补充材料 · 提交者：member")

    @patch("apps.box_upload.ingestion.get_literature_storage")
    @patch("apps.box_upload.ingestion.UploadedDocument.objects.create", side_effect=RuntimeError("db failed"))
    def test_shared_ingestion_removes_stored_pdf_when_database_write_fails(
        self, create_upload, get_storage
    ):
        canonical = CanonicalDocument.objects.create()
        prepared = prepare_pdf(SimpleUploadedFile("cleanup.pdf", b"%PDF-1.7\ncleanup"))
        store = MagicMock(return_value=StoredLiteratureObject(NAS_WEBDAV, "/cleanup/web.pdf"))

        with self.assertRaises(RuntimeError):
            save_pdf_upload(canonical, self.user, prepared, store_file=store)

        store.assert_called_once()
        create_upload.assert_called_once()
        get_storage.return_value.delete.assert_called_once_with("/cleanup/web.pdf")
        self.assertFalse(UploadedDocument.objects.exists())

    @patch("apps.box_upload.ingestion.get_literature_storage")
    def test_shared_ingestion_cleans_up_concurrent_duplicate_doi_pdf(self, get_storage):
        owner = User.objects.create_user(username="owner", password="Strong-pass-1234")
        canonical = CanonicalDocument.objects.create(doi="10.1000/race")
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=owner,
            original_name="existing.pdf",
            remote_path="/existing.pdf",
            sha256="a" * 64,
            size=1,
        )
        prepared = prepare_pdf(SimpleUploadedFile("racing.pdf", b"%PDF-1.7\nrace"))
        store = MagicMock(return_value=StoredLiteratureObject(NAS_WEBDAV, "/cleanup/racing.pdf"))

        document = save_pdf_upload(
            canonical,
            self.user,
            prepared,
            store_file=store,
            reuse_existing_pdf=True,
        )

        self.assertIsNone(document)
        self.assertEqual(canonical.uploads.count(), 1)
        self.assertTrue(canonical.uploaders.filter(pk=self.user.pk).exists())
        get_storage.return_value.delete.assert_called_once_with("/cleanup/racing.pdf")

    def test_library_hides_historical_exact_duplicate_attachments(self):
        canonical = CanonicalDocument.objects.create(title="Duplicate attachment paper", sha256="d" * 64)
        for index in range(2):
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=self.user,
                original_name="duplicate.pdf",
                remote_path=f"/duplicate-{index}.pdf",
                sha256="d" * 64,
                size=1,
            )

        response = self.client.get("/library/")

        self.assertContains(response, "Duplicate attachment paper")
        self.assertContains(response, "正文 PDF · 提交者：member", count=1)

    def test_doi_is_unique_ignoring_case(self):
        CanonicalDocument.objects.create(doi="10.1000/CASE")

        with self.assertRaises(IntegrityError), transaction.atomic():
            CanonicalDocument.objects.create(doi="10.1000/case")

    @patch("apps.box_upload.upload_review.store_literature", return_value=StoredLiteratureObject(NAS_WEBDAV, "/paper.pdf"))
    @patch("apps.box_upload.upload_review.fetch_doi_bibtex")
    @patch("apps.box_upload.upload_review.extract_pdf_evidence")
    def test_upload_uses_title_matched_doi_before_storage(
        self, extract_evidence, fetch_bibtex, store
    ):
        extract_evidence.return_value = {
            "doi": "10.5281/zenodo.19590759",
            "title": "Holographic lasing with dielectric metasurfaces",
            "doi_candidates": [
                {"doi": "10.5281/zenodo.19590759", "source": "pdf_page", "page": 9},
                {"doi": "10.1126/sciadv.aea7345", "source": "pdf_page", "page": 9},
            ],
            "doi_source": {"source": "pdf_page", "page": 9},
        }
        records = {
            "10.5281/zenodo.19590759": "@misc{wrong, title={MATLAB code for genetic optimization of a holographic lasing metasurface}, author={Doe, Jane}, year={2026}, doi={10.5281/zenodo.19590759}}",
            "10.1126/sciadv.aea7345": "@article{right, title={Holographic lasing with dielectric metasurfaces}, author={Doe, Jane}, year={2026}, doi={10.1126/sciadv.aea7345}}",
        }
        fetch_bibtex.side_effect = records.__getitem__

        batch_id = self.client.post("/upload/batches/").json()["batch_id"]
        response = self.client.post(
            f"/upload/batches/{batch_id}/files/",
            data={"file": SimpleUploadedFile("paper.pdf", b"%PDF-1.7\nmock")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["metadata"]["doi"], "10.1126/sciadv.aea7345")
        self.assertFalse(CanonicalDocument.objects.exists())
        store.assert_called_once()

    def test_home_shows_workspace_entries_without_upload_form(self):
        response = self.client.get("/")

        self.assertContains(response, "功能区")
        self.assertContains(response, 'href="/library/"')
        self.assertContains(response, 'href="/upload/"')
        self.assertContains(response, 'href="/uploads/"')
        self.assertContains(response, 'href="/skills/"')
        self.assertContains(response, "我的文献")
        self.assertNotContains(response, "进入管理后台")
        self.assertNotContains(response, 'type="file"')

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.assertContains(self.client.get("/"), "进入管理后台")

    def test_home_explains_attachment_count_and_reuses_library_rows(self):
        canonical = CanonicalDocument.objects.create(
            title="One canonical paper",
            abstract="Summary visible only in Library",
            sha256="f" * 64,
        )
        for index in range(2):
            UploadedDocument.objects.create(
                canonical_document=canonical,
                uploader=self.user,
                original_name=f"attachment-{index}.pdf",
                remote_path=f"/attachment-{index}.pdf",
                sha256=f"{index + 1:064x}",
                size=1,
            )

        response = self.client.get("/")

        self.assertEqual(response.context["record_count"], 2)
        self.assertEqual(response.context["canonical_count"], 1)
        self.assertEqual(len(response.context["recent_literature"]), 1)
        self.assertContains(response, "每次上传或导入计一条")
        self.assertContains(response, "同一篇文献只计一次")
        self.assertContains(response, '<table class="literature-table">')
        self.assertContains(response, "One canonical paper", count=1)
        self.assertNotContains(response, "Summary visible only in Library")
        self.assertNotContains(self.client.get("/library/"), "Summary visible only in Library")

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
        self.assertContains(response, "我的文献")
        self.assertNotContains(response, "mine.pdf · 正文 PDF")
        self.assertNotContains(response, "other.pdf")
        self.assertContains(response, "文献操作")
        self.assertContains(response, "PDF 附件")
        self.assertContains(response, '<div class="file-meta">关联用户：member、other</div>', html=True)
        self.assertContains(response, "关系：你实际上传过 PDF")
        self.assertContains(response, "正文 PDF · 提交者：member")
        self.assertContains(response, "正文 PDF · 提交者：other")
        self.assertContains(response, f'/uploads/{UploadedDocument.objects.get(original_name="mine.pdf").pk}/delete/')
        self.assertNotContains(response, f'/uploads/{UploadedDocument.objects.get(original_name="other.pdf").pk}/delete/')

    def test_my_literature_explains_association_without_granting_attachment_actions(self):
        owner = User.objects.create_user(username="owner", password="Strong-pass-1234")
        canonical = CanonicalDocument.objects.create(doi="10.1000/linked", title="Linked paper")
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=owner,
            original_name="owner.pdf",
            remote_path="/owner.pdf",
            sha256="b" * 64,
            size=1,
        )
        canonical.uploaders.add(self.user)

        response = self.client.get("/uploads/")

        self.assertContains(response, "Linked paper")
        self.assertContains(response, "关系：通过 DOI 或 Zotero 关联，未重复保存 PDF")
        self.assertNotContains(response, "owner.pdf")
        self.assertContains(response, "正文 PDF · 提交者：owner")
        self.assertNotContains(response, f'/uploads/{document.pk}/delete/')
        self.assertNotContains(response, "生成 AI 建议")

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
        self.assertContains(response, "关联用户：other")
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
        canonical = CanonicalDocument.objects.create(sha256="8" * 64)
        document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=other_user,
            original_name="not-mine.pdf",
            remote_path="/not-mine.pdf",
            sha256="8" * 64,
            size=1,
        )
        canonical.uploaders.add(self.user)

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

        for heading in ("标题", "作者", "期刊与年份", "状态", "文献操作", "PDF 附件"):
            self.assertContains(response, heading)
        for value in ("Complete metadata paper", "Author Four", "10.1000/complete", "Complete Journal", "2026", "在线打开", "下载"):
            self.assertContains(response, value)
        for removed in ("Complete abstract text.", "user-tag", "source-tag", "ai-tag", "complete.pdf", "/complete.pdf", "123456", "查看完整证据", "外部引用"):
            self.assertNotContains(response, removed)
        self.assertContains(response, "元数据需处理")
        self.assertContains(response, "不完整、待复核或冲突")
        self.assertContains(response, "Agent 可检索")
        self.assertContains(response, "查看并处理")
        self.assertContains(response, "PDF 上传成功即发布")
        self.assertContains(response, "PDF 上传成功后会立即向 Agent 发布")
        html = response.content.decode()
        self.assertNotIn(">摘要</th>", html)
        self.assertLess(html.index(">状态</th>"), html.index(">文献操作</th>"))
        self.assertLess(html.index(">文献操作</th>"), html.index(">PDF 附件</th>"))

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

    @patch("apps.box_upload.views.fetch_zotero_collections", return_value=[{"name": "Physics", "key": "COLL1234"}])
    def test_zotero_connect_saves_encrypted_credentials(self, fetch_collections):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.post("/zotero/import/", data={
            "action": "connect",
            "library_type": "users",
            "library_id": "123",
            "api_key": "secret-key",
        })

        self.assertEqual(response.json()["collections"], [{"name": "Physics", "key": "COLL1234"}])
        connection = ZoteroConnection.objects.get(user=self.user)
        self.assertNotIn("secret-key", connection.api_key_ciphertext)
        self.assertEqual(decrypt_zotero_api_key(connection.api_key_ciphertext), "secret-key")
        fetch_collections.assert_called_once_with("users", "123", "secret-key")

        ciphertext = connection.api_key_ciphertext
        fetch_collections.side_effect = ZoteroImportError("invalid credentials")
        failed = self.client.post("/zotero/import/", data={
            "action": "connect", "library_type": "users", "library_id": "999", "api_key": "wrong-key",
        })
        connection.refresh_from_db()
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(connection.api_key_ciphertext, ciphertext)
        self.assertNotContains(failed, "wrong-key", status_code=400)

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

    def test_zotero_import_is_upgrade_only_for_members(self):
        page = self.client.get("/zotero/import/")
        post = self.client.post("/zotero/import/", data={
            "library_type": "users",
            "library_id": "123",
            "api_key": "secret-key",
        })

        self.assertContains(page, "正在测试升级当中")
        self.assertNotContains(page, "zotero-import-form")
        self.assertEqual(post.status_code, 403)

    @patch("apps.box_upload.views.iter_zotero_import_library", return_value=iter((
        {"progress": 5, "message": "正在连接 Zotero"},
        {"progress": 100, "message": "导入完成", "result": {"created": 1, "reused": 0, "skipped": 0}, "done": True},
    )))
    def test_staff_zotero_import_streams_progress(self, import_library):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        ZoteroConnection.objects.create(
            user=self.user,
            library_type="users",
            library_id="123",
            api_key_ciphertext=encrypt_zotero_api_key("secret-key"),
        )
        response = self.client.post("/zotero/import/", data={
            "action": "import",
            "item_keys": ["ITEM1234", "ITEM5678"],
        }, HTTP_ACCEPT="application/x-ndjson")

        events = [json.loads(line) for line in b"".join(response.streaming_content).decode().splitlines()]
        self.assertEqual([event["progress"] for event in events], [5, 100])
        self.assertTrue(events[-1]["done"])
        self.assertEqual(response["X-Accel-Buffering"], "no")
        import_library.assert_called_once_with(
            "users",
            "123",
            "secret-key",
            item_keys=["ITEM1234", "ITEM5678"],
            browser_pdfs={},
            uploader=self.user,
        )

    @patch("apps.box_upload.views.iter_zotero_import_library", return_value=iter((
        {"progress": 100, "message": "导入完成", "result": {"pdf_failed": 0}, "done": True},
    )))
    def test_zotero_import_accepts_only_pdf_bound_to_selected_item(self, import_library):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        ZoteroConnection.objects.create(
            user=self.user,
            library_type="users",
            library_id="123",
            api_key_ciphertext=encrypt_zotero_api_key("secret-key"),
        )
        selected = SimpleUploadedFile("selected.pdf", b"%PDF-1.7\nselected", content_type="application/pdf")
        forged = SimpleUploadedFile("forged.pdf", b"%PDF-1.7\nforged", content_type="application/pdf")

        response = self.client.post("/zotero/import/", data={
            "action": "import",
            "item_keys": ["ITEM1234"],
            "pdf_ITEM1234": selected,
            "pdf_OTHER123": forged,
        }, HTTP_ACCEPT="application/x-ndjson")
        list(response.streaming_content)

        browser_pdfs = import_library.call_args.kwargs["browser_pdfs"]
        self.assertEqual(list(browser_pdfs), ["ITEM1234"])
        self.assertEqual(browser_pdfs["ITEM1234"].name, "selected.pdf")

    @patch("apps.box_upload.views.fetch_zotero_items")
    def test_staff_browses_collection_items(self, fetch_items):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        ZoteroConnection.objects.create(
            user=self.user,
            library_type="users",
            library_id="123",
            api_key_ciphertext=encrypt_zotero_api_key("secret-key"),
        )
        fetch_items.return_value = [{
            "key": "ITEM1234",
            "version": 1,
            "data": {"itemType": "journalArticle", "title": "Selected paper", "creators": []},
        }]

        response = self.client.post("/zotero/import/", data={"action": "items", "collection_key": "COLL1234"})

        self.assertEqual(response.json()["items"][0], {
            "key": "ITEM1234", "title": "Selected paper", "year": None, "authors": [],
        })
        fetch_items.assert_called_once_with(
            "users", "123", "secret-key", collection_key="COLL1234"
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

    def test_retired_nju_box_stream_raises_without_network_access(self):
        with self.assertRaisesMessage(NjuBoxUploadError, "retired"):
            stream_from_nju_box("/paper.pdf", byte_range="bytes=0-7")

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

    @skip("NJU Box backend retired")
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

    @skip("NJU Box backend retired")
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

    @skip("NJU Box backend retired")
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

    @skip("NJU Box backend retired")
    @patch.dict("os.environ", {}, clear=True)
    def test_upload_requires_repository_configuration(self):
        with self.assertRaises(NjuBoxUploadError):
            upload_to_nju_box(SimpleUploadedFile("test.pdf", b"pdf"), "api-token", "library-password")

    @skip("NJU Box backend retired")
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

    @skip("NJU Box backend retired")
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

    @skip("NJU Box backend retired")
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
    def test_multiple_dois_select_the_work_whose_title_matches_the_pdf(self):
        cases = [
            (
                "Optical corner detection with azimuthal Hilbert transform metasurfaces",
                "10.3788/pi.2023.r01",
                "Revolutionary meta-imaging: from superlens to metalens",
                "10.1126/sciadv.aed8301",
            ),
            (
                "Holographic lasing with dielectric metasurfaces",
                "10.5281/zenodo.19590759",
                "MATLAB code for genetic optimization of a holographic lasing metasurface",
                "10.1126/sciadv.aea7345",
            ),
        ]
        for pdf_title, first_doi, first_title, expected_doi in cases:
            with self.subTest(pdf_title=pdf_title):
                evidence = {
                    "doi": first_doi,
                    "title": pdf_title,
                    "doi_candidates": [
                        {"doi": first_doi, "source": "pdf_page", "page": 8},
                        {"doi": expected_doi, "source": "pdf_page", "page": 9},
                    ],
                    "doi_source": {"source": "pdf_page", "page": 8},
                }
                bibtex = {
                    first_doi: f"@article{{wrong, title={{{first_title}}}, author={{Doe, Jane}}, year={{2026}}, doi={{{first_doi}}}}}",
                    expected_doi: f"@article{{right, title={{{pdf_title}}}, author={{Doe, Jane}}, year={{2026}}, doi={{{expected_doi}}}}}",
                }
                barrier = Barrier(len(bibtex))

                def concurrent_fetch(doi):
                    barrier.wait(timeout=1)
                    return bibtex[doi]

                doi, _ = select_pdf_doi(evidence, bibtex_fetcher=concurrent_fetch)

                self.assertEqual(doi, expected_doi)
                self.assertEqual(evidence["doi"], expected_doi)

    def test_multiple_matching_dois_prefer_published_article_over_dataset(self):
        title = "Quantum-enhanced time-domain spectroscopy"
        dataset_doi = "10.5525/gla.researchdata.1848"
        article_doi = "10.1126/sciadv.adt2187"
        evidence = {
            "doi": dataset_doi,
            "title": title,
            "doi_candidates": [
                {"doi": dataset_doi, "source": "pdf_page", "page": 7},
                {"doi": article_doi, "source": "pdf_page", "page": 7},
            ],
        }
        bibtex = {
            dataset_doi: (
                f"@misc{{data, title={{{title}}}, author={{Adamou, Dionysis}}, "
                f"year={{2024}}, doi={{{dataset_doi}}}}}"
            ),
            article_doi: (
                f"@article{{paper, title={{{title}}}, author={{Adamou, Dionysis}}, "
                f"journal={{Science Advances}}, year={{2025}}, doi={{{article_doi}}}}}"
            ),
        }

        doi, _ = select_pdf_doi(evidence, bibtex_fetcher=bibtex.__getitem__)

        self.assertEqual(doi, article_doi)

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

    @patch("apps.box_upload.metadata.PdfReader")
    def test_generated_pdf_title_uses_first_page_title_for_doi_matching(self, pdf_reader):
        class Page:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        article_doi = "10.1117/1.AP.6.5.056004"
        pages = [
            Page(
                "Superresolution imaging using superoscillatory\n"
                "diffractive neural networks\n"
                "Hang Chen ,a,\u2020 Sheng Gao ,a,\u2020\n"
                f"[DOI: {article_doi}]\n"
                "Abstract. Optical superoscillation enables far-field superresolution imaging."
            ),
            Page("second"),
            Page("Reference DOI 10.1000/REFERENCE.2"),
        ]
        pdf_reader.return_value = type(
            "Reader",
            (),
            {"metadata": {"/Title": "AP-24-110703 1..11"}, "pages": pages},
        )()
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n")

        evidence = extract_pdf_evidence(uploaded)

        self.assertEqual(
            evidence["title"],
            "Superresolution imaging using superoscillatory diffractive neural networks",
        )
        bibtex = {
            article_doi.lower(): (
                "@article{article, title={Superresolution imaging using superoscillatory "
                "diffractive neural networks}, author={Doe, Jane}, year={2024}, "
                f"doi={{{article_doi}}}}}"
            ),
            "10.1000/reference.2": (
                "@article{reference, title={An unrelated reference work}, author={Doe, Jane}, "
                "year={2024}, doi={10.1000/reference.2}}"
            ),
        }

        doi, _ = select_pdf_doi(evidence, bibtex_fetcher=bibtex.__getitem__)

        self.assertEqual(doi, article_doi.lower())

    @patch("apps.box_upload.metadata.PdfReader")
    def test_untitled_pdf_metadata_uses_first_page_title(self, pdf_reader):
        class Page:
            def extract_text(self):
                return (
                    "Spatial Terahertz Modulator\n"
                    "Zhenwei Xie1,2* Xinke Wang1* Jiasheng Ye1\n"
                    "Abstract\nTerahertz technology is developing rapidly."
                )

        pdf_reader.return_value = type(
            "Reader",
            (),
            {"metadata": {"/Title": "untitled"}, "pages": [Page()]},
        )()

        evidence = extract_pdf_evidence(SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n"))

        self.assertEqual(evidence["title"], "Spatial Terahertz Modulator")

    @patch("apps.box_upload.metadata.PdfReader")
    def test_untitled_pdf_metadata_stays_empty_when_first_page_title_is_unavailable(self, pdf_reader):
        class Page:
            def extract_text(self):
                return ""

        pdf_reader.return_value = type(
            "Reader",
            (),
            {"metadata": {"/Title": "untitled"}, "pages": [Page()]},
        )()

        evidence = extract_pdf_evidence(SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n"))

        self.assertIsNone(evidence["title"])

    @patch("apps.box_upload.metadata.PdfReader")
    def test_empty_pdf_metadata_uses_first_page_title_and_numbered_authors(self, pdf_reader):
        class Page:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        pdf_reader.return_value = type(
            "Reader",
            (),
            {
                "metadata": {},
                "pages": [
                    Page(
                        "Optical Diffusion Models for Image Generation\n"
                        "Ilker Oguz1 Niyazi Ulas Dinc1 Mustafa Yildirim1 Junjie Ke2 Innfarn Yoo2\n"
                        "Qifei Wang3 Feng Yang2\u2217 Christophe Moser1\u2217 Demetri Psaltis1\u2217\n"
                        "1 Ecole Polytechnique Federale de Lausanne 2 Google Research 3 Google\n"
                        "Abstract\n"
                        "Diffusion models generate new samples."
                    )
                ],
            },
        )()
        uploaded = SimpleUploadedFile("paper.pdf", b"%PDF-1.7\n")

        evidence = extract_pdf_evidence(uploaded)

        self.assertEqual(evidence["title"], "Optical Diffusion Models for Image Generation")
        self.assertEqual(
            evidence["authors"],
            [
                "Ilker Oguz",
                "Niyazi Ulas Dinc",
                "Mustafa Yildirim",
                "Junjie Ke",
                "Innfarn Yoo",
                "Qifei Wang",
                "Feng Yang",
                "Christophe Moser",
                "Demetri Psaltis",
            ],
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

    def test_bibtex_parser_accepts_full_month_names_case_insensitively(self):
        months = (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )
        for month in months:
            for value in (month, month.lower(), month.upper()):
                with self.subTest(value=value):
                    entry, metadata = parse_bibtex_metadata(
                        f"@article{{paper, title={{Month paper}}, month={value}, doi={{10.1000/MONTH.1}}}}",
                        expected_doi="10.1000/month.1",
                    )

                    self.assertEqual(entry["month"], month)
                    self.assertEqual(metadata["title"], "Month paper")

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
        self.assertEqual(literature.index_status, CanonicalDocument.IndexStatus.PENDING)
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

    def test_selected_item_keys_are_sent_to_zotero(self):
        urls = []

        def request_page(url, api_key):
            urls.append(url)
            return ([], {})

        result = import_zotero_library(
            "users", "123", "secret-key", item_keys=["ABCD1234"], request_page=request_page
        )

        self.assertIn("itemKey=ABCD1234", urls[0])
        self.assertEqual(result["created"], 0)

    def test_browser_pdf_has_priority_and_invalid_file_preserves_metadata(self):
        user = User.objects.create_user(username="zotero-browser", password="test-pass")
        store_file = MagicMock(return_value=StoredLiteratureObject(NAS_WEBDAV, "/zotero/browser.pdf"))
        request_file = MagicMock()
        valid_result = import_zotero_library(
            "users",
            "123",
            "secret-key",
            uploader=user,
            browser_pdfs={"ITEM123": SimpleUploadedFile("browser.pdf", b"%PDF-1.7\nbrowser")},
            request_page=self._request_page,
            request_file=request_file,
            store_file=store_file,
        )

        self.assertEqual(valid_result["pdf_browser"], 1)
        self.assertEqual(valid_result["pdf_imported"], 1)
        browser_upload = UploadedDocument.objects.get()
        self.assertEqual(browser_upload.original_name, "browser.pdf")
        self.assertEqual(browser_upload.canonical_document.index_status, CanonicalDocument.IndexStatus.PUBLISHED)
        self.assertEqual(browser_upload.canonical_document.sha256, hashlib.sha256(b"%PDF-1.7\nbrowser").hexdigest())
        request_file.assert_not_called()

        def invalid_request_page(url, api_key):
            return ([{
                "key": "BADF1234",
                "version": 1,
                "data": {"itemType": "journalArticle", "title": "Metadata survives", "creators": []},
            }], {})

        invalid_result = import_zotero_library(
            "users",
            "456",
            "secret-key",
            uploader=user,
            browser_pdfs={"BADF1234": SimpleUploadedFile("wrong.pdf", b"not a pdf")},
            request_page=invalid_request_page,
            request_file=request_file,
            store_file=store_file,
        )
        self.assertEqual(invalid_result["pdf_failed"], 1)
        self.assertEqual(CanonicalDocument.objects.count(), 2)
        self.assertEqual(ExternalReference.objects.filter(library_id="456").count(), 1)
        self.assertEqual(UploadedDocument.objects.count(), 1)
        self.assertEqual(store_file.call_count, 1)
        request_file.assert_not_called()

    @override_settings(MCP_MAX_UPLOAD_BYTES=12)
    def test_browser_pdf_over_size_limit_preserves_metadata_without_storage(self):
        user = User.objects.create_user(username="zotero-large", password="test-pass")
        store_file = MagicMock()

        result = import_zotero_library(
            "users",
            "123",
            "secret-key",
            uploader=user,
            browser_pdfs={"ITEM123": SimpleUploadedFile("large.pdf", b"%PDF-1.7\nlarge")},
            request_page=self._request_page,
            store_file=store_file,
        )

        self.assertEqual(result["pdf_failed"], 1)
        self.assertEqual(CanonicalDocument.objects.get().index_status, CanonicalDocument.IndexStatus.PENDING)
        self.assertFalse(UploadedDocument.objects.exists())
        store_file.assert_not_called()

    def test_imports_only_hosted_pdfs_and_isolates_one_failure(self):
        user = User.objects.create_user(username="zotero-admin", password="test-pass")
        valid_pdf = b"%PDF-1.7\ncontent"

        def request_page(url, api_key):
            self.assertEqual(api_key, "secret-key")
            if "/children" not in url:
                return self._request_page(url, api_key)
            if "start=100" in url:
                return ([
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
                {"key": "BROKEN", "data": {
                    "itemType": "attachment", "linkMode": "imported_file",
                    "contentType": "application/pdf", "filename": "broken.pdf",
                }},
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
            {"pdf_imported": 1, "pdf_reused": 0, "pdf_skipped": 4, "pdf_failed": 1},
        )
        self.assertIn("broken.pdf", result["pdf_failures"][0])
        self.assertEqual(UploadedDocument.objects.count(), 1)
        self.assertEqual(UploadedDocument.objects.get().original_name, "hosted.pdf")
        self.assertEqual(store_file.call_count, 1)
        canonical = CanonicalDocument.objects.get()
        self.assertEqual(canonical.title, "Structured Zotero paper")
        self.assertEqual(canonical.index_status, CanonicalDocument.IndexStatus.PUBLISHED)

    def test_existing_doi_pdf_merges_a_different_zotero_uploader_without_download(self):
        from .zotero import _import_zotero_pdf

        owner = User.objects.create_user(username="owner", password="test-pass")
        newcomer = User.objects.create_user(username="newcomer", password="test-pass")
        canonical = CanonicalDocument.objects.create(doi="10.1000/shared-zotero", sha256="9" * 64)
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=owner,
            original_name="existing.pdf",
            remote_path="/existing.pdf",
            sha256="9" * 64,
            size=1,
        )
        request_file = MagicMock()
        store_file = MagicMock()

        outcome = _import_zotero_pdf(
            canonical,
            newcomer,
            "users",
            "123",
            "secret-key",
            {"item_key": "ATTACHMENT", "filename": "paper.pdf"},
            request_file=request_file,
            store_file=store_file,
        )

        self.assertEqual(outcome, "reused")
        self.assertEqual(set(canonical.uploaders.values_list("username", flat=True)), {"owner", "newcomer"})
        canonical.refresh_from_db()
        self.assertEqual(canonical.index_status, CanonicalDocument.IndexStatus.PUBLISHED)
        self.assertEqual(UploadedDocument.objects.count(), 1)
        request_file.assert_not_called()
        store_file.assert_not_called()

    def test_removes_stored_pdf_if_upload_row_creation_fails(self):
        from .zotero import _import_zotero_pdf

        user = User.objects.create_user(username="zotero-cleanup", password="test-pass")
        canonical = CanonicalDocument.objects.create(title="Cleanup")
        stored = StoredLiteratureObject(NAS_WEBDAV, "/zotero/orphan.pdf")
        storage = MagicMock()

        with (
            patch("apps.box_upload.ingestion.UploadedDocument.objects.create", side_effect=RuntimeError("db failed")),
            patch("apps.box_upload.ingestion.get_literature_storage", return_value=storage),
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

    def test_prefers_local_pdf_then_falls_back_to_web(self):
        from .zotero import ZoteroImportError, _import_zotero_pdf

        user = User.objects.create_user(username="zotero-local", password="test-pass")
        web_file = MagicMock(return_value=BytesIO(b"%PDF-1.7\nweb"))
        store_file = MagicMock(side_effect=[
            StoredLiteratureObject(NAS_WEBDAV, "/zotero/local.pdf"),
            StoredLiteratureObject(NAS_WEBDAV, "/zotero/web.pdf"),
        ])
        local_attachment = {"item_key": "LOCAL123", "filename": "local.pdf"}
        web_attachment = {"item_key": "WEBF1234", "filename": "web.pdf"}

        local_outcome = _import_zotero_pdf(
            CanonicalDocument.objects.create(title="Local"),
            user,
            "users",
            "123",
            "secret-key",
            local_attachment,
            request_file=web_file,
            store_file=store_file,
            local_api_available=True,
            request_local_text=lambda _url: "file:///C:/Zotero/storage/local.pdf",
            open_local_file=lambda _path, _mode: BytesIO(b"%PDF-1.7\nlocal"),
        )
        web_outcome = _import_zotero_pdf(
            CanonicalDocument.objects.create(title="Web"),
            user,
            "users",
            "123",
            "secret-key",
            web_attachment,
            request_file=web_file,
            store_file=store_file,
            local_api_available=True,
            request_local_text=MagicMock(side_effect=ZoteroImportError("local unavailable")),
        )

        self.assertEqual((local_outcome, local_attachment["_pdf_source"]), ("imported", "local"))
        self.assertEqual((web_outcome, web_attachment["_pdf_source"]), ("imported", "web"))
        self.assertEqual(web_file.call_count, 1)
