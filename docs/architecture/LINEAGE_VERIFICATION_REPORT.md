# Lineage Verification Report — Program Intake Sprint 006 (2026-08-05)

Mission requirement (Phase 4): for every document, it must be possible to reconstruct: the original upload,
the segment, the classification, the case-ownership decision, the review (if any), and the final placement in
the case. Nothing may be lost.

## The one new lineage primitive

`predmet_dokumenti.source_intake_job_segment_id` (migration `094_case_assimilation.sql`) — a single nullable
FK to `intake_job_segments.id`. Since `intake_job_segments` (Sprint 005) already carries `intake_job_id`,
`document_id`, and full classification/boundary metadata, this one column makes the entire chain
reconstructable via a single JOIN:

```
predmet_dokumenti
  → source_intake_job_segment_id → intake_job_segments
      → intake_job_id            → intake_jobs (original upload: storage_path, uploaded_by, created_at)
      → document_id              → intake_documents (classification: document_type, confidence)
                                  → intake_review_queue (review, if any: reason, low_confidence_fields, resolved_at)
      → boundary_signals, segmentation_reason, segmentation_confidence (segment identity, Sprint 005)
```

This closes Sprint 001's long-open `INTAKE-003` gap ("no FK exists from `predmet_dokumenti` back to
`intake_jobs`") for every job segmented by Sprint 005 — no new lineage table was needed; the existing
identity model already carried everything, it just needed one link back from the case-file side.

## Deliberate scope boundary: single-document jobs

`source_intake_job_segment_id` is NULL for every document created before this migration, and NULL for every
single-document job after it — because Sprint 005's own invariant means no `intake_job_segments` row exists
at all for those jobs (a job that stays one whole document writes zero segment rows, by design). This is a
**structural absence, not a lost lineage**: a single-document job's chain is still fully reconstructable via
the existing, unchanged `intake_jobs.id` ↔ `intake_documents.intake_job_id` link — the new FK only adds value
for the specific case Sprint 005 introduced (2+ documents per job), and correctly stays NULL where it doesn't
apply, verified directly by `tests/test_sprint006_finalize_assimilation.py::test_single_document_job_has_no_lineage_fk_by_design`.

## Verification, per document, at assimilation time

`shared/intake_segments.py::get_segment_for_document(document_id)` is the one lookup finalize performs per
document — returning the owning segment's row (including `start_page`/`end_page`, used to slice that
document's own text out of the shared underlying file) or `None` for a single-document job. Proven correct
per-document (not shared/collided across documents in the same job) by
`tests/test_sprint006_finalize_assimilation.py::test_lineage_fk_set_from_matching_segment_per_document`
— two documents in one finalize call each get their OWN segment's id, never the sibling's.

## Provenance continuity

Every successfully-registered document now runs inside `shared/ai_provenance.py::case_context(predmet_id=...,
document_id=..., module_name="smart_intake", operation_name="finalize_document_assimilation")` — the same
correlation-ID-inheriting primitive Missions Atlas/Ledger/Migration already proved and standardized, reused
here rather than a parallel mechanism. Immediately followed by `shared/audit_immutable.py::log_action(
"document_assimilated", ...)` — a genuinely new call site (Phase 1 audit finding: finalize previously had
zero audit calls for document-into-case registration), using the existing, proven, tamper-evident audit
primitive. `"document_assimilated"` was added to `AUDITABLE_ACTIONS` (the fixed, closed vocabulary this
codebase requires for every audited action) as part of this sprint.

## What is NOT reconstructable yet, named honestly

- **Segment-to-segment lineage across two DIFFERENT overall uploads** (e.g. a punomoćje scanned once, then
  re-scanned into a different bundle later) has no shared identity today — each upload's segments are only
  linked within their own `intake_job_id`. Closing this needs a per-segment content hash, not yet built (see
  `OWNERSHIP_RESOLUTION_SPECIFICATION.md` §4 and the Architectural Debt Register).
- **Ownership Resolution's own decision reasoning** (which signal fired, what candidates were considered) is
  captured in the `document_assimilated` audit entry's metadata for the SUCCESSFUL path, but a
  `review_required`/blocked finalize call does not yet write its own audit row (it returns an HTTP error
  instead) — a human retry with an explicit `predmet_id` is itself unaudited as a distinct decision point.
  Named as a bounded, deferred item, not silently missing.
