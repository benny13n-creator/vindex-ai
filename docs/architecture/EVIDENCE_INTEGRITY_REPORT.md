# Evidence Integrity Report — Program Intake Sprint 006 (2026-08-05)

Mission requirement (Phase 6): one document → one Evidence record → one lineage → one audit chain. No
duplicates. No orphans.

## The invariant, made concrete and DB-enforced

`CREATE UNIQUE INDEX uq_predmet_dokumenti_source_segment ON predmet_dokumenti(source_intake_job_segment_id)
WHERE source_intake_job_segment_id IS NOT NULL` (migration 094). This is not application-code discipline —
it is a database-level guarantee: a segment can produce AT MOST ONE `predmet_dokumenti` row, ever. A retry,
a replay, or a concurrent double-call that attempted to insert a second row for the same segment fails at the
database level.

## No duplicates

- **Whole-file re-upload**: prevented at enqueue time by the existing `idempotency_key` unique index (Sprint
  002), unchanged by this sprint.
- **Same segment inserted twice within one finalize call**: prevented by the UNIQUE constraint above.
- **Same segment inserted twice across two finalize attempts** (e.g. a retried HTTP call after a transient
  network failure): `claim_intake_finalize`'s atomic claim (migration 092, Sprint 002) prevents a second
  finalize call from ever re-running the whole function body while the first is genuinely in flight, or after
  it has already fully succeeded (`intake_jobs.predmet_id` already set) — unchanged by this sprint, still the
  correct first line of defense; the new UNIQUE constraint is the second, independent, DB-level line of
  defense for the specific per-document insert itself.

## No orphans

An "orphan" here means: a segment whose `intake_job_segments.assimilation_status = 'resolved'` but which has
no corresponding `predmet_dokumenti` row (a data-integrity contradiction — "resolved" should only ever be set
AFTER the insert genuinely succeeds).

**Verification**: `shared/intake_segments.py::mark_assimilation_resolved(segment_id)` is called in
`finalize_intake_job`'s per-document loop ONLY after `dok_ins.data` confirms the insert actually returned a
row — never optimistically before. The reconciliation query this invariant makes possible: segments where
`assimilation_status = 'resolved'` but no `predmet_dokumenti` row references them via
`source_intake_job_segment_id` should return zero rows, always; this is the concrete, checkable form of "no
orphans" the mission asks for.

**The symmetric failure mode, also checked**: a `predmet` created/attached but ending up with ZERO of its
source documents linked (the false-success bug this sprint's own Phase 1 audit found and fixed — see
`CANONICAL_CASE_ASSIMILATION_ARCHITECTURE_REPORT.md` finding #7). The finalize response now honestly reports
`dokumenata_povezano` (count actually linked) alongside `dokumenata_ukupno` (count that should have been), and
a total failure (0 of N) is logged at ERROR level, not silently returned as an ordinary non-fatal warning.

## Per-document failure isolation (Phase 5, cross-referenced here for completeness)

Each document in the per-document loop gets its own `try`/`except` — one document's `predmet_dokumenti`
insert throwing does not abort the loop, and does not leave that document's `intake_job_segments` row
ambiguous: it is explicitly marked `assimilation_status='failed'` via `mark_assimilation_failed()`, and the
sibling document(s) still get their own chance to be correctly resolved. Proven directly by
`tests/test_sprint006_finalize_assimilation.py::test_one_document_insert_failure_does_not_lose_or_block_sibling`.

## What is NOT covered by "no duplicates," named honestly

Cross-upload duplicate detection (the SAME physical document re-scanned into two DIFFERENT overall uploads,
producing two independent segments with no shared identity) is not detected by any mechanism built this
sprint — it would require a per-segment content hash, which does not exist yet (see
`OWNERSHIP_RESOLUTION_SPECIFICATION.md` §4, and the Architectural Debt Register entry for this gap).
