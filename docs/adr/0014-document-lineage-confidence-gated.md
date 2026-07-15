# ADR-0014: Document Lineage edges are confidence-scored and reviewable, never auto-asserted

- Status: Accepted
- Date: 2026-07-15

## Context

Document Lineage — Lawsuit → Response → Reply → Judgment → Appeal as a
graph of procedural relationships, not just chronological order — is
genuinely differentiating (few competitors model this at all). But a wrong
edge is not a cosmetic error: a false "this appeal responds to that
judgment" can feed a strategy module a false premise about case history,
which is a materially worse failure mode than a misfiled document.

## Decision

Lineage edges (`document_lineage`: `from_document_id`, `to_document_id`,
`relationship`, `confidence`, `detection_method`) are detected two ways —
explicit reference (a document citing the specific decision number it
appeals; high confidence, near-deterministic) or LLM inference for implicit
cases (lower confidence). Edges below the same confidence threshold used
elsewhere in this design (ADR-0005's 60/90 split) are offered as
suggestions in the review queue, never silently asserted into the graph.

## Alternatives Considered

- **Auto-assert all detected edges, high or low confidence.** Rejected —
  the downstream blast radius (a strategy or health-score module reasoning
  over a false relationship) is worse than the cost of a review step, and
  worse than the equivalent risk already accepted for case-matching, which
  gets the review treatment for the same reason.
- **Only build lineage from explicit references, skip LLM inference
  entirely.** Rejected — would miss the more valuable implicit cases (a
  reply that clearly responds to an earlier filing without quoting its
  reference number), leaving the feature's most useful cases unhandled.

## Consequences

- Reuses the review-queue and confidence-explainability mechanisms already
  built for case-matching and entity extraction — no new UX pattern.
- Document Lineage is sequenced late in the roadmap deliberately: detection
  quality depends on a corpus of already-classified, already-matched
  documents to detect relationships against, which only exists after
  earlier phases have shipped.
