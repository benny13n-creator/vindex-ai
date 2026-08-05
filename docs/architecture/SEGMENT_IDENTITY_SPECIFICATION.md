# Segment Identity Specification — Program Intake Sprint 005 (2026-08-05)

Mission requirement (Phase 4): every segment must have a unique ID, parent upload ID, order, start/end page,
segmentation reason, confidence, and correlation ID — nothing may remain anonymous.

## Design synthesis

Two independent design proposals were reconciled during this sprint: one recommended extending
`intake_documents` with segment columns (reasoning: "which document" and "which segment" are the same
question once a segment is classified); the other recommended a new table with its own status/lifecycle
columns (reasoning: a segment needs a status — pending/processing/failed — *before* it is ever classified, a
genuinely different question than identity).

**Resolution**: the new table (`intake_job_segments`) owns BOTH identity fields and status/lifecycle fields.
`intake_documents` / `extracted_entities` / `intake_review_queue` need zero new columns — they already scope
correctly via `document_id`, and a segment's own `intake_documents` row is created the same way a
single-document job's row always has been (Phase 5 hand-off, unchanged). Only `intake_processing_outcomes`
(job-scoped, not document-scoped, today) genuinely needed a new nullable `segment_id` column — without it,
multiple segments' outcomes under one `intake_job_id` would collide/be ambiguous.

## `intake_job_segments` (migration `093_intake_job_segments.sql`)

| Column | Type | Identity requirement satisfied |
|---|---|---|
| `id` | UUID PK | Unique ID |
| `intake_job_id` | UUID FK → `intake_jobs(id)` | Parent upload ID |
| `segment_index` | INTEGER (unique with `intake_job_id`) | Order |
| `start_page` / `end_page` | INTEGER (inclusive, 1-based) | Start/end page |
| `segmentation_reason` | TEXT | Segmentation reason (fixed vocabulary, see Signal Specification) |
| `segmentation_confidence` | NUMERIC | Confidence |
| `segmentation_method` | TEXT, default `'deterministic_signals_v1'` | Names the one canonical engine version — never a second, competing method value |
| `boundary_signals` | JSONB | Full audit trail of which signals justified this cut |
| `status` | TEXT, CHECK `pending/processing/completed/awaiting_review/failed` | Lifecycle (Phase 6) |
| `document_id` | UUID FK → `intake_documents(id)`, nullable until classified | Links identity to the existing classification pipeline's own document row |
| `attempts` / `max_attempts` | INTEGER, default 2 | Bounded in-process retry state |
| `last_error` | TEXT | Failure diagnostics |
| `created_at` / `updated_at` | TIMESTAMPTZ | Audit |

**Correlation ID**: deliberately NOT a new stored column. Each segment mints its own correlation ID at the
point its downstream processing begins (matching the codebase's own already-established pattern of parallel
operations each keeping their own transient correlation ID) — the durable link back to the parent upload
remains the existing `intake_job_id` FK. Correlation ID answers "which single AI/audit operation is this," a
narrower and more transient question than "which document/upload does this belong to," which `intake_job_id`
and `document_id` already answer durably.

## `intake_processing_outcomes.segment_id` (new nullable column, same migration)

NULL for every outcome written before this sprint, and NULL for every single-segment job after it (identical
to before) — set only when a job segmented into 2+ documents, disambiguating multiple segments' outcomes under
one shared `intake_job_id`.

## `intake_review_queue.reason` — two new values

`segmentation_uncertain` (real-but-insufficient split evidence, mission's own conservatism mandate — see
Signal Specification §2) and `processing_failed` (a segment permanently dead-lettered after its bounded
in-process retries — see Failure Recovery Report). Both added to the existing CHECK constraint, following the
exact same fixed-vocabulary discipline Sprint 004 established for this column.

## Nothing remains anonymous — verification

- Every confirmed `Segment` the pure engine returns carries `start_page`/`end_page`/`reason`(property)/
  `confidence`(property)/`signals` (the audit trail) before it is ever persisted.
- `shared/intake_segments.py::create_segments()` persists one `intake_job_segments` row per `Segment`,
  assigning `id` and `segment_index` at insert time — verified by
  `tests/test_sprint005_segmentation_worker.py::test_two_bundled_documents_produce_two_segments_and_two_documents`.
- Every segment's own `document_id` is set the moment its classification completes
  (`mark_segment_completed`/`mark_segment_awaiting_review`), or remains NULL with `status='failed'` if it
  never completes — never a silent, unidentified gap.
