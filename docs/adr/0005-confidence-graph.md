# ADR-0005: Per-entity confidence, not one score per document

- Status: Accepted
- Date: 2026-07-15

## Context

A single `confidence = 0.87` per document forces a binary UX: either the
whole document is "trusted" or the whole document goes to a human. In
practice a document can be 99% confident on its case number and 51%
confident on a monetary amount at the same time — collapsing that into one
number throws away exactly the information that would let a reviewer look
at one field instead of re-reading the page.

## Decision

Every extracted entity (case number, judge, plaintiff, defendant, court,
deadline, amount, law cited) is scored independently and stored in
`extracted_entities`, each with its own `confidence` and
`extraction_method`. Routing thresholds (auto-accept ≥ 90%, review 60–89%,
below 60% treated as "insufficient evidence to guess," not "low
confidence") apply per field, not per document.

## Alternatives Considered

- **Single document-level confidence (weighted average of fields).**
  Rejected — a low-confidence amount and a low-confidence judge name are
  different review tasks; averaging them into one score hides which one
  actually needs attention.
- **No confidence scoring, binary accept/reject only.** Rejected outright —
  removes the explainability the rest of the design depends on (ADR-0014
  and the review-queue UX both assume per-field confidence exists).

## Consequences

- Review-queue UX can say "check these two fields" instead of "check this
  document" — the actual UX payoff this ADR exists to deliver.
- Every entity-producing worker (extraction, case-matching, lineage
  detection) must emit a confidence value as a first-class output, not an
  afterthought bolted on after the fact.
