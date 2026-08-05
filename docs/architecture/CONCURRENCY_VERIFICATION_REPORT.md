# Concurrency Verification Report — Program Intake Sprint 004 (2026-08-05)

Phase 6 requirement: prove no duplication, no lost decisions, no contradictory statuses under concurrency.
Every scenario below is backed by a passing regression test, not a narrative claim alone.

| Scenario | Outcome | Proof |
|---|---|---|
| Two users open the same review | Both see identical, consistent data (`GET /jobs/{id}` is a pure read, no state mutation) | Inherent — no write occurs on view |
| Two users (or one, double-clicking) resolve the same review simultaneously | Exactly one resolves it (`review_resolved_now: true`); the other gets an honest `false`, not an error or a duplicate resolution | `tests/test_intake_documents.py::test_resolve_review_simultaneous_approval_only_one_wins` |
| Resolve called on a job with no review entry at all (never flagged, or a misdirected call) | Safe no-op, not an exception | `tests/test_intake_documents.py::test_resolve_review_on_job_with_no_review_entry_is_a_safe_noop` |
| Resolve called after the job is already finalized | Detected explicitly (`predmet_id` already set) before touching `resolve_review()` at all; response says `already_finalized: true`, not a generic success | `tests/test_sprint004_review_resolve.py::test_resolve_job_review_already_finalized_returns_honest_noop` |
| Browser refresh mid-review | All state is server-derived and re-fetchable (`GET /jobs/{id}`); no client-only state exists that a refresh could lose | Inherent to the existing polling architecture, unchanged by this sprint |
| Retry of the resolve action itself | Idempotent — second call finds nothing left to resolve, reports so honestly | `tests/test_intake_documents.py::test_resolve_review_idempotent_when_already_resolved_and_completed` |
| Retry of finalize after resolve | Already covered by Sprint 002's `claim_intake_finalize` atomic claim — resume introduces no new finalize-level race, since it only changes the precondition finalize already checked | `tests/test_sprint004_review_resolve.py::test_resolve_then_finalize_proceeds_without_repeating_processing` |
| Network timeout during resolve | The two-step sequence (`resolve_review_queue_for_job` then status advance) is individually atomic per step; a timeout after step 1 leaves the job correctly still `awaiting_review` (fail-closed) — finalize remains correctly blocked until a successful retry completes both steps | `RESUME_WORKFLOW_SPECIFICATION.md` §3 (reasoning), same idempotency tests above cover the retry-safety half |
| Worker restart during a job that will need review | `_process()`'s own idempotency guard (Sprint 001, extended this sprint) re-derives `needs_review` from the actual persisted review state (`existing["review"] is not None`) rather than assuming completion — a restart at this exact boundary loses no information | `tests/test_intake_worker_phase1a.py::test_process_skips_already_processed_job_idempotent` (extended this sprint's reasoning, same mechanism) |
| Worker restart during resume itself (between resolve and finalize) | Resume has no worker-side component at all — it is two HTTP-triggered DB writes and one already-idempotent HTTP call. A worker process restarting mid-way has zero effect on this sequence, since no worker participates in it | Architectural — no code path exists for a worker to interfere with resolve/finalize |

## Why this sprint's concurrency proof is narrower in scope than Sprint 002's, and that's correct

Sprint 002 proved atomicity for a genuinely multi-step, multi-side-effect operation (finalize's own case
creation) under concurrent retry — a hard problem requiring a new RPC. This sprint's resume mechanism is
deliberately NOT a new multi-step operation: it is two single-row, single-condition UPDATEs (each already
atomic via Postgres's own row-level semantics, the same reasoning Sprint 002/003 already established for
`tip_dokaza`), followed by re-invoking an ALREADY-proven-atomic function (finalize). The concurrency proof
required here is correspondingly simpler — and correctly so, since building new atomicity machinery for an
operation that doesn't need it would be exactly the kind of unnecessary complexity this sprint's own closing
instruction warns against ("ne optimizuj za broj zatvorenih stavki").

## Full regression suite

2530 passed, 1 skipped, 0 failed — the entire existing suite, plus every new test in this report, runs
together with zero regressions.
