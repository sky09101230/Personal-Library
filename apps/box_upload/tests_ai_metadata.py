import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .ai_metadata import (
    DeepSeekProposalError,
    build_evidence_packet,
    generate_deepseek_proposal,
    validate_metadata_proposal,
)
from .metadata_jobs import (
    enqueue_metadata_proposal,
    enqueue_metadata_proposal_safely,
    process_next_metadata_proposal,
    queue_existing_metadata_proposals,
)
from .models import CanonicalDocument, MetadataProposal, UploadedDocument
from .storage import NAS_WEBDAV, StoredLiteratureObject


def proposal_payload(title="Proposed title"):
    return {
        "metadata": {
            "title": title,
            "authors": [{"name": "Ada Lovelace"}],
            "abstract": "A proposed abstract.",
            "journal": "Journal of Tests",
            "publication_year": 2026,
            "doi": "10.1000/test.1",
            "keywords": ["optics"],
        },
        "confidence": {"title": 0.95, "doi": 0.9},
        "evidence": {
            "title": [{"source": "pdf_page", "page": 1, "quote": title}],
        },
        "warnings": [],
    }


class MetadataEvidenceTests(TestCase):
    def test_evidence_packet_is_bounded_and_excludes_upload_identity(self):
        user = User.objects.create_user(username="uploader")
        canonical = CanonicalDocument.objects.create(
            title="Evidence title",
            metadata_evidence={"pdf": {"pages": [{"number": 1, "text": "x" * 7000}]}, "crossref": {"doi": "10.1000/test"}},
        )
        UploadedDocument.objects.create(
            canonical_document=canonical,
            uploader=user,
            original_name="private.pdf",
            remote_path="/secret/private.pdf",
            sha256="1" * 64,
            size=1,
        )

        packet = build_evidence_packet(canonical)
        serialized = json.dumps(packet)

        self.assertEqual(len(packet["pdf"]["pages"][0]["text"]), 6000)
        self.assertNotIn("/secret/private.pdf", serialized)
        self.assertNotIn("uploader", serialized)

    def test_unmatched_page_quote_becomes_warning(self):
        canonical = CanonicalDocument.objects.create(title="Current")
        packet = build_evidence_packet(canonical)
        packet["pdf"]["pages"] = [{"number": 1, "text": "Actual page title"}]
        payload = proposal_payload("Invented title")

        proposal, warnings = validate_metadata_proposal(payload, packet)

        self.assertEqual(proposal["title"], "Invented title")
        self.assertIn("未在输入文本中找到", warnings[0])
        self.assertNotIn("title", proposal["field_evidence"])


class DeepSeekClientTests(TestCase):
    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-v4-flash"}, clear=False)
    def test_json_output_is_validated(self):
        canonical = CanonicalDocument.objects.create(title="Current")
        packet = build_evidence_packet(canonical)
        packet["pdf"]["pages"] = [{"number": 1, "text": "Proposed title"}]
        calls = []

        def request_func(url, body, api_key, timeout):
            calls.append((url, body, api_key, timeout))
            return {
                "model": "deepseek-v4-flash",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(proposal_payload())}}],
            }

        result = generate_deepseek_proposal(packet, request_func=request_func)

        self.assertEqual(result["proposal"]["title"], "Proposed title")
        self.assertEqual(result["attempt_count"], 1)
        self.assertEqual(calls[0][1]["response_format"], {"type": "json_object"})
        self.assertEqual(calls[0][2], "test-key")

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_empty_output_retries_once(self):
        calls = []

        def request_func(*args):
            calls.append(args)
            return {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}

        with self.assertRaises(DeepSeekProposalError) as context:
            generate_deepseek_proposal({"canonical": {}, "pdf": {"pages": []}}, request_func=request_func)

        self.assertEqual(context.exception.code, "empty_output")
        self.assertEqual(len(calls), 2)

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_truncated_output_is_not_accepted(self):
        with self.assertRaises(DeepSeekProposalError) as context:
            generate_deepseek_proposal(
                {"canonical": {}, "pdf": {"pages": []}},
                request_func=lambda *args: {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            )
        self.assertEqual(context.exception.code, "truncated")

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_malformed_json_is_rejected(self):
        with self.assertRaises(DeepSeekProposalError) as context:
            generate_deepseek_proposal(
                {"canonical": {}, "pdf": {"pages": []}},
                request_func=lambda *args: {"choices": [{"finish_reason": "stop", "message": {"content": "{broken"}}]},
            )
        self.assertEqual(context.exception.code, "invalid_json")

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_retryable_transport_error_retries_once(self):
        calls = []

        def request_func(*args):
            calls.append(args)
            raise DeepSeekProposalError("transport_error", "offline", retryable=True)

        with self.assertRaises(DeepSeekProposalError):
            generate_deepseek_proposal({"canonical": {}, "pdf": {"pages": []}}, request_func=request_func)
        self.assertEqual(len(calls), 2)


class MetadataJobTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner")
        self.canonical = CanonicalDocument.objects.create(
            title="Needs review",
            metadata_status=CanonicalDocument.MetadataStatus.NEEDS_REVIEW,
        )
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=self.user,
            original_name="paper.pdf",
            remote_path="/paper.pdf",
            sha256="2" * 64,
            size=1,
        )

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_queue_reuses_active_job_and_worker_does_not_change_canonical(self):
        first = enqueue_metadata_proposal(self.canonical, requested_by=self.user, source_upload=self.upload)
        second = enqueue_metadata_proposal(self.canonical, requested_by=self.user, source_upload=self.upload)

        processed = process_next_metadata_proposal(generator=lambda packet: {
            "proposal": {"title": "Candidate", "authors": [], "abstract": "", "journal": "", "publication_year": None, "doi": "", "ai_tags": [], "field_confidence": {}, "field_evidence": {}},
            "warnings": ["Needs author"],
            "model": "mock-model",
            "prompt_version": "test-v1",
            "attempt_count": 1,
        })

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(processed.status, MetadataProposal.Status.SUCCEEDED)
        self.canonical.refresh_from_db()
        self.assertEqual(self.canonical.title, "Needs review")
        self.assertEqual(self.canonical.metadata_status, CanonicalDocument.MetadataStatus.NEEDS_REVIEW)

    @patch.dict("os.environ", {}, clear=True)
    def test_disabled_provider_records_failure_without_changing_metadata(self):
        proposal = enqueue_metadata_proposal(self.canonical, requested_by=self.user, source_upload=self.upload)

        self.assertEqual(proposal.status, MetadataProposal.Status.FAILED)
        self.assertEqual(proposal.error_code, "disabled")
        self.canonical.refresh_from_db()
        self.assertEqual(self.canonical.index_status, CanonicalDocument.IndexStatus.PENDING)

    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False)
    def test_backfill_is_bounded_and_does_not_duplicate_active_job(self):
        first = queue_existing_metadata_proposals(requested_by=self.user, limit=1)
        second = queue_existing_metadata_proposals(requested_by=self.user, limit=1)

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(MetadataProposal.objects.count(), 1)

    def test_safe_enqueue_contains_internal_errors(self):
        with patch("apps.box_upload.metadata_jobs.enqueue_metadata_proposal", side_effect=RuntimeError("boom")):
            self.assertIsNone(enqueue_metadata_proposal_safely(self.canonical))


class MetadataReviewViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="Strong-pass-1234")
        self.other = User.objects.create_user(username="other", password="Strong-pass-1234")
        self.canonical = CanonicalDocument.objects.create(
            title="Old title",
            metadata_status=CanonicalDocument.MetadataStatus.NEEDS_REVIEW,
            index_status=CanonicalDocument.IndexStatus.PENDING,
        )
        self.upload = UploadedDocument.objects.create(
            canonical_document=self.canonical,
            uploader=self.owner,
            original_name="paper.pdf",
            remote_path="/paper.pdf",
            sha256="3" * 64,
            size=1,
        )
        self.proposal = MetadataProposal.objects.create(
            canonical_document=self.canonical,
            source_upload=self.upload,
            status=MetadataProposal.Status.SUCCEEDED,
            model="mock-model",
            prompt_version="test-v1",
            canonical_updated_at=self.canonical.updated_at,
            evidence_snapshot={"canonical": {
                "title": self.canonical.title,
                "authors": self.canonical.authors,
                "abstract": self.canonical.abstract,
                "journal": self.canonical.journal,
                "publication_year": self.canonical.publication_year,
                "doi": self.canonical.doi,
                "identifiers": self.canonical.identifiers,
                "source_tags": self.canonical.source_tags,
                "ai_tags": self.canonical.ai_tags,
                "metadata_source": self.canonical.metadata_source,
                "metadata_status": self.canonical.metadata_status,
            }},
            requested_by=self.owner,
            proposal={
                "title": "Confirmed title",
                "authors": [{"name": "Ada Lovelace"}],
                "abstract": "Confirmed abstract.",
                "journal": "Journal of Tests",
                "publication_year": 2026,
                "doi": "10.1000/test.1",
                "ai_tags": ["optics"],
                "field_confidence": {},
                "field_evidence": {},
            },
        )

    def _accept_data(self):
        return {
            "title": "Confirmed title",
            "authors": "Ada Lovelace",
            "abstract": "Confirmed abstract.",
            "journal": "Journal of Tests",
            "publication_year": "2026",
            "doi": "10.1000/test.1",
            "ai_tags": "optics, diffractive",
        }

    def test_only_uploader_or_staff_can_open_proposal(self):
        self.client.force_login(self.owner)
        owner_response = self.client.get(f"/library/metadata-review/{self.proposal.pk}/")
        self.canonical.uploaders.add(self.other)
        self.client.force_login(self.other)
        other_response = self.client.get(f"/library/metadata-review/{self.proposal.pk}/")

        self.assertEqual(owner_response.status_code, 200)
        self.assertContains(owner_response, f"/library/view/{self.upload.pk}/")
        self.assertContains(owner_response, "在线打开 PDF")
        self.assertEqual(other_response.status_code, 404)

    def test_queue_shows_candidate_metadata_and_actionable_counts(self):
        self.client.force_login(self.owner)

        response = self.client.get("/library/metadata-review/")

        self.assertContains(response, "Confirmed title")
        self.assertContains(response, "Ada Lovelace")
        self.assertContains(response, "待确认 <strong>1</strong>", html=True)
        self.assertContains(response, "1</strong> 篇可批量确认")
        self.assertContains(response, "确认选中安全项（不发布）")
        self.assertTrue(response.context["page"].object_list[0].bulk_safe)

    def test_queue_requires_individual_review_for_warning_bearing_proposal(self):
        risky_canonical = CanonicalDocument.objects.create(title="Risky current title")
        risky_upload = UploadedDocument.objects.create(
            canonical_document=risky_canonical,
            uploader=self.owner,
            original_name="risky.pdf",
            remote_path="/risky.pdf",
            sha256="6" * 64,
            size=1,
        )
        risky_proposal = MetadataProposal.objects.create(
            canonical_document=risky_canonical,
            source_upload=risky_upload,
            status=MetadataProposal.Status.SUCCEEDED,
            canonical_updated_at=risky_canonical.updated_at,
            proposal=self.proposal.proposal,
            validation_warnings=["标题证据需检查"],
        )
        self.client.force_login(self.owner)

        response = self.client.get("/library/metadata-review/")

        proposals = {proposal.pk: proposal for proposal in response.context["page"].object_list}
        self.assertTrue(proposals[self.proposal.pk].bulk_safe)
        self.assertFalse(proposals[risky_proposal.pk].bulk_safe)
        self.assertEqual(response.context["page_bulk_safe_count"], 1)
        self.assertEqual(response.context["page_individual_review_count"], 1)
        self.assertNotContains(response, f'name="proposal_ids" value="{risky_proposal.pk}"')
        self.assertContains(response, "需详情")

    def test_uploader_accepts_proposal_without_publishing(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            f"/library/metadata-review/{self.proposal.pk}/accept/",
            self._accept_data(),
        )

        self.assertRedirects(response, "/library/metadata-review/")
        self.canonical.refresh_from_db()
        self.proposal.refresh_from_db()
        self.assertEqual(self.canonical.title, "Confirmed title")
        self.assertEqual(self.canonical.metadata_status, CanonicalDocument.MetadataStatus.VERIFIED)
        self.assertEqual(self.canonical.index_status, CanonicalDocument.IndexStatus.PENDING)
        self.assertEqual(self.proposal.status, MetadataProposal.Status.ACCEPTED)
        self.assertEqual(self.proposal.reviewed_by, self.owner)
        self.assertEqual(self.proposal.accepted_before["title"], "Old title")

    def test_uploader_bulk_accepts_selected_proposals_without_publishing(self):
        other_canonical = CanonicalDocument.objects.create(title="Other title")
        other_upload = UploadedDocument.objects.create(
            canonical_document=other_canonical,
            uploader=self.other,
            original_name="other.pdf",
            remote_path="/other.pdf",
            sha256="4" * 64,
            size=1,
        )
        other_proposal = MetadataProposal.objects.create(
            canonical_document=other_canonical,
            source_upload=other_upload,
            status=MetadataProposal.Status.SUCCEEDED,
            canonical_updated_at=other_canonical.updated_at,
            proposal=self.proposal.proposal,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            "/library/metadata-review/bulk-accept/",
            {"proposal_ids": [self.proposal.pk, other_proposal.pk]},
        )

        self.assertRedirects(response, "/library/metadata-review/")
        self.canonical.refresh_from_db()
        self.proposal.refresh_from_db()
        other_canonical.refresh_from_db()
        other_proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, MetadataProposal.Status.ACCEPTED)
        self.assertEqual(self.canonical.index_status, CanonicalDocument.IndexStatus.PENDING)
        self.assertEqual(other_proposal.status, MetadataProposal.Status.SUCCEEDED)
        self.assertEqual(other_canonical.title, "Other title")

    def test_bulk_accept_skips_warning_bearing_proposal_even_when_posted_directly(self):
        self.proposal.validation_warnings = ["摘要证据需检查"]
        self.proposal.save(update_fields=["validation_warnings"])
        self.client.force_login(self.owner)

        response = self.client.post(
            "/library/metadata-review/bulk-accept/",
            {"proposal_ids": [self.proposal.pk]},
            follow=True,
        )

        self.proposal.refresh_from_db()
        self.canonical.refresh_from_db()
        self.assertEqual(self.proposal.status, MetadataProposal.Status.SUCCEEDED)
        self.assertEqual(self.canonical.title, "Old title")
        self.assertEqual(self.canonical.index_status, CanonicalDocument.IndexStatus.PENDING)
        self.assertContains(response, "需进入详情逐篇确认")

    def test_confirm_and_next_opens_next_succeeded_proposal(self):
        next_canonical = CanonicalDocument.objects.create(title="Next title")
        next_upload = UploadedDocument.objects.create(
            canonical_document=next_canonical,
            uploader=self.owner,
            original_name="next.pdf",
            remote_path="/next.pdf",
            sha256="5" * 64,
            size=1,
        )
        next_proposal = MetadataProposal.objects.create(
            canonical_document=next_canonical,
            source_upload=next_upload,
            status=MetadataProposal.Status.SUCCEEDED,
            canonical_updated_at=next_canonical.updated_at,
            proposal=self.proposal.proposal,
        )
        self.client.force_login(self.owner)
        data = {**self._accept_data(), "continue": "next"}

        response = self.client.post(f"/library/metadata-review/{self.proposal.pk}/accept/", data)

        self.assertRedirects(response, f"/library/metadata-review/{next_proposal.pk}/")

    def test_invalid_confirmation_keeps_remaining_count_context(self):
        self.client.force_login(self.owner)
        data = {**self._accept_data(), "title": ""}

        response = self.client.post(f"/library/metadata-review/{self.proposal.pk}/accept/", data)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "还剩 1 篇待确认", status_code=400)

    def test_stale_proposal_does_not_overwrite_newer_metadata(self):
        self.canonical.title = "Newer title"
        self.canonical.save()
        self.client.force_login(self.owner)

        self.client.post(f"/library/metadata-review/{self.proposal.pk}/accept/", self._accept_data())

        self.canonical.refresh_from_db()
        self.proposal.refresh_from_db()
        self.assertEqual(self.canonical.title, "Newer title")
        self.assertEqual(self.proposal.status, MetadataProposal.Status.STALE)

    def test_reject_leaves_canonical_unchanged(self):
        self.client.force_login(self.owner)

        response = self.client.post(f"/library/metadata-review/{self.proposal.pk}/reject/")

        self.assertRedirects(response, "/library/metadata-review/")
        self.canonical.refresh_from_db()
        self.proposal.refresh_from_db()
        self.assertEqual(self.canonical.title, "Old title")
        self.assertEqual(self.proposal.status, MetadataProposal.Status.REJECTED)

    def test_staff_can_review_zotero_only_record(self):
        staff = User.objects.create_user(username="staff", password="Strong-pass-1234", is_staff=True)
        zotero = CanonicalDocument.objects.create(title="Zotero only")
        proposal = MetadataProposal.objects.create(
            canonical_document=zotero,
            status=MetadataProposal.Status.SUCCEEDED,
            canonical_updated_at=zotero.updated_at,
            proposal=self.proposal.proposal,
        )
        self.client.force_login(staff)

        response = self.client.get(f"/library/metadata-review/{proposal.pk}/")

        self.assertEqual(response.status_code, 200)


class MetadataUploadIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="Strong-pass-1234")
        self.client.force_login(self.user)

    @patch(
        "apps.box_upload.views.store_literature",
        return_value=StoredLiteratureObject(
            NAS_WEBDAV,
            "/public/PLAB_KnowledgeBase/Literature/ai-review.pdf",
        ),
    )
    @patch.dict("os.environ", {
        "NJU_BOX_API_TOKEN": "env-token",
        "NJU_BOX_LIBRARY_PASSWORD": "env-password",
    }, clear=True)
    def test_upload_succeeds_and_records_disabled_ai_state(self, store_file):
        response = self.client.post("/upload/", data={
            "files": [SimpleUploadedFile("ai-review.pdf", b"%PDF-1.7\nno doi", content_type="application/pdf")],
        })

        self.assertEqual(response.status_code, 302)
        upload = UploadedDocument.objects.get(original_name="ai-review.pdf")
        self.assertEqual(upload.storage_backend, NAS_WEBDAV)
        proposal = MetadataProposal.objects.get()
        self.assertEqual(proposal.status, MetadataProposal.Status.FAILED)
        self.assertEqual(proposal.error_code, "disabled")
