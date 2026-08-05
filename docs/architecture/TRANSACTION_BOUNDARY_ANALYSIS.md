# Transaction Boundary Analysis — Program Intake Sprint 002 (2026-08-05)

Phase 3 requirement: identify where transactions start, where they end, what isn't covered, what runs
asynchronously, where half-commit is possible. Proven, not guessed. Full narrative:
`.vindex_ai_team/decisions/2026-08-05_intake_sprint002_fork_transaction_boundaries_state_machine.md` §3.

## Where a transaction boundary genuinely exists today

**Exactly one mechanism**: a single `.rpc()` call to a `plpgsql` function is one implicit Postgres
transaction. Confirmed by reading the actual function bodies, not by trusting names or comments:

| RPC | Statements inside the one transaction |
|---|---|
| `enqueue_intake_job` | idempotency-key check + `intake_jobs` insert + `intake_audit_log` insert + `events` outbox insert (4 statements, 1 transaction) |
| `claim_intake_job` | `SELECT...FOR UPDATE SKIP LOCKED` + `UPDATE...RETURNING` (atomic by Postgres row-lock semantics) |
| `complete_intake_job` | status UPDATE + audit insert + outbox insert (3 statements, 1 transaction) |
| `fail_intake_job` | branch on dead-letter vs. retry, each branch does UPDATE + audit insert (+ outbox insert on dead-letter only) |
| **`claim_intake_finalize`** (new, migration 092, this sprint) | `SELECT...FOR UPDATE SKIP LOCKED` + `UPDATE` on `finalizing_at`, same shape as `claim_intake_job` |

Confirmed (not assumed): `supabase==2.28.3`/`postgrest==2.28.3` expose no client-held multi-statement
transaction API; PostgREST itself executes each HTTP request as its own single implicit transaction. A
repo-wide grep for `psycopg2|asyncpg|BEGIN;|\.transaction\(` found exactly one hit, an unrelated one-off
tooling script (`scripts/export_rls_policies.py`), not part of the running application.

## Where no transaction boundary exists (everything else)

Every other write across all 3 pipelines is a bare `supa.table(...).insert()/.update()/.delete()` —
independently committed the instant it returns, with zero grouping. A sequence of N such calls inside one
Python function is N independent transactions, never one. This is true for every write against
`predmet_dokumenti`, `predmet_klijenti`, `predmet_hronologija`, `klijenti`, `intake_documents`,
`extracted_entities`, `intake_review_queue`, `intake_processing_outcomes` — confirmed by direct grep across
`api.py`, `routers/smart_intake.py`, `shared/intake_worker.py`, `shared/intake_documents.py`.

**Pipeline C's finalize is the worst-case instance**: 6-8 independently-committed writes in one HTTP request
(predmet, client, deadline, document, Pinecone ingest, plus the completion marker), zero RPC usage anywhere
in that function prior to this sprint.

## What runs asynchronously (outside any request's transaction boundary entirely)

- Fire-and-forget `asyncio.create_task()` calls: `log_action` (audit), `case_context`-wrapped AI calls
  (provenance), Evidence Vault auto-classify, Genome refresh, analytics `_track_event`. None of these are
  awaited by the request that schedules them — their success or failure is invisible to the caller and, in
  several cases, to any log line at all (bare `except: pass` at the weakest call sites, e.g. Pipeline C's
  `_track_event`).
- The `IntakeWorker` background loop itself runs entirely outside any HTTP request's lifetime.
- `dispatch_pending_events()`'s Event Bus polling loop, similarly out-of-request.

## Where half-commit was possible before this sprint, and what changed

1. **Pipeline C finalize — the sprint's central finding.** Steps 1-7 of the function (predmet, client, deadline,
   document, Pinecone, 2 background task schedules) could each independently commit while the 8th step (the
   `predmet_id` completion marker) failed — leaving a fully-formed case with no idempotency protection against
   a subsequent retry re-running everything. **Fixed**: the completion marker is no longer the only guard —
   `claim_intake_finalize` now atomically reserves the right to run steps 1-7 in the first place, *before* any
   of them execute, so a concurrent second call is turned away at the door rather than allowed to duplicate
   everything and race for who "wins" the marker write at the end.
2. **`IntakeWorker._process()`'s own completion signal.** `write_processing_outcome()` (the last statement in
   both success branches) could fail silently, letting `_tick()` mark the job `completed` regardless. **Fixed**:
   `raise_on_error=True` at `_process()`'s two call sites means this failure now propagates to `_tick()`'s
   already-atomic `mark_job_failed` → retry path, extending Sprint 001's own proven half-commit-recovery
   pattern (`delete_partial_document`) to this one remaining gap.
3. **Storage-write-then-downstream-failure on both upload pipelines.** A successfully-uploaded encrypted blob
   had no compensating action if anything downstream failed (Pipeline A: 5 raise sites; Pipeline B: the
   ordinary duplicate-resubmit case). **Fixed**: both pipelines now perform a best-effort compensating delete
   of the just-uploaded blob when the surrounding operation doesn't complete — the correct pattern for a
   system with no rollback primitive: undo manually, don't rely on a transaction that doesn't exist.

## What is honestly still not covered (deferred, not silently ignored)

- **Pipeline A/C's Pinecone-ingest-then-DB-insert-failure window** (`INTAKE-005`/`INTAKE-001`) — no
  compensating Pinecone delete exists on either pipeline. A genuinely new capability (Pinecone doesn't expose
  transactional semantics with Postgres either — a cross-system compensating action would need to be built,
  not just wired up), correctly out of this sprint's bounded-fix scope.
- **The narrowed residual risk on fix #1**: if the finalize completion-marker write itself fails (distinct
  from the concurrent-race scenario the atomic claim now prevents), the claim remains valid for up to 120
  seconds (the staleness window) before a retry could re-run the function from scratch. A materially smaller
  window than before (was: unbounded, any concurrent retry, any time), not zero.

## Conclusion

The transaction boundary "as it actually exists" in this codebase is narrower than Sprint 001's own blanket
statement implied — real atomicity exists, but only inside 5 specific RPCs (4 pre-existing + 1 new this
sprint), never across sequences of bare client calls. This sprint's 4 fixes did not attempt to retrofit
transactions where none can exist (supabase-py structurally cannot provide them) — each fix instead applied
the codebase's own already-proven pattern (atomic claim-before-acting, or compensating delete-after-failing)
to the specific half-commit windows Fork A/B/C proved were real and reachable.
