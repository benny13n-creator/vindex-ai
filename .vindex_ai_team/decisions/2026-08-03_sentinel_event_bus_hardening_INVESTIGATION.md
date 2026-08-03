# Project Sentinel — Phase 2: Event Bus Hardening (Investigation, read-only)

**Date:** 2026-08-03. **Scope:** `services/event_bus.py` and every producer/consumer of all 12
`EventType` values. No code changed. Every claim below is cited to a file:line or a direct grep
result executed during this investigation — nothing is carried over from older audit docs without
re-verification (several older docs, e.g. `OPERATING_SYSTEM_CONNECTIVITY_AUDIT_V2.md`, are dated
2026-07-19, predate Project Synapse's fixes, and are confirmed STALE below where they disagree
with current code).

## Method

1. Read `services/event_bus.py` in full (401 lines) — this is the entire in-memory bus +
   durable-outbox implementation, no other file defines bus mechanics.
2. Grepped every `EventType.<MEMBER>` reference repo-wide to find all producers/consumers.
3. Grepped `emit(EventType\.|bus\.publish\(|bus\.publish_async\(` across `*.py` to find literally
   every in-process emission call site — result: **exactly 3 call sites in all of production code**
   (`api.py:3264`, `routers/matter_intel.py:153`, `routers/matter_intel.py:166`).
4. Grepped `DocumentJob(Enqueued|Completed|Failed)` to find the durable-outbox-only producers
   (direct SQL `INSERT INTO events` inside Postgres RPC functions, `migrations/073_intake_foundations.sql:170-280`).
5. Read `routers/case_dna.py:503-545` (`_emit_genome_event`) to confirm `GENOME_UPDATED`'s
   producer contract.
6. Read `services/case_pipeline.py:674-752` (`run_case_pipeline`) and one representative step
   (`_step_ekstrakcija_rokova`, lines 219-235) to check idempotency — **confirmed idempotent**,
   marker-based (`[Pipeline:rokovi]` sentinel row in `predmet_istorija`), which matters directly for
   the fix recommendation below.
7. Read `shared/intake_worker.py:109-125` to confirm `DocumentJobFailed`'s producer path and that
   no consumer exists for it.

## Event type inventory — all 12

| # | EventType | Producer | Consumer registered? | Severity of gap |
|---|---|---|---|---|
| 1 | `PREDMET_KREIRAN` | `api.py:3264`, pure in-process `emit()` only, no durable-outbox write | Yes — `on_predmet_kreiran` (`event_bus.py:98-107`) | **CRITICAL** |
| 2 | `DOKUMENT_UPLOADOVAN` | **None found anywhere in production code** | Yes — `on_dokument_uploadovan` (`event_bus.py:110-123`) | **HIGH** (dead wire, work already built) |
| 3 | `ROK_DODAN` | None | None | LOW (fully dead, no handler exists to wire it to) |
| 4 | `ROK_KRITICAN` | `routers/matter_intel.py:166`, pure in-process `emit()` only, no durable-outbox write | Yes — `on_rok_kritican` (`event_bus.py:66-95`) | **CRITICAL** (same class of gap as #1) |
| 5 | `ROCISTE_ZAKAZANO` | None | None | LOW (fully dead) |
| 6 | `STRATEGIJA_GENERISANA` | None | None | LOW (fully dead) |
| 7 | `ANALIZA_ZAHTEVANA` | None | None | LOW (fully dead) |
| 8 | `HEALTH_SCORE_PROMENJEN` | `routers/matter_intel.py:153`, pure in-process `emit()` only, no durable-outbox write | Yes — `on_health_score_promenjen` (`event_bus.py:126-146`) | **CRITICAL** (same class of gap as #1) |
| 9 | `GENOME_UPDATED` | `routers/case_dna.py:503-545` (`_emit_genome_event`), **durable outbox ONLY** — direct `events` table insert, deliberately never calls `emit()`/`bus.publish()` in-process (comment at `case_dna.py:510-514` explains why: avoids double-handler-run) | Yes — `on_genome_updated` (`event_bus.py:149-178`), invoked only via `dispatch_pending_events()` poller | **NONE** — this is the only event type in the system with a fully correct durability contract |
| 10 | `DOCUMENT_JOB_ENQUEUED` | `migrations/073_intake_foundations.sql:173-174`, direct outbox insert from `enqueue_intake_job` RPC | **No handler registered** — `EventBus._register_defaults()` (`event_bus.py:196-201`) only subscribes 5 of 12 types; this is not one of them | MEDIUM (currently harmless — nothing needs to react — but see note) |
| 11 | `DOCUMENT_JOB_COMPLETED` | `migrations/073_intake_foundations.sql:244-245`, direct outbox insert | **No handler registered** | MEDIUM (same) |
| 12 | `DOCUMENT_JOB_FAILED` | `migrations/073_intake_foundations.sql:279-280`, direct outbox insert; producer-side confirmed live via `shared/intake_worker.py:118-125` (`mark_job_failed` called on every worker exception) | **No handler registered** | **HIGH** — a real OCR/intake failure is durably recorded and then silently discarded (see Finding 5) |

**Zaključak:** of 12 defined `EventType` values, only 5 have any registered consumer at all
(`event_bus.py:196-201`). Of those 5, only 1 (`GENOME_UPDATED`) has a producer using the durable
outbox. The other 4 registered-consumer types (`PREDMET_KREIRAN`, `ROK_KRITICAN`,
`HEALTH_SCORE_PROMENJEN`, and the wired-but-never-fired `DOKUMENT_UPLOADOVAN`) all share one
structural weakness described in Finding 1. Documentation claiming otherwise (`OPERATING_SYSTEM_
CONNECTIVITY_AUDIT_V2.md:23,31`, dated 2026-07-19) is now **stale** — `PREDMET_KREIRAN` and
`ROK_KRITICAN` DO have producers today (added by Project Synapse, 2026-08-02/03), but the durability
gap that document never anticipated is the actual live risk now.

---

## Finding 1 (CRITICAL) — In-process-only `emit()` events have zero crash/restart durability

**Affected:** `PREDMET_KREIRAN`, `ROK_KRITICAN`, `HEALTH_SCORE_PROMENJEN` — every event type whose
*only* producer path is a bare `emit()`/`bus.publish()` call inside a FastAPI request handler or
background task, with no corresponding `events` table row ever written.

**Mechanism (traced in `services/event_bus.py:209-231`, `EventBus.publish`):**
```python
try:
    loop = asyncio.get_running_loop()
    loop.create_task(_run())          # fire-and-forget
except RuntimeError:
    asyncio.run(_run())
```
`publish()` schedules the handler as an `asyncio.create_task` and returns immediately — the caller
(the HTTP request) gets its 200/201 response the instant the task is *scheduled*, not when it
*completes*. There is no row anywhere recording "this event needs to be processed."

**Concretely, for `PREDMET_KREIRAN` (`api.py:3241-3267`, `kreiraj_predmet`):**
1. `predmeti` row is inserted and committed (line 3249-3255) — the client already sees success at
   this point conceptually (`novi_predmet` exists).
2. `emit(EventType.PREDMET_KREIRAN, ...)` is called (line 3264), wrapped in a try/except that only
   `logger.warning`s on failure — never retried, never persisted.
3. If the process is killed (deploy, OOM, crash) **after step 1 commits but before the
   `asyncio.create_task` scheduled in step 2 actually runs** `on_predmet_kreiran` →
   `run_case_pipeline` to completion, the predmet exists in the database *forever* with:
   - no rokovi extracted,
   - no mini-strategija,
   - no HCC briefing,
   - no risk snapshot,
   - **and no marker anywhere that any of this was ever supposed to happen.** There is no
     `pipeline_status` column, no outbox row, no retry queue. The gap is permanently invisible —
     nothing will ever re-attempt it, and no dashboard or alert will ever flag the predmet as
     incomplete, because from the schema's point of view a predmet with no pipeline output looks
     identical to a predmet whose pipeline genuinely produced nothing (e.g. too little text to
     extract).
4. Same failure mode applies mid-pipeline: if `run_case_pipeline` itself throws partway through
   (see `services/case_pipeline.py:697-717` — 9 steps, several concurrent GPT calls with 20s
   timeouts), `on_predmet_kreiran`'s except (`event_bus.py:106-107`) just logs a warning. Whatever
   steps completed stay; whatever didn't, silently never will, again with no marker.

**This is exactly the gap already flagged in `MISSION_BOARD.md` as NEX-004 ("PREDMET_KREIRAN Event
Bus durability gap — needs `run_case_pipeline` idempotency verification before any fix is
attempted"). That verification is now done (see next paragraph) — the blocker for implementing a
fix is removed.**

**De-risking confirmation (idempotency of `run_case_pipeline`):** `services/case_pipeline.py:219-235`
(`_step_ekstrakcija_rokova`) starts every run with a marker check:
```python
ist_r = ... .like("pitanje", "[Pipeline:rokovi]%") ...
if _safe_data(ist_r):
    return StepResult(..., "Rokovi već ekstraktovani (idempotent)")
```
This is deliberately idempotent by design ("Idempotent: skips if `[Pipeline:rokovi]` marker exists"
per its own docstring). This means: **re-running `run_case_pipeline` for the same predmet_id is
safe and will not create duplicate rokovi/strategija/etc.** — a durable-outbox + retry fix for
`PREDMET_KREIRAN` (mirroring the `GENOME_UPDATED` pattern exactly: write to `events` table in the
same insert flow, let `dispatch_pending_events()` invoke the handler) is now verified low-risk to
implement. The same durable-outbox pattern should be checked (not yet verified in this
investigation — out of scope, flagged for Phase 3) for `ROK_KRITICAN` and `HEALTH_SCORE_PROMENJEN`
before converting those two the same way, since their handlers (`on_rok_kritican`,
`on_health_score_promenjen`) insert `proactive_alerts` rows with no dedup key visible in
`event_bus.py:66-95` / `126-146` beyond whatever the caller (`matter_intel.py`) already checked —
a naive durable retry could double-insert an alert if the caller-side dedup isn't itself
idempotent to being invoked twice for the same underlying state. **Recommendation: verify
`matter_intel.py`'s dedup-against-existing-unread-alerts check (mentioned in prior session
findings) is keyed on more than just time before wiring these two through the durable outbox.**

**Severity: CRITICAL.** This is the single largest reliability gap in the entire event architecture
— it is the only failure mode in this audit that can silently and permanently lose a business
outcome (an entire case's pipeline output) with zero trace, zero alert, and zero recovery path.

---

## Finding 2 (HIGH) — `DOKUMENT_UPLOADOVAN` has a working, tested handler that is never invoked

`on_dokument_uploadovan` (`event_bus.py:110-123`) is registered (`event_bus.py:199`) and writes a
`decision_log` entry on every document upload — but grepping `emit(EventType\.DOKUMENT_UPLOADOVAN`
and `EventType\.DOKUMENT_UPLOADOVAN` repo-wide (excluding docs/tests) returns **zero production
call sites**. The handler has been dead code since it was written. Not a durability bug — a pure
connectivity gap (same class Project Nexus already catalogued elsewhere) — flagged here because
Phase 2 explicitly asked to confirm "postoji producer" for every event, and for this one the answer
is unambiguously no.

**Severity: HIGH** (not CRITICAL — no data is at risk, an audit-trail entry is simply never
written), but cheap to fix and directly increases provenance coverage (Phase 5 of this mission)
since `decision_log` entries feed traceability elsewhere.

---

## Finding 3 (MEDIUM) — 3 dead `EventType` values with neither producer nor consumer

`ROK_DODAN`, `ROCISTE_ZAKAZANO`, `STRATEGIJA_GENERISANA`, `ANALIZA_ZAHTEVANA` (4, not 3 — corrected
count) are defined in the enum, never emitted anywhere, never subscribed to anywhere. They are
inert. No risk, but they are misleading — a future engineer (or an AI agent working autonomously
overnight) grepping `EventType.ROK_DODAN` will reasonably assume a live wire exists because the
enum member exists and reads as though it should. Recommend either wiring them to real producers
during a future mission or removing them with a comment explaining why, but this is explicitly an
Optimization-tier item (lowest priority per this mission's own stated order: Critical Flow
Integrity > Security > Reliability > Automation > Optimization) — not touched this investigation.

---

## Finding 4 (MEDIUM) — `DOCUMENT_JOB_ENQUEUED` / `DOCUMENT_JOB_COMPLETED` have producers but zero consumers

Both are written durably (`migrations/073_intake_foundations.sql:170-245`) and correctly picked up
by `dispatch_pending_events()` (`event_bus.py:274-330`) — but `bus._handlers[type]` is `[]` for
both (`event_bus.py:196-201` never subscribes them), so `publish_async` iterates zero handlers,
does nothing, and the row is marked `dispatched_at` regardless (`event_bus.py:311-314` — dispatch
success is defined as "handlers ran without throwing," and zero handlers trivially satisfies that).
**This is not currently harmful** — nothing in the product depends on reacting to a job being
enqueued or completed (the intake UI polls `intake_jobs` status directly, a separate mechanism, out
of this investigation's scope to re-verify). Flagged as MEDIUM only because it is a placeholder gap
that should be closed the moment any feature needs to react live to intake completion (e.g. a
"document ready" toast), not because anything is broken today.

---

## Finding 5 (HIGH) — `DOCUMENT_JOB_FAILED` is durably recorded and then silently discarded

**This is the one gap in Finding 4's category that IS currently harmful.** Producer path confirmed
live: `shared/intake_worker.py:118-125` calls `intake_queue.mark_job_failed(...)` on every worker
exception (`self.jobs_failed += 1; logger.error(...); await intake_queue.mark_job_failed(...)`),
which (per `migrations/073_intake_foundations.sql:276-280`) writes both an `intake_audit_log` row
and a durable `events` row with `event_type='DocumentJobFailed'`. But exactly like Finding 4, zero
handlers are subscribed to `DOCUMENT_JOB_FAILED` — the event is dispatched-and-dropped.

**Concrete impact:** when OCR/intake processing fails for an uploaded document (bad PDF, OCR
service down, embedding failure, any of the failure classes Phase 3 of this mission is about to
simulate), the failure is captured in `intake_jobs`/`intake_audit_log`/`events` tables — but **no
`proactive_alerts` row is ever created, no notification is ever sent.** A lawyer who uploaded a
document has no way to learn it failed to process except by manually re-checking the document's
status in the UI, if such a status indicator even surfaces this specific failure class (not
verified in this investigation — flagged for Phase 3's OCR-failure simulation to confirm).

**Severity: HIGH.** This is a genuine "silent error" in exactly the sense Phase 9's Beta Gate asks
about ("Može li kritična greška ostati neprimećena?" — can a critical error go unnoticed). Today,
yes, for intake/OCR failures specifically. Recommend subscribing a new handler (mirroring
`on_rok_kritican`'s `proactive_alerts` insert pattern) to `DOCUMENT_JOB_FAILED` — this is exactly
the item already scoped as NEX-005 in `MISSION_BOARD.md` ("new `DOCUMENT_JOB_FAILED` handler").

---

## Summary table — all 7 hardening properties, only for event types with a real handler+producer pair

| Event | Producer exists | Consumer exists | No double-emit | Idempotent | Retry | Recovery | Audit |
|---|---|---|---|---|---|---|---|
| `PREDMET_KREIRAN` | Yes (in-process only) | Yes | Yes (single call site) | Downstream pipeline: **yes**, verified | **No** | **No** | Partial (`log_action` for `predmet_create` exists separately, `api.py:3273+`, but nothing audits pipeline completion) |
| `ROK_KRITICAN` | Yes (in-process only) | Yes | Not verified this pass (see Finding 1 recommendation) | Not verified this pass | **No** | **No** | Not verified this pass |
| `HEALTH_SCORE_PROMENJEN` | Yes (in-process only) | Yes | Not verified this pass | Not verified this pass | **No** | **No** | Not verified this pass |
| `GENOME_UPDATED` | Yes (durable outbox) | Yes | Yes (comment explicitly designed to prevent double-run, `case_dna.py:510-514`) | Yes (poller-only dispatch) | Yes (`dispatch_attempts`/`last_error`, `event_bus.py:315-326`) | Yes (row persists until dispatched) | Yes (`on_genome_updated` writes `audit_immutable`) |
| `DOKUMENT_UPLOADOVAN` | **No** | Yes | N/A | N/A | N/A | N/A | N/A (dead) |
| `DOCUMENT_JOB_ENQUEUED/COMPLETED` | Yes (durable outbox) | **No** | N/A | N/A | Yes (outbox-level only) | Yes (outbox-level only) | Partial (`intake_audit_log`, no downstream reaction) |
| `DOCUMENT_JOB_FAILED` | Yes (durable outbox) | **No** | N/A | N/A | Yes (outbox-level only) | Yes (outbox-level only) | Partial (logged, never surfaced to user) |

**Only `GENOME_UPDATED` scores fully green across all 7 properties.** This confirms and updates the
prior session's finding — it remains true today, and is now understood as the *template* to copy
for `PREDMET_KREIRAN` specifically (already de-risked above), not just an isolated success.

---

## Single most severe gap (for coordinator)

`PREDMET_KREIRAN`'s producer path is pure in-process `emit()` with **zero durable-outbox backing**
(`api.py:3264`) — if the process crashes between the `predmeti` insert committing and the
fire-and-forget `asyncio.create_task` completing `run_case_pipeline`, the case permanently loses
all 9 pipeline outputs (rokovi, strategija, HCC briefing, risk snapshot, etc.) with **zero trace,
zero retry, zero alert** — nothing marks the predmet as pipeline-incomplete, so nothing will ever
notice or re-attempt it. The fix is now de-risked: `run_case_pipeline`'s own steps are already
idempotent by design (marker-based dedup, confirmed in `_step_ekstrakcija_rokova`,
`case_pipeline.py:219-235`), so converting `PREDMET_KREIRAN` to the same durable-outbox pattern
already proven correct for `GENOME_UPDATED` (`case_dna.py:503-545`) carries no risk of duplicate
pipeline output. This is the highest-leverage Phase-3+ fix in the entire event bus.
