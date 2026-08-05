# Retry Reliability Report — Program Intake Sprint 007 (2026-08-05)

Mission requirement (Debt 2): if processing stops at segment 7 of 12, a retry must resume from segment 7, not
from the start. No new lineage, audit, provenance, or case may be created on retry. Retry must be fully
idempotent.

## The two interruption shapes, and why both needed a fix

**Hard crash** — the process dies (or the request times out) after creating case-file documents but BEFORE
`finalize_intake_job`'s own durable completion marker is written. This was already partially guarded by
Sprint 002's `claim_intake_finalize` (atomic claim, `predmet_id IS NULL` gate) — but the claim mechanism alone
doesn't prevent the FUNCTION BODY, once re-claimed, from running Ownership Resolution fresh and creating a
**second** predmet.

**Soft partial failure** — the function completes without crashing (no exception escapes), but one or more
documents genuinely failed to link (a transient DB error survived all fallback insert variants). Before this
sprint, `intake_jobs.predmet_id` was still written unconditionally at the end, and the top-of-function
idempotency check (`if job.get("predmet_id"): return already_finalized`) treated ANY set `predmet_id` as
"permanently done" — meaning this job could **never** be retried again, even though it genuinely has unlinked
documents. This is exactly Sprint 006's own deferred `INTAKE-019`.

## The fix: two new signals, one for each shape

1. **`intake_jobs.assimilation_complete`** (migration 095) — set to `true` ONLY when
   `doc_linked_count == len(documents)` at the end of the per-document loop. `claim_intake_finalize`'s WHERE
   clause changed from `predmet_id IS NULL` to `assimilation_complete = false`, so BOTH interruption shapes
   remain reclaimable: a hard crash (predmet_id never written, assimilation_complete still its default `false`)
   and a soft partial failure (predmet_id written, but assimilation_complete correctly still `false`).
2. **`predmet_dokumenti.source_intake_job_id`** (migration 095, generalizing Sprint 006's segment-only
   `source_intake_job_segment_id` to every document) — the recovery lookup `finalize_intake_job` performs
   immediately after a successful claim: does any document already exist for this job? If so, its `predmet_id`
   is reused directly — Ownership Resolution, predmet creation, client-linking, and the deadline/conflict-check
   steps are all skipped entirely on a resume, since they already ran (or were attempted) on the crashed
   attempt. Only the per-document Evidence Registration loop re-runs, and it is idempotent per document via
   the content-hash check (`DUPLICATE_DETECTION_REPORT.md`).

## Why client-linking/deadline/conflict-check are skipped on resume, not re-run

These three steps are best-effort and have no per-item idempotency guard of their own (the conflict-check's
`proactive_alerts` insert in particular has no dedup at all — re-running it on every resume would create a
duplicate alert every time). Skipping them on resume is a deliberate, bounded choice: the core mission
guarantee (one document, one case, one lineage chain, one audit/provenance record) is about **documents**, not
about these secondary, single-shot side effects. This is recorded as a named scope boundary, not a silent gap
(see Architectural Debt Register).

## "No new lineage/audit/provenance on retry" — how this is actually true, not just claimed

Every already-linked document is detected via the content-hash check (`DUPLICATE_DETECTION_REPORT.md`) BEFORE
the code path that writes lineage (`source_intake_job_segment_id`/`source_intake_job_id`), calls
`log_action("document_assimilated", ...)`, or opens a `case_context()` provenance scope. The idempotent-skip
branch returns early, by construction, before any of those calls — this is not a separate "don't audit twice"
check bolted on afterward; it is architecturally impossible to reach the audit/provenance code for a document
that already has a row, because the function returns from that iteration first.

## Required test scenarios and how each is proven

| Mission scenario (Serbian) | Test | What it proves |
|---|---|---|
| Crash | `test_crash_recovery_reuses_existing_predmet_not_a_new_one` | `intake_jobs.predmet_id` still `None`, but a document from this job already exists → recovers the SAME predmet_id, zero new `predmeti` inserts |
| Restart / replay | Same test, plus `test_soft_partial_failure_job_is_not_treated_as_already_finalized` | A restarted worker/retried HTTP call reaches the identical, deterministic outcome regardless of how many times it's attempted |
| Partial retry | `test_partial_retry_resumes_only_the_unresolved_segment` | Each segment is independently resumable; an already-linked segment is skipped, an unlinked one is processed, regardless of position in the sequence |
| Duplicate retry | `test_same_content_after_retry_isti_sadrzaj_posle_retry` (Duplicate Detection Report) | A retry that re-attempts an already-succeeded segment is a no-op, not a duplicate |
| Interrupted finalize | `test_assimilation_complete_only_set_when_all_documents_linked` | The completion marker honestly reflects reality — never optimistically `true` for a partial result |
| (Regression guard) | `test_fully_complete_job_still_takes_the_fast_exit_path` | A genuinely fully-done job still fast-exits — this sprint narrows the fast-exit condition, it does not remove the optimization for the common, fully-successful case |

## Deliberately not built this sprint

A dead-lettered/permanently-failed document (one that fails every fallback insert variant across multiple
retry attempts) has no automatic backoff/retry-count ceiling of its own at the finalize layer — a lawyer can
retry finalize indefinitely, and each retry cheaply re-attempts only the unresolved documents (via the
content-hash check), but there is no cross-run exponential backoff or dead-letter marking specific to
finalize's own document loop (Sprint 005 has this for the classification stage; Sprint 007 does not add an
equivalent for the assimilation stage). Given finalize is a lawyer-initiated action (not an automatic
background retry loop), this is judged a reasonable, bounded scope boundary rather than a gap — a human is
always the one deciding whether to retry, and each retry is cheap and safe.
