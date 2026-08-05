# Resume Workflow Specification — Program Intake Sprint 004 (2026-08-05)

Phase 4 requirement: after human confirmation, the pipeline must automatically continue from the correct
phase — no repeated successful steps, no duplicate document/case/vectors, resume must be idempotent.

## 1. Design principle: reuse the existing gate, don't build a new one

Before this sprint, `finalize_intake_job` had exactly one precondition check: `job["status"] != "completed"`
→ 409. This sprint's entire resume mechanism is built by making this ALREADY-EXISTING check mean something
new, not by adding new blocking logic:

- **Stop**: `IntakeWorker._process()` now reports whether review is needed; `_tick()` sets
  `intake_jobs.status='awaiting_review'` instead of `'completed'` when true. Finalize's pre-existing status
  check now naturally rejects these jobs — zero new lines of blocking logic in `finalize_intake_job` itself.
- **Resume**: `resolve_review()` advances the job's status from `awaiting_review` back to `completed`. The
  *exact same* finalize call, retried by the lawyer (or the frontend automatically, per this sprint's UI fix),
  now passes the *exact same* precondition check it always had.

This is deliberate: a new, separate "resume" code path would be a second way to reach the same outcome finalize
already produces — exactly the kind of duplicate business logic this sprint's own success criteria forbid.

## 2. What "resume" concretely does NOT repeat

| Step | Repeated on resume? | Why not |
|---|---|---|
| Decrypt + OCR | No | `intake_documents`/`extracted_entities` rows already exist from the original `_process()` run; finalize's `get_job_result()` reads them, never re-triggers extraction |
| Classification | No | Same — `intake_documents.document_type`/`classification_confidence` already persisted |
| Entity extraction | No | Same — `extracted_entities` rows already persisted, including any lawyer corrections made via `/entities/{id}/correct` before resolving |
| `predmet` (case) creation | No — **idempotent by construction** | `claim_intake_finalize` (Sprint 002, migration 092) already guarantees at most one case is created per job, independent of how many times finalize is called |
| Pinecone vector ingest | No — same guarantee | Ingestion only happens inside the one finalize execution that wins the atomic claim |
| `predmet_dokumenti` row | No — same guarantee | Same claim-protected execution |

**The only thing resume actually does is flip one status value and let an already-idempotent function run
(for the first time it's ever allowed to complete for this job).** This is why no new idempotency proof was
needed for the "resume" concept itself — Sprint 002 already proved finalize is safe to call multiple times;
this sprint's job was only to correctly gate *when* the first successful call is allowed to happen.

## 3. The resolve action itself — idempotency proof

`shared/intake_documents.py::resolve_review()`:
1. `resolve_review_queue_for_job()` — `UPDATE intake_review_queue SET resolved_at=... WHERE intake_job_id=?
   AND resolved_at IS NULL`. Postgres single-row-UPDATE atomicity means at most one concurrent caller's
   UPDATE actually matches a row; every other caller's WHERE clause excludes the now-already-resolved row.
   Returns `True` only for the caller that actually changed something.
2. `UPDATE intake_jobs SET status='completed' WHERE id=? AND status='awaiting_review'` — same atomicity
   argument, same pattern.

**Not wrapped in a single RPC transaction** (deliberate, matches Sprint 002 Fork B's own established
reasoning about where atomicity is actually needed): if step 1 succeeds and step 2 fails, the job remains
correctly `awaiting_review` — finalize's gate still (correctly) blocks it, and a retried `resolve_review()`
call safely re-attempts step 2 (step 1 is now a no-op, having already succeeded). **Fail-closed, not
fail-open** — a partial failure here never allows finalize to proceed prematurely, it only ever delays the
job remaining correctly blocked until the retry completes both steps.

## 4. Concurrency scenarios proven (Phase 6, full detail: `CONCURRENCY_VERIFICATION_REPORT.md`)

- Two users resolve the same review simultaneously → exactly one gets `review_resolved_now: true`; the other
  gets an honest `false` — no duplication, no lost decision, no error.
- Resolve called on a job that already has no outstanding review (already resolved, or never flagged at all)
  → safe no-op, not an exception.
- Resolve called after the job is already finalized → the endpoint detects `predmet_id` is already set and
  returns `already_finalized: true` without touching `resolve_review()` at all — nothing left to unblock, and
  the response says so honestly rather than claiming a generic success.
- Worker restart between `_process()` completing and `_tick()` writing the final status → covered by the
  pre-existing idempotent-retry mechanism (Sprint 001/002): if the job is somehow reclaimed, `_process()`'s
  own idempotency check re-derives whether a review exists (`existing["review"] is not None`) rather than
  blindly assuming completion — no information is lost by a restart at this boundary.

## 5. What resume does not (yet) support — deferred, business decision

"Reject and reprocess from scratch" is not implemented. Only "confirm and proceed" (resolve) exists. See
`HUMAN_REVIEW_ARCHITECTURE_REPORT.md` §3 for why this is a genuine product decision (what should rejection
concretely trigger?), not a bounded technical gap this sprint could close unilaterally.
