## Context

The review queue currently places every succeeded proposal in the same pending list and allows every listed proposal ID to reach the bulk-accept endpoint. The form validator prevents structurally invalid metadata from being applied, but validation warnings are advisory and do not prevent a proposal from being bulk accepted. This leaves the uploader to manually identify low-risk proposals and creates a path for warning-bearing proposals to bypass individual evidence review.

The production evidence path remains pypdf. A three-paper read-only A/B test found no core metadata improvement from Docling, while parsing was materially slower and exact page-quote validation produced more warnings.

## Goals / Non-Goals

**Goals:**

- Make the common low-risk path require one review-page action instead of per-row selection.
- Make the bulk eligibility rule visible and identical in the queue and POST handler.
- Preserve uploader authorization, stale-proposal protection, audit fields, and the publication invariant.
- Record that Docling is not part of the production metadata workflow.

**Non-Goals:**

- Automatically accept proposals without an explicit uploader POST and confirmation dialog.
- Change proposal generation, pypdf extraction, the DeepSeek prompt, metadata completeness rules, or publication behavior.
- Add a new model, migration, job type, or PDF dependency.

## Decisions

1. A proposal is bulk-safe only when it is succeeded, has no validation warnings, and contains title, at least one named author, publication year, and either DOI or journal. This reuses the queue's existing completeness definition instead of introducing a second confidence threshold.
2. One shared Python predicate supplies both queue presentation and server enforcement. Template-only disabling is insufficient because a crafted POST could still submit a risky proposal ID.
3. Safe proposals on the current page are checked by default. The uploader still sees the candidates, can uncheck any item, and must confirm the final count in a browser dialog before submitting.
4. Warning-bearing and incomplete proposals remain in the pending queue but show an individual-review action instead of a bulk checkbox.
5. The production parser remains pypdf. Docling is not installed, imported, configured, or conditionally invoked by this change.

## Risks / Trade-offs

- [A complete proposal can still contain a plausible but wrong value] → Keep explicit uploader confirmation, show title/authors/journal/year/DOI in the queue, and preserve individual evidence review.
- [The safety rule may be conservative] → Users can still confirm a blocked proposal from the editable detail page; no proposal is discarded.
- [Client-side default selection can surprise users] → Label the behavior, display the selected count, allow unchecking, and retain a final confirmation dialog stating that publication is unchanged.
- [Queue and endpoint logic could drift] → Use one predicate and cover it with queue and crafted-POST tests.
