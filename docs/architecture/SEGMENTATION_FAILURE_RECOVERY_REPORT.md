# Segmentation Failure Recovery Report — Program Intake Sprint 005 (2026-08-05)

Mission requirement (Phase 6): if segment 3 fails, segments 1, 2, 4, and 5 must not be lost. Every segment
must have its own lifecycle.

## The load-bearing fix

`shared/intake_worker.py::_process()`'s pre-Sprint-005 code had exactly ONE `try`/`except` wrapping the
entire classify→extract→persist stretch, for the single document a job was always assumed to contain. For
genuine per-segment failure isolation, this had to move INSIDE a per-segment loop — `_process_segments()`'s
`for idx, (seg, row) in enumerate(zip(segments, segment_rows)):` loop wraps each segment's own
classify/extract/persist attempt in its own `try`/`except`, so one segment's exception cannot abort processing
of its siblings in the same run. Proven directly by
`tests/test_sprint005_segmentation_worker.py::test_one_segment_permanently_failing_does_not_lose_or_block_its_sibling`:
segment B fails every attempt; segment A is still fully classified, persisted, and marked completed.

## Bounded scope decision: in-process retry, not a cross-run backoff system

A full cross-run claim/backoff RPC (mirroring `claim_intake_job`'s `SELECT ... FOR UPDATE SKIP LOCKED` +
exponential-backoff `next_retry_at` scheduling) is genuinely new architecture beyond this sprint's bounded
scope — recorded as a deferred item in the Architectural Debt Register, not silently skipped.

Instead: each segment gets `max_attempts` (default 2) **immediate, in-process** retry attempts within the
SAME worker tick — no sleep/backoff needed, since the whole point of per-segment isolation is that a slow
cross-run retry for one segment must never delay or block its already-processed siblings.
`shared/intake_segments.py::mark_segment_failed()` records each attempt and returns whether this was the
final one (dead-lettered, `status='failed'`) — the caller uses this to decide "retry the same segment now" vs.
"move on to the next segment."

**Orphan-document guard** (a defect the codebase already fixed once for the single-document path, and which
this sprint's own retry loop had to guard against making again): if `create_document()`/`insert_entities()`
succeed but a LATER step in the same attempt (review-queue write, `write_processing_outcome`) throws, an
immediate in-process retry must not leave that partial document behind AND create a second one on the next
attempt. `_process_segments()`'s except handler calls the existing `intake_documents.delete_partial_document()`
before retrying whenever a `document_id` was already created in the failed attempt — the exact same cleanup
primitive Program Intake Sprint 001 built for the single-document case, reused here rather than reinvented.

## Job-level status derivation

A segmented job's overall `needs_review` signal (which `_tick()` uses to choose `mark_job_completed()` vs.
`mark_job_awaiting_review()`) is derived, not independently decided: **any** segment ending in
`awaiting_review` or permanently `failed` (dead-lettered) means the job as a whole routes to
`awaiting_review` — a lawyer opens review and sees which specific document(s) need attention (via the
`processing_failed` / `segmentation_uncertain` / existing confidence-based reasons), the rest already
resolved.

**Deliberate, bounded simplification, named not hidden**: a distinct `partially_failed` job status (M-1-of-M
segments completed) was considered and NOT built this sprint — it collapses into the existing
`awaiting_review` status instead, so zero changes were needed to `intake_jobs`'s CHECK constraint, `_tick()`'s
dispatch logic, or the `claim`/`complete`/`fail` RPCs. Whether `finalize_intake_job` should ever be allowed to
create a case from a job where one segment never resolved is a genuine founder product decision (mirroring
Sprint 004's own `INTAKE-012` precedent for "reject") — recorded in the Architectural Debt Register, not
guessed at. Until that decision is made, `finalize_intake_job`'s existing `status != 'completed'` gate
naturally blocks any job that is not fully resolved, with zero new blocking code — the same trick Sprint 004
used once for `awaiting_review` itself.

## Resume (crash mid-processing, worker restarts)

`_process()`'s idempotency check now looks up `intake_job_segments` FIRST, via a plain list query (never
`.maybe_single()` — a segmented job can have 2+ `intake_documents` rows sharing one `intake_job_id`, and
`.maybe_single()`'s own ambiguity guard would raise on 2+ rows if the old single-document check ran first on a
resumed segmented job — this itself was a real gap found and fixed during this sprint's own implementation,
not a hypothetical).

If segment rows already exist for a job, `_process()` re-downloads and re-segments (segmentation is a pure,
deterministic function of the same bytes, so this reproduces the identical segments in the identical order)
and reconciles against the ALREADY-PERSISTED rows by position — `completed`/`awaiting_review`/`failed`
segments are never reprocessed or duplicated; only `pending`/`processing` segments (crashed mid-flight) are
retried, continuing from their own recorded `attempts` count. Proven directly by
`tests/test_sprint005_segmentation_worker.py::test_resume_skips_already_completed_segment_only_processes_pending_one`.

## Success criteria verification

- "Segment 3 failing must not lose segments 1/2/4/5" — proven (partial-failure test above).
- "Every segment has its own lifecycle" — `intake_job_segments.status` is per-row, independently
  transitioned, never a shared/aggregate field.
- "Segmentation must be partially fault-tolerant" — proven; a permanently-failed segment dead-letters without
  aborting the job or its siblings, and the job still reaches a terminal, human-actionable state
  (`awaiting_review`), never stuck.
