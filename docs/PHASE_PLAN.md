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

- [x] Persistent Event Bus (outbox pattern) — `services/event_bus.py::dispatch_pending_events`, migration 073 (`events` table) — [ADR-0001](adr/0001-async-ingest-job-queue.md), design review §7/§26.4
- [x] Persistent Job Queue (`intake_jobs`, Postgres-backed, `claim_intake_job` RPC) — `shared/intake_queue.py` — [ADR-0002](adr/0002-postgres-job-queue.md)
- [x] Upload transaction — `enqueue_intake_job` RPC (job + audit + outbox event atomic, migration 073)
- [x] Retry mechanism (exponential backoff, dead-letter at max_attempts) — `shared/intake_queue.py::mark_job_failed`
- [x] Audit log (`intake_audit_log`, append-only) — `shared/intake_queue.py::write_audit`
- [ ] Wire a periodic worker to call `dispatch_pending_events()` (cron/background task — not yet scheduled anywhere)
- [ ] `POST /api/intake/documents` endpoint wiring `enqueue_job()` to real file storage (currently: queue/outbox plumbing exists, no HTTP endpoint calls it yet)

Migration `073_intake_foundations.sql` written — **not yet run** (user runs
migrations himself, per standing project rule). 15 new tests, full suite
green. See commit for this phase for exact file list.

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
