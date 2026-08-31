import base64
import hashlib
from urllib.parse import urlsplit
from unittest.mock import patch

from django.contrib.auth.models import User
from django.conf import settings
from django.test import Client, TransactionTestCase, override_settings
from starlette.testclient import TestClient

from apps.box_upload.models import (
    CanonicalDocument,
    MetadataProposal,
    UploadedDocument,
    UploadReviewBatch,
    UploadReviewItem,
)
from apps.box_upload.storage import NAS_WEBDAV, StoredLiteratureObject
from apps.mcp_gateway.models import McpAccessToken
from apps.mcp_gateway.forms import McpAccessTokenForm
from apps.skills.models import GitHubSkillSource, SharedSkill, SharedSkillRelease
from config.asgi import application


class McpHttpTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mcp_client = TestClient(application)
        cls.mcp_client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mcp_client.__exit__(None, None, None)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="mcp-user", password="Strong-pass-1234")
        self.token, self.plaintext = McpAccessToken.issue(
            owner=self.user,
            label="test client",
            scopes=[
                McpAccessToken.LITERATURE_READ,
                McpAccessToken.LITERATURE_WRITE,
                McpAccessToken.SKILLS_READ,
            ],
        )
        self.token.save()
        canonical = CanonicalDocument.objects.create(
            sha256="a" * 64,
            title="MCP Paper",
            doi="10.1000/mcp",
            metadata_status=CanonicalDocument.MetadataStatus.VERIFIED,
            index_status=CanonicalDocument.IndexStatus.PUBLISHED,
        )
        self.canonical = canonical
        self.document = UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=self.user,
            original_name="mcp-paper.pdf",
            remote_path="/mcp-paper.pdf",
            sha256="a" * 64,
            size=4,
            content_type="application/pdf",
        )
        source = GitHubSkillSource.objects.create(
            name="Test Skills",
            slug="test-skills",
            repository_url="https://github.com/example/test-skills",
        )
        self.skill = SharedSkill.objects.create(
            source=source,
            slug="pdf-reader",
            name="PDF Reader",
            description="Read academic PDFs.",
            source_path="skills/pdf-reader",
        )
        self.release = SharedSkillRelease.objects.create(
            skill=self.skill,
            git_commit="b" * 40,
            archive_name="pdf-reader.zip",
            archive_remote_path="/skills/pdf-reader.zip",
            archive_size=10,
        )

    def _headers(self, authorized=True):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
            "Host": urlsplit(settings.MCP_PUBLIC_BASE_URL).netloc,
        }
        if authorized:
            headers["Authorization"] = f"Bearer {self.plaintext}"
        return headers

    def _call(self, client, name, arguments, request_id=2):
        return client.post(
            "/mcp",
            headers=self._headers(),
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        )

    def _initialize(self, client, authorized=True):
        return client.post(
            "/mcp",
            headers=self._headers(authorized),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
        )

    @staticmethod
    def _tool_text(response):
        return response.json()["result"]["content"][0]["text"]

    def test_mcp_requires_bearer_token(self):
        response = self._initialize(self.mcp_client, authorized=False)

        self.assertEqual(response.status_code, 401)

    def test_mcp_lists_literature_for_authorized_token(self):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        response = self._call(self.mcp_client, "list_literature", {"query": "MCP"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("structuredContent", response.json()["result"])
        result = self._tool_text(response)
        self.assertIn("共 1 条", result)
        self.assertIn(f"文献 ID: {self.canonical.id}", result)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_mcp_hides_pending_literature(self):
        CanonicalDocument.objects.create(sha256="c" * 64, title="Pending private paper")
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)

        response = self._call(self.mcp_client, "list_literature", {"query": "Pending private"})

        self.assertNotIn("Pending private paper", self._tool_text(response))

    @patch("apps.mcp_gateway.server.build_literature_download_url", return_value="https://plab.example.test/library/download/signed/token/")
    def test_mcp_download_uses_published_canonical_literature_id(self, build_download_url):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)

        response = self._call(
            self.mcp_client,
            "get_literature_download_link",
            {"document_id": self.canonical.id},
        )

        self.assertIn("https://plab.example.test/library/download/signed/token/", self._tool_text(response))
        self.assertEqual(build_download_url.call_args.args[0].pk, self.document.pk)

    @patch("apps.mcp_gateway.server.build_literature_download_url", return_value="https://plab.example.test/library/download/signed/token/")
    def test_mcp_download_prefers_primary_pdf_over_supplementary_material(self, build_download_url):
        supplementary = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=self.user,
            original_name="mcp-paper-supplement.pdf",
            remote_path="/mcp-paper-supplement.pdf",
            sha256="b" * 64,
            size=4,
            content_type="application/pdf",
            file_role=UploadedDocument.FileRole.SUPPLEMENTARY,
        )
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)

        response = self._call(
            self.mcp_client,
            "get_literature_download_link",
            {"document_id": self.canonical.id},
        )

        self.assertIn("https://plab.example.test/library/download/signed/token/", self._tool_text(response))
        self.assertEqual(build_download_url.call_args.args[0].pk, self.document.pk)
        self.assertNotEqual(build_download_url.call_args.args[0].pk, supplementary.pk)

    @patch(
        "apps.box_upload.upload_review.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/literature/mcp-staged.pdf"),
    )
    @patch("apps.box_upload.upload_review.extract_pdf_evidence", return_value={
        "title": "Staged MCP Paper",
        "authors": [{"name": "Ada Lovelace"}],
        "doi": "",
        "doi_candidates": [],
    })
    def test_mcp_upload_stages_owned_review_without_formal_records_or_search_visibility(self, extract_evidence, store_file):
        canonical_count = CanonicalDocument.objects.count()
        upload_count = UploadedDocument.objects.count()
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        response = self._call(self.mcp_client, "upload_literature", {
            "filename": "mcp-staged.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\ncontent").decode("ascii"),
            "content_type": "application/pdf",
        })

        self.assertEqual(response.status_code, 200)
        batch = UploadReviewBatch.objects.get()
        item = batch.items.get()
        result = self._tool_text(response)
        self.assertIn("状态: pending_review", result)
        self.assertIn(f"Batch ID: {batch.pk}", result)
        self.assertIn(f"网页审核地址: {settings.MCP_PUBLIC_BASE_URL}/upload/?batch={batch.pk}", result)
        self.assertIn("Staged MCP Paper", result)
        self.assertEqual(batch.uploader, self.user)
        self.assertEqual(item.original_name, "mcp-staged.pdf")
        self.assertEqual(CanonicalDocument.objects.count(), canonical_count)
        self.assertEqual(UploadedDocument.objects.count(), upload_count)
        self.assertFalse(MetadataProposal.objects.exists())
        listed = self._call(self.mcp_client, "list_literature", {"query": "mcp-staged.pdf"})
        self.assertIn("共 0 条", self._tool_text(listed))
        extract_evidence.assert_called_once()
        store_file.assert_called_once()

    @patch(
        "apps.box_upload.upload_review.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/literature/owned-review.pdf"),
    )
    @patch("apps.box_upload.upload_review.extract_pdf_evidence", return_value={
        "title": "Owned Review",
        "authors": [],
        "doi": "",
        "doi_candidates": [],
    })
    def test_mcp_uploader_can_open_review_page_but_other_user_gets_404(self, extract_evidence, store_file):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        self._call(self.mcp_client, "upload_literature", {
            "filename": "owned-review.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\nowned").decode("ascii"),
            "content_type": "application/pdf",
        })
        batch = UploadReviewBatch.objects.get()
        web = Client()
        web.force_login(self.user)

        owner_response = web.get(f"/upload/?batch={batch.pk}")
        other = User.objects.create_user(username="other-mcp-user", password="Strong-pass-1234")
        web.force_login(other)
        other_response = web.get(f"/upload/?batch={batch.pk}")

        self.assertEqual(owner_response.status_code, 200)
        self.assertContains(owner_response, "owned-review.pdf")
        self.assertEqual(other_response.status_code, 404)

    @patch(
        "apps.box_upload.upload_review.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/literature/confirmed-mcp.pdf"),
    )
    @patch("apps.box_upload.upload_review.extract_pdf_evidence", return_value={
        "title": "Confirmed MCP Paper",
        "authors": [],
        "doi": "",
        "doi_candidates": [],
    })
    def test_browser_confirmation_publishes_mcp_upload_for_mcp_search(self, extract_evidence, store_file):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        self._call(self.mcp_client, "upload_literature", {
            "filename": "confirmed-mcp.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\nconfirmed").decode("ascii"),
            "content_type": "application/pdf",
        })
        batch = UploadReviewBatch.objects.get()
        web = Client()
        web.force_login(self.user)

        confirm_response = web.post(f"/upload/batches/{batch.pk}/confirm/")

        self.assertEqual(confirm_response.status_code, 200)
        uploaded = UploadedDocument.objects.get(original_name="confirmed-mcp.pdf")
        self.assertEqual(uploaded.uploader, self.user)
        self.assertEqual(uploaded.canonical_document.index_status, CanonicalDocument.IndexStatus.PUBLISHED)
        listed = self._call(self.mcp_client, "list_literature", {"query": "Confirmed MCP Paper"})
        self.assertIn(f"文献 ID: {uploaded.canonical_document_id}", self._tool_text(listed))

    @patch("apps.box_upload.upload_review.store_literature")
    def test_mcp_rejects_invalid_pdf_before_storage(self, store_file):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)

        response = self._call(self.mcp_client, "upload_literature", {
            "filename": "fake.pdf",
            "content_base64": base64.b64encode(b"not a pdf").decode("ascii"),
            "content_type": "application/pdf",
        })

        self.assertTrue(response.json()["result"].get("isError"))
        self.assertIn("有效 PDF", self._tool_text(response))
        store_file.assert_not_called()

    @override_settings(MCP_MAX_UPLOAD_BYTES=12)
    @patch("apps.box_upload.upload_review.store_literature")
    def test_mcp_rejects_oversized_pdf_before_storage(self, store_file):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)

        response = self._call(self.mcp_client, "upload_literature", {
            "filename": "large.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\nlarge").decode("ascii"),
            "content_type": "application/pdf",
        })

        self.assertTrue(response.json()["result"].get("isError"))
        store_file.assert_not_called()

    @patch("apps.box_upload.upload_review.delete_literature")
    @patch(
        "apps.box_upload.upload_review.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/literature/duplicate-stage.pdf"),
    )
    @patch("apps.box_upload.upload_review.extract_pdf_evidence", return_value={
        "title": "Duplicate PDF",
        "authors": [],
        "doi": "",
        "doi_candidates": [],
    })
    def test_confirmed_mcp_duplicate_reuses_body_and_associates_token_owner(self, extract_evidence, store_file, delete_literature):
        content = b"%PDF-1.7\nduplicate"
        original_uploader = User.objects.create_user(username="original-owner", password="Strong-pass-1234")
        existing = CanonicalDocument.objects.create(
            sha256=hashlib.sha256(content).hexdigest(),
            title="Existing Duplicate",
            metadata_status=CanonicalDocument.MetadataStatus.VERIFIED,
            index_status=CanonicalDocument.IndexStatus.PUBLISHED,
        )
        UploadedDocument.objects.create(
            canonical_document=existing,
            uploader=original_uploader,
            original_name="original.pdf",
            remote_path="/literature/original.pdf",
            sha256=existing.sha256,
            size=len(content),
        )
        upload_count = UploadedDocument.objects.count()
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        self._call(self.mcp_client, "upload_literature", {
            "filename": "duplicate.pdf",
            "content_base64": base64.b64encode(content).decode("ascii"),
            "content_type": "application/pdf",
        })
        batch = UploadReviewBatch.objects.get()
        web = Client()
        web.force_login(self.user)

        response = web.post(f"/upload/batches/{batch.pk}/confirm/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["state"], "merged")
        existing.refresh_from_db()
        self.assertEqual(UploadedDocument.objects.count(), upload_count)
        self.assertTrue(existing.uploaders.filter(pk=self.user.pk).exists())
        delete_literature.assert_called_once()

    @patch(
        "apps.box_upload.upload_review.store_literature",
        return_value=StoredLiteratureObject(NAS_WEBDAV, "/literature/title-warning.pdf"),
    )
    @patch("apps.box_upload.upload_review.fetch_doi_bibtex", return_value=(
        "@article{wrong, title={Unrelated DOI Work}, author={Lovelace, Ada}, "
        "journal={Journal of Tests}, year={2026}, doi={10.1000/warning}}"
    ))
    @patch("apps.box_upload.upload_review.extract_pdf_evidence", return_value={
        "title": "PDF Extracted Work",
        "authors": [],
        "doi": "10.1000/warning",
        "doi_candidates": [{"doi": "10.1000/warning", "source": "pdf_page", "page": 1}],
    })
    def test_mcp_returns_non_blocking_doi_title_warning(self, extract_evidence, fetch_bibtex, store_file):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        response = self._call(self.mcp_client, "upload_literature", {
            "filename": "title-warning.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\nwarning").decode("ascii"),
            "content_type": "application/pdf",
        })

        result = self._tool_text(response)
        item = UploadReviewItem.objects.get(original_name="title-warning.pdf")
        self.assertIn("DOI/BibTeX 标题与 PDF 提取标题明显不一致", result)
        self.assertIn("PDF Extracted Work", result)
        self.assertIn("Unrelated DOI Work", result)
        self.assertEqual(item.evidence["bibtex"]["title"], "Unrelated DOI Work")
        web = Client()
        web.force_login(self.user)
        confirm_response = web.post(f"/upload/batches/{item.batch_id}/confirm/")
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(
            CanonicalDocument.objects.get(title="Unrelated DOI Work").index_status,
            CanonicalDocument.IndexStatus.PUBLISHED,
        )

    def test_mcp_enforces_tool_scope(self):
        limited_token, limited_plaintext = McpAccessToken.issue(
            owner=self.user,
            label="read only",
            scopes=[McpAccessToken.LITERATURE_READ],
        )
        limited_token.save()
        self.plaintext = limited_plaintext
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        response = self._call(self.mcp_client, "list_skills", {})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["result"].get("isError"))
        self.assertIn("skills:read", response.json()["result"]["content"][0]["text"])

    @patch("apps.mcp_gateway.server.build_skill_download_url", return_value="https://plab.test/skills/download/token/")
    def test_mcp_lists_skills_and_returns_download_link(self, build_download_url):
        self.assertEqual(self._initialize(self.mcp_client).status_code, 200)
        list_response = self._call(self.mcp_client, "list_skills", {"query": "PDF Reader"})
        download_response = self._call(
            self.mcp_client,
            "get_skill_download_link",
            {"skill_id": self.skill.id},
            request_id=3,
        )

        self.assertIn(f"Skill ID: {self.skill.id}", self._tool_text(list_response))
        self.assertIn("https://plab.test/skills/download/token/", self._tool_text(download_response))
        build_download_url.assert_called_once_with(self.release)

    def test_access_token_form_uses_selected_scopes(self):
        form = McpAccessTokenForm(data={
            "owner": self.user.id,
            "label": "form token",
            "scopes": [McpAccessToken.LITERATURE_READ, McpAccessToken.SKILLS_READ],
            "is_active": True,
        })

        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["scopes"],
            [McpAccessToken.LITERATURE_READ, McpAccessToken.SKILLS_READ],
        )

    def test_admin_reveals_new_token_once_and_can_regenerate_it(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        client = Client()
        client.force_login(self.user)
        create_response = client.post("/admin/mcp_gateway/mcpaccesstoken/add/", {
            "owner": self.user.id,
            "label": "admin token",
            "scopes": [McpAccessToken.LITERATURE_READ],
            "is_active": "on",
            "_save": "保存",
        })

        self.assertContains(create_response, "离开此页面后无法再次查看")
        token = McpAccessToken.objects.get(label="admin token")
        self.assertNotContains(create_response, token.token_digest)

        regenerate_response = client.post(
            f"/admin/mcp_gateway/mcpaccesstoken/{token.pk}/change/",
            {
                "owner": self.user.id,
                "label": token.label,
                "scopes": [McpAccessToken.LITERATURE_READ],
                "is_active": "on",
                "_regenerate_token": "1",
            },
        )

        self.assertContains(regenerate_response, "旧令牌已立即失效")
