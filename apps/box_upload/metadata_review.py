from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .ai_metadata import canonical_metadata_snapshot, normalize_doi
from .models import CanonicalDocument, MetadataProposal


EDITABLE_FIELDS = ("title", "authors", "abstract", "journal", "publication_year", "doi", "ai_tags")


def can_review_document(user, canonical):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_staff:
        return True
    return canonical.uploads.filter(uploader=user).exists()


def proposals_for_user(user):
    queryset = MetadataProposal.objects.select_related(
        "canonical_document",
        "source_upload",
        "requested_by",
        "reviewed_by",
    )
    if user.is_staff:
        return queryset
    return queryset.filter(canonical_document__uploads__uploader=user).distinct()


def apply_metadata_proposal(proposal_id, reviewer, values):
    with transaction.atomic():
        proposal = MetadataProposal.objects.select_for_update().select_related("canonical_document").get(pk=proposal_id)
        canonical = CanonicalDocument.objects.select_for_update().get(pk=proposal.canonical_document_id)
        if not can_review_document(reviewer, canonical):
            raise PermissionError("You cannot review this literature record.")
        if proposal.status != MetadataProposal.Status.SUCCEEDED:
            raise ValueError("Only a succeeded proposal can be accepted.")
        generated_snapshot = (proposal.evidence_snapshot or {}).get("canonical")
        canonical_changed = canonical.updated_at != proposal.canonical_updated_at
        if generated_snapshot:
            canonical_changed = canonical_changed or canonical_metadata_snapshot(canonical) != generated_snapshot
        if canonical_changed:
            proposal.status = MetadataProposal.Status.STALE
            proposal.reviewed_by = reviewer
            proposal.reviewed_at = timezone.now()
            proposal.save(update_fields=("status", "reviewed_by", "reviewed_at"))
            return proposal, False

        before = canonical_metadata_snapshot(canonical)
        original_index_status = canonical.index_status
        for field in EDITABLE_FIELDS:
            setattr(canonical, field, values.get(field))
        canonical.doi = normalize_doi(canonical.doi)
        if canonical.doi:
            canonical.identifiers = {**canonical.identifiers, "doi": canonical.doi}
        else:
            canonical.identifiers = {key: value for key, value in canonical.identifiers.items() if key.lower() != "doi"}
        complete = metadata_is_complete(canonical)
        canonical.metadata_status = (
            CanonicalDocument.MetadataStatus.VERIFIED
            if complete
            else CanonicalDocument.MetadataStatus.NEEDS_REVIEW
        )
        canonical.metadata_source = "human_review"
        canonical.metadata_confidence = Decimal("1.000") if complete else Decimal("0.800")
        if complete:
            canonical.metadata_candidates = {}
        canonical.metadata_evidence = {
            **canonical.metadata_evidence,
            "ai_review": {
                "proposal_id": proposal.id,
                "provider": proposal.provider,
                "model": proposal.model,
                "prompt_version": proposal.prompt_version,
                "reviewed_by_id": reviewer.id,
                "reviewed_at": timezone.now().isoformat(),
                "field_evidence": proposal.proposal.get("field_evidence", {}),
            },
        }
        canonical.index_status = original_index_status
        canonical.save()

        proposal.status = MetadataProposal.Status.ACCEPTED
        proposal.reviewed_by = reviewer
        proposal.reviewed_at = timezone.now()
        proposal.accepted_before = before
        proposal.accepted_after = canonical_metadata_snapshot(canonical)
        proposal.save(update_fields=("status", "reviewed_by", "reviewed_at", "accepted_before", "accepted_after"))
        return proposal, True


def reject_metadata_proposal(proposal_id, reviewer):
    with transaction.atomic():
        proposal = MetadataProposal.objects.select_for_update().select_related("canonical_document").get(pk=proposal_id)
        if not can_review_document(reviewer, proposal.canonical_document):
            raise PermissionError("You cannot review this literature record.")
        if proposal.status not in {MetadataProposal.Status.SUCCEEDED, MetadataProposal.Status.FAILED}:
            raise ValueError("This proposal cannot be rejected.")
        proposal.status = MetadataProposal.Status.REJECTED
        proposal.reviewed_by = reviewer
        proposal.reviewed_at = timezone.now()
        proposal.save(update_fields=("status", "reviewed_by", "reviewed_at"))
        return proposal


def metadata_is_complete(canonical):
    return bool(
        canonical.title.strip()
        and canonical.authors
        and canonical.publication_year
        and (canonical.doi.strip() or canonical.journal.strip())
    )
