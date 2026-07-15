# Smart Intake Engine — Implementation Phase Plan

Tracking doc for implementation against the frozen architecture in
`docs/adr/`. See `docs/adr/README.md` for the decision index and
`docs/ENGINEERING_PRINCIPLES.md` for standing rules.

**Rule for this entire implementation:** if an ADR exists, implementation
follows it. A shortcut ("skip the review queue here," "write straight to
the table for just this endpoint") is not a local decision — it's either
disallowed, or it means the ADR itself needs a formal amendment first.
"Small deviations" during implementation are exactly how the durability and
review-queue guarantees this whole design exists to provide quietly stop
being true.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Foundations
**Goal: make upload reliable and durable. No AI behavior changes yet.**

- [x] Persistent Event Bus (outbox pattern) — `services/event_bus.py::dispatch_pending_events` + `DispatchLoop`, migration 073 (`events` table) — [ADR-0001](adr/0001-async-ingest-job-queue.md), design review §7/§26.4
- [x] Persistent Job Queue (`intake_jobs`, Postgres-backed, `claim_intake_job` RPC) — `shared/intake_queue.py` — [ADR-0002](adr/0002-postgres-job-queue.md)
- [x] Upload transaction — `enqueue_intake_job` RPC (job + audit + outbox event atomic, migration 073)
- [x] Retry mechanism (exponential backoff, dead-letter at max_attempts) — `shared/intake_queue.py::mark_job_failed` + `fail_intake_job` RPC (atomic)
- [x] Audit log (`intake_audit_log`, append-only) — `shared/intake_queue.py::write_audit`
- [x] Worker scheduling — `shared/intake_worker.py::IntakeWorker` (idempotent claim→process→complete/fail, graceful shutdown, periodic reaping of stale claimed jobs, heartbeat)
- [x] Periodic dispatch of outbox events — `services/event_bus.py::DispatchLoop`
- [x] Upload endpoint — `POST /api/smart-intake/documents` (`routers/smart_intake.py`) — **note:** originally specced as `/api/intake/documents` (ADR-0001); renamed after discovering `/api/intake/*` already belongs to the live CRM Intake Wizard (`routers/intake.py`, unrelated feature, same word). Formally amended in ADR-0001, not silently changed.
- [x] Operational observability — `GET /api/smart-intake/admin/health` (queue depth, oldest pending, failed/retrying, outbox backlog, dispatch latency, worker heartbeats) — `intake_queue_metrics` / `events_outbox_metrics` views
- [x] Restart-safety — `claimed_at` + `reap_stale_jobs()`: a job stuck in an in-progress status past a staleness threshold is requeued through the normal retry/dead-letter path, never permanently stuck
- [x] End-to-end restart-safety test (simulated crash mid-processing, confirm no lost events / effectively-once) — `tests/test_intake_e2e_restart.py`, drives the real production code (not a reimplementation) against an in-memory fake of the Postgres RPC surface. Honest limitation documented in the test's own docstring: this proves the orchestration logic, not the real Postgres row-locking guarantees — those need the live migration run to verify for real.

**Phase 0 — Definition of Done: met, verified live against production Supabase (2026-07-15).**

Migration 073 ran into three real bugs on first execution — found and
fixed via founder-run diagnostics, not guessed:
1. `CREATE POLICY` has no `IF NOT EXISTS` in Postgres (unlike `CREATE
   TABLE`) — any re-run of the file aborted on the first policy statement.
   Fixed with `DROP POLICY IF EXISTS` before each of the 5 policies.
2. `CREATE TABLE IF NOT EXISTS` doesn't add columns to a table that already
   exists — `intake_jobs` was created before `claimed_at` existed in the
   file, so it was silently missing. Fixed with an explicit `ALTER TABLE
   ADD COLUMN IF NOT EXISTS` (same pattern as migration 072).
3. `claim_intake_job` was the only one of 4 RPCs missing `SECURITY
   DEFINER` — its `UPDATE ... RETURNING` silently returned empty under RLS
   even though the write succeeded, making a successful claim look like
   "no job found." Found live: 11 test jobs stuck in `preprocessing`.

**Live verification performed** (direct against production Supabase, real
RPCs, real `IntakeWorker`, real `dispatch_pending_events` — not mocks):
- 5 consecutive enqueue→claim→complete cycles: 5/5 correct
- Full acceptance sequence (upload → 202-equivalent in 327ms → queue depth
  → autonomous worker claim → complete → audit trail → outbox → dispatch →
  heartbeat → queue depth back to 0): 10/10 steps passed
- Chaos/restart-safety test (upload → claim → simulated crash → reap →
  reclaim by a second worker → complete → dispatch): 11/11 checks passed,
  exactly one `DocumentJobCompleted` event despite the crash, zero events
  left undispatched, complete audit trail (`job_created` → `job_retry_
  scheduled` → `job_completed`)
- Performance baseline: 20 sequential uploads, enqueue latency 88–287ms
  (avg 110ms). Throughput measurement was inconclusive due to a counting
  artifact in the benchmark script itself, not re-run — noted honestly
  rather than reported with false confidence. Worth redoing properly
  before Phase 1A if throughput becomes a real question.
- Housekeeping: found and killed 3 orphaned local dev server processes
  left running from earlier in the session — one of them was actively
  racing the verification scripts for the same jobs, which is what
  originally made the SECURITY DEFINER bug look non-deterministic.

Migration `073_intake_foundations.sql` **run successfully** against
production Supabase. Includes the `intake-dokumenti` storage bucket
insert. See commits for this phase for exact file list and bug fixes.

**Not yet verified:** the actual HTTP layer (`POST /api/smart-intake/
documents` with real multipart upload + encryption + Storage write, `GET
/api/smart-intake/admin/health` with real founder auth) — all live testing
above went through the service layer directly (`shared/intake_queue.py`,
`shared/intake_worker.py`, `services/event_bus.py`), not through FastAPI
+ auth. Worth a real HTTP-level smoke test before Phase 1A ships.

## Phase 1 — Smart Intake
**Goal: documents become classified, matched, reviewable.**

- [ ] OCR pipeline (extend existing extractor — deskew/perspective/denoise)
- [ ] Metadata extraction — [ADR-0003](adr/0003-hybrid-extraction.md) (regex-first, LLM-fallback)
- [ ] Classification (12-type taxonomy, hybrid heuristic+LLM)
- [ ] Confidence Graph — [ADR-0005](adr/0005-confidence-graph.md)
- [ ] Review Queue (office-scoped) — design review §26.9
- [ ] Folders as views — [ADR-0004](adr/0004-folders-as-views.md)

## Phase 2 — Living Case
**Goal: case state becomes visible and historical.**

- [ ] `case_dimension_type` lookup table — [ADR-0011](adr/0011-case-dimension-type-as-entity.md)
- [ ] `CaseDimensionChanged` event + `case_dimension_history` — [ADR-0009](adr/0009-configuration-vs-knowledge-state.md), [ADR-0010](adr/0010-case-dimension-changed-envelope.md)
- [ ] Health / Confidence / Completeness projections — [ADR-0015](adr/0015-target-state-scoped.md) (target-state for these two first)
- [ ] State Diff Engine — [ADR-0012](adr/0012-state-diff-debounce.md)
- [ ] Case Evolution UI — [ADR-0013](adr/0013-case-evolution-no-analytics-table.md)

## Phase 3 — Intelligence
**Goal: the harder, higher-payoff signals.**

- [ ] Semantic Deduplication — [ADR-0008](adr/0008-semantic-dedup-entity-overlap.md)
- [ ] Document Lineage — [ADR-0014](adr/0014-document-lineage-confidence-gated.md)
- [ ] Case Memory — [ADR-0006](adr/0006-case-memory-deterministic.md)

## Phase 4 — Automation
**Goal: intake reaches into the rest of the platform.**

- [ ] Reactive fan-out wiring: Case DNA, Health Index, Zastarelost Guardian, Strategija, Profitabilnost AI, Client Twin, Knowledge Graph each subscribe to `DocumentIngested` — design review §7, §26.11
- [ ] Deadline propagation (auto-reminder)
- [ ] Client Twin update trigger
- [ ] Profitability update trigger

## Phase 5 — Optimization

- [ ] Mobile capture surface
- [ ] Windows folder watcher / email adapter
- [ ] Only after real usage data exists: revisit Intent Engine — [ADR-0016](adr/0016-intent-engine-deferred.md) (deferred, not scheduled)

---

*Deferred, not scoped into any phase:* Versioned Facts —
[ADR-0007](adr/0007-versioned-facts-deferred.md).

*Every new AI-driven action added anywhere in this plan gets classified
against [ADR-0017](adr/0017-automation-safety-levels.md) before it ships.*
