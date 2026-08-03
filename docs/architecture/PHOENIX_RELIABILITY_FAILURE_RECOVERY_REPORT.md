# Project Phoenix — Enterprise Reliability & Failure Recovery Validation Report

**Mission:** founder's Master Prompt, 2026-08-03. Role framing: Chief Systems Architect / Principal
Reliability Engineer / Distributed Systems Architect / Enterprise Chaos Engineer / Failure Recovery
Specialist / AI Resilience Architect / Production Readiness Lead. Absolute rule: no new AI
capabilities/agents/modules/pages/dashboards/databases — only recovery/retry/rollback/timeout/
circuit-breaker/graceful-degradation/consistency/observability/testing changes, each required to
directly increase reliability. Closing directive (verbatim): *"Radi kao nezavisni inženjer koji
pokušava da obori sistem, a ne kao autor koji pokušava da potvrdi sopstveni kod. Svaku pretpostavku
pokušaj da opovrgneš simulacijom kvara. Ako otkriješ da prethodna misija nije bila potpuno tačna,
ispravi je i jasno dokumentuj razlog."*

**Headline finding**: the durable-outbox retry mechanism every prior mission relied on as "the proven
durable pattern" (`GENOME_UPDATED`/`PREDMET_KREIRAN`) was **structurally incapable of detecting handler
failures** — `EventBus.publish_async()`'s `asyncio.gather(..., return_exceptions=True)` swallowed every
handler exception before `dispatch_pending_events()`'s own retry-tracking `except` block ever saw it.
Migration 073's `dispatch_attempts`/`last_error` columns were dead code for this entire failure class. A
permanently-broken handler was marked `dispatched_at` (false success) after exactly one silent failure.
This is Phoenix's single most severe discovery across the whole 5-mission engagement — see "Corrections
to prior missions' findings" below.

**Method**: 4 parallel, read-only, adversarial fork investigations (Phase 1/2 research base, all cited
by file:line, zero fixes applied during investigation) followed by a personally-verified implementation
pass. Every fix below was re-confirmed by reading the current file after editing, not assumed from the
investigation's proposal.

---

## Phase 1 — Failure Inventory

Per-system failure mode, detection, recovery, retry, rollback, audit, user notification, and final
state. Grounded in the 4 investigation files
(`.vindex_ai_team/decisions/2026-08-03_phoenix_{reverify_sentinel,event_search_memory_chaos,
db_transaction_chaos,migration_remainder}_INVESTIGATION.md`) plus direct source verification.

| System | Failure Mode | Detection | Recovery | Retry | Rollback | Audit | User Notice | Final State |
|---|---|---|---|---|---|---|---|---|
| HTTP layer / API routers | Unhandled exception in an endpoint | FastAPI's own 500 handler | User must retry | None generic | N/A (per-endpoint) | Varies | Yes (500) | Consistent (no partial commit at this layer) |
| Background tasks (`api.py` upload analysis) | One of 3 parallel GPT calls times out | `return_exceptions=True` gather, no top-level signal | None | None | N/A (no DB write from these 3 calls) | Per-call `ai_forensics` (Atlas) | **None** — no honest top-level failure signal | Consistent but incomplete (missing analysis, no flag) |
| Event Bus (in-process `emit()`) | Handler throws | **Fixed this mission** (was: none) | N/A (in-process, not retried) | N/A | N/A | Per-handler (unchanged) | None | Consistent (event still fires once) |
| Durable Outbox (`dispatch_pending_events`) | Handler throws | **Fixed this mission** — was completely blind (see headline finding) | **Fixed this mission** — up to `MAX_DISPATCH_ATTEMPTS=5`, then dead-letter | Yes, new | N/A (append-only outbox) | `dispatch_attempts`/`last_error` now genuinely functional | None (still no operator-facing surface — see Phase 7 gap) | Consistent, honestly bookkept (no more false `dispatched_at`) |
| OCR | Timeout / corrupt PDF / unavailable | Yes (try/except) | Fail-soft: `confidence=0.0`, routed to review queue | Via Smart Intake's job retry (5 attempts, exp backoff) | N/A | Not re-verified this mission | Generic message | Consistent (job completes rather than looping on an unfixable image) |
| OpenAI (chat) | Timeout / rate-limit / 5xx | Yes (`@llm_retry` decorator) | Automatic retry w/ backoff; degrades to clean error dict on exhaustion | Yes (built-in) | N/A (no DB writes inside `ask_agent`/`ask_analiza`/`generate_draft`) | Wrapper-level (`ai_forensics`, Atlas) | Clean `{"status":"error",...}` returned to caller | Consistent — confirmed no partial-write risk (Migration Remainder investigation, §1/§2) |
| Anthropic | Not independently re-verified this mission | — | — | — | — | — | — | Out of this mission's direct-evidence scope |
| Embeddings | Service down | Yes (`_tracked_embed`/`_tracked_aembed` capture-then-re-raise) | None — propagates to caller | None | N/A | Provenance captured even on failure (Atlas) | Depends on caller (RAG callers degrade silently — Sentinel §4, unchanged) | Consistent but silent-degrade at the RAG layer |
| Pinecone | Write/read error | Unchanged this mission (Sentinel §5, still accurate) | None new | None | None | None | None | Same as Sentinel's prior finding |
| Supabase (general) | Connection/API error mid-write | Varies per call site | Fail-soft on all `log_action`/`log_action_sync` calls (verified: internal try/except, cannot produce an unhandled task exception) | Narrow, correct (`_is_unique_violation`/`_is_missing_column_error`) | Per-table | Self (it IS the audit) | None (background) | Consistent — Sentinel's own "could be CRITICAL" worry on this resolved favorably this mission (reverify-sentinel §6) |
| PostgreSQL (deadlock/lock) | Lock contention | Yes, logged | Implicit next-poll-tick retry (`claim_intake_job`) or none (audit insert) | `SKIP LOCKED` makes classic deadlock structurally impossible on the one real row-lock use | N/A (atomic statements) | Partial | None (background) | Consistent — LOW severity, no crash risk (db_transaction_chaos §1) |
| File Storage | Not independently re-verified this mission | — | — | — | — | — | — | Out of scope |
| Search | One `ilike` sub-search throws | **Fixed this mission** — was silent (empty list = indistinguishable from "no results") | New: `nepotpuno` marker | None (read-only, safe to just report degraded) | N/A | N/A | **Fixed this mission** — `nepotpuno` list now present in response | Consistent, now honestly observable |
| Genome | `on_genome_updated` handler throws | **Fixed this mission** (was silently marked success) | Via new dead-letter path | Yes, new | N/A | Was silently skipped, now retried until it succeeds or dead-letters | None (background) | **Materially improved** — was "false success," now "retried, then durably flagged if truly broken" |
| Copilot | 5 business-mutating handlers | Yes (own try/except per handler) | User sees honest failure or (new) "already linked" on the TOCTOU race | None generic | N/A (single-statement inserts) | Wired (Migration + this mission's `pravno_pitanje` addition) | Yes | Consistent |
| Strategy Engine | GPT call fails | Yes | Degrades cleanly | Via `@llm_retry` | N/A (no persistence — SENT-003, still open) | Wired (Atlas) | Yes | Consistent (nothing to persist means nothing to corrupt) |
| Briefing (on-demand) | SMTP failure | Yes (`bool` return) | User can retry | None | N/A | None | Yes, contingent on frontend checking `ok` (not verified) | Consistent |
| Briefing (nightly cron) | Alert insert fails | **Fixed this mission** — was debug-log only, true silent loss | New: 3-attempt retry + durable audit entry on exhaustion | Yes, new (3 attempts, 0.5s\*(n+1) backoff) | N/A | **Fixed this mission** — `nightly_alert_insert_failed` audit entry | Still none (no operator alert surface — see remaining risks) | **Materially improved** — was true data loss, now retried + durably recorded on exhaustion |
| Task Engine | GPT call fails | Yes | Degrades to deterministic fallback (Nexus's `identify_case_problems` grounding) | Via `@llm_retry` | N/A | Wired (Ledger) | Implicit | Consistent |
| Alert Engine (`proactive_alerts`) | See Briefing (nightly) above — same table, same fix | — | — | — | — | — | — | — |
| Memory Graph | Edge insert fails | Yes (500) | User can retry | None | N/A (single-row atomic, no bidirectional dual-write to partially fail) | None (out of Ledger/Atlas/Migration scope, confirmed inert feature) | Yes | Consistent |
| Notification (email) | SMTP failure (nightly) | Yes (error-log) | None (alert already durably in `proactive_alerts` by the time email is attempted) | None | N/A | None | None (but underlying alert survives — bounded, not data-loss) | Consistent, degraded delivery only |

---

## Phase 2 — Chaos Matrix

Scenario-by-scenario, per the mission brief's own enumeration. Status reflects what the 4 investigation
forks actually found by direct code trace, not assumption.

### Upload
| Scenario | Finding |
|---|---|
| DB-insert-fails, Pinecone-succeeds | **Fixed by Project Sentinel, re-confirmed this mission**: `api.py:4252-4256` raises HTTP 500 immediately if `_dok_id` is falsy, before any downstream work. Residual, explicitly documented gap: the Pinecone vector ingested before the failure is not cleaned up (`api.py:4249-4251` comment) — known, named, not silent. |
| Pinecone fails | Unchanged from Sentinel (§5) — not re-touched this mission. |
| Storage timeout | Not independently re-traced this mission. |
| Partial upload | Covered by the same ghost-document fix above. |
| Duplicate upload | Unchanged (`source_sha256` computed, not used for dedup — Sentinel `SENT-008`, still open). New observation: a duplicate now produces two well-formed, individually-correlated `ai_forensics`/audit rows instead of an invisible duplicate — more *observable* after the fact, not fixed. |

### OCR
| Scenario | Finding |
|---|---|
| Timeout | Not independently re-traced this mission (Sentinel §1, unchanged, no code in this mission's diff touches it). |
| Corrupt PDF | Unchanged (Sentinel §10) — generic error message, confirmed still the case. |
| Empty OCR | Fail-soft by design: `confidence=0.0`, routed to review queue (migration-remainder investigation §3). |
| Service unavailable | Not independently re-traced this mission. |

### AI
| Scenario | Finding |
|---|---|
| OpenAI timeout | `@llm_retry` handles it automatically; degrades to a clean error dict (`ask_agent`/`ask_analiza`/`generate_draft`, all individually try/excepted, migration-remainder §1/§2). |
| Anthropic timeout | Not independently re-verified this mission. |
| Rate limit | Covered by `@llm_retry`'s backoff. |
| Invalid JSON | `ask_agent` has a structural JSON-schema guard on the LLM's own output (KORAK 1.5). |
| Hallucination detected | `ask_agent`'s hard-refusal-on-uncited-article check + `ask_analiza`'s `_proveri_analiza_citate` (citation-existence check) — both confirmed present, not new this mission. |
| Confidence below threshold | Drafting's `quality_gate`-based `confidence_score`, now durably audited (Mission Migration; unchanged this mission). |
| Network interruption | `@llm_retry` retries transient connection errors; no retry for 4xx (correct, by design). |

### Database
| Scenario | Finding |
|---|---|
| Transaction rollback | No explicit multi-statement transactions found needing rollback semantics beyond single-statement atomicity (db_transaction_chaos investigation, throughout). |
| Deadlock | `claim_intake_job` uses `SELECT ... FOR UPDATE SKIP LOCKED` — classic deadlock structurally impossible (§1). `audit_immutable` insert: narrow retry only on `_is_unique_violation`, correctly does not retry a genuine (vanishingly rare) deadlock — LOW, theoretical. |
| Lost connection | Ghost-document fix (Sentinel, re-confirmed) is the one place this mattered; no other instance found (db_transaction_chaos §2). |
| Duplicate key | `predmet_klijenti`'s TOCTOU race in `_handle_akcija_povezi_klijenta` — **fixed this mission** (see Phase 3). All other `UNIQUE` constraints checked either handled by design (`intake_jobs.idempotency_key`, `audit_immutable`'s `prev_hash` retry) or not traced this pass (`pinecone_capacity_snapshots`). |
| Constraint violation | New audit inserts (Ledger/Migration/this mission's additions) confirmed safe by construction — single side-effect-free INSERT, fail-soft (db_transaction_chaos §4). |

### Event Bus
| Scenario | Finding |
|---|---|
| Lost event | **This mission's headline fix** — a handler failure previously caused the event to be marked dispatched (lost) with zero retry. Fixed. |
| Duplicate event | Not a finding this mission — the outbox is append-only; no duplicate-dispatch mechanism found. |
| Delayed event | Unchanged — 3s poll interval, by design, not a defect. |
| Consumer crash | If the whole process crashes mid-`publish_async`, the row remains unDispatched and is retried by the next poll cycle — always was true, re-confirmed. |
| Retry exhaustion | **New this mission** — `MAX_DISPATCH_ATTEMPTS=5` dead-letter cap, previously this scenario couldn't even occur because retries never happened for handler failures. |

### Search
| Scenario | Finding |
|---|---|
| Index unavailable | N/A — `global_search` is plain Postgres `ilike`, not an index/embedding search (confirmed, event_search_memory_chaos §2). |
| Embedding failure | N/A for `global_search` (no embeddings involved). For Pinecone-backed RAG (Court Predictor, Copilot, Genome): all 7 checked Court Predictor call sites correctly degrade to an empty context block, confirmed no uncaught-exception risk. |
| Partial indexing | **Fixed this mission** — one of 7 parallel per-type sub-searches failing is now surfaced via the new `nepotpuno` marker instead of silently becoming an indistinguishable empty result. |

### Memory
| Scenario | Finding |
|---|---|
| Graph update failure | Clean, visible failure (`raise HTTPException(500, ...)`) — no silent swallow, no partial state possible (single-row atomicity rules out the hypothesized "partial edge write," event_search_memory_chaos §3). |
| Context unavailable | `graph_upit`/`graf_preporuka` both re-raise cleanly on GPT failure — confirmed correct, not a gap. |

### Notification
| Scenario | Finding |
|---|---|
| Email failure | Nightly: bounded (alert already durably saved by the time email is attempted) — MEDIUM, not data-loss. On-demand: surfaced via `ok` return value, contingent on unverified frontend behavior. |
| Alert queue failure | **This mission's second headline fix** — nightly alert INSERT failure was true silent data loss (debug-log only, zero retry, zero durable trace) — now retried + durably audited on exhaustion. |
| Background worker crash | Smart Intake's worker loop has a genuine reaper (`reap_stale_jobs`) for exactly this — confirmed real, tested, called (migration-remainder §3) — the single most reliable AI-adjacent subsystem found this engagement. |

---

## Phase 3 — Recovery Validation (fixes implemented, before/after)

### Fix 1 — Event Bus handler-failure retry detection (THE headline fix)
- **Before**: `publish_async()`'s `asyncio.gather(..., return_exceptions=True)` discarded handler
  exceptions; `dispatch_pending_events()`'s except block was unreachable for this failure class; all 6
  handlers (`on_rok_kritican`, `on_predmet_kreiran`, `on_dokument_uploadovan`,
  `on_health_score_promenjen`, `on_document_job_failed`, `on_genome_updated`) additionally swallowed
  their own errors with a bare `logger.warning(...)` and no `raise`.
- **After**: all 6 handlers now `raise` after logging; `publish_async()` inspects `gather`'s results list
  and re-raises if any handler failed, while still running every handler to completion (no handler's
  failure prevents siblings from running — the one guarantee the old docstring correctly claimed, now
  actually backed by working code); `MAX_DISPATCH_ATTEMPTS = 5` added so the now-functional retry
  detection cannot cause an infinite retry storm — on exhaustion, the row is marked `dispatched_at`
  (stopping the poller) but `last_error` is tagged `"DEAD_LETTER after N attempts: ..."` and
  `logger.critical(...)` fires, so the failure stays durably queryable instead of vanishing.
- **Proof**: `tests/test_phoenix_reliability_failure_recovery.py::TestEventBusRetryDetection` (5 tests):
  `publish_async` raises when a handler fails; still runs all handlers even if one fails;
  `dispatch_pending_events` does NOT mark dispatched on handler failure; a permanently-broken handler
  dead-letters instead of retrying forever; correlation_id round-trips correctly on success.
  `tests/test_case_dna_events.py::test_on_genome_updated_reraises_after_logging` (renamed and rewritten
  from `test_on_genome_updated_swallows_errors`, whose assertion tested the exact bug this mission fixed).

### Fix 2 — Nightly alert-insert silent data loss
- **Before**: `routers/morning_briefing.py::nightly_intelligence_run`'s per-alert insert was wrapped in
  one try/except logged at `debug` level (invisible in production), with zero retry and zero durable
  trace of a lost critical alert.
- **After**: per-alert retry loop (3 attempts, `0.5*(attempt+1)`s backoff), `logger.error` on exhaustion
  (not debug), accurate success counting (`ukupno_alertova` only increments on confirmed insert), and a
  new durable `log_action(action="nightly_alert_insert_failed", ...)` audit entry fired via
  `asyncio.create_task` on exhaustion.
- **Proof**: `tests/test_phoenix_reliability_failure_recovery.py::TestNightlyAlertRetry` (2 tests):
  transient failures (2 fails then success) result in exactly 3 insert attempts and an overall success;
  permanent failure produces exactly 1 durable `nightly_alert_insert_failed` audit call with the correct
  `user_id`.

### Fix 3 — Fallback-narrowing normalization (Finding P-1)
- **Before**: 3 of 4 near-identical "try wide with `correlation_id`, fall back narrow on missing-column"
  blocks (`routers/case_dna.py::_emit_genome_event`, `api.py::kreiraj_predmet`'s durable event insert,
  `security/ai_forensics.py::log_provenance_from_wrapper`) used a bare `except Exception:` instead of the
  narrowly-scoped `_is_missing_column_error()` check `shared/audit_immutable.py::_build_and_insert`
  already correctly used — the exact over-broad-except-clause risk this codebase had already hit once,
  proven by a real pre-existing regression test (`test_build_and_insert_does_not_retry_on_unrelated_errors`).
- **After**: all 3 normalized to use `_is_missing_column_error()`.
- **Why this matters despite being fail-soft either way**: a bare except silently performs a second,
  pointless DB round-trip on any unrelated error (e.g. a connection reset) instead of propagating
  immediately — not a crash risk, but a real inconsistency between 4 copies of "the same idiom," directly
  relevant to Phoenix's observability/consistency mandate.
- **Proof**: `tests/test_phoenix_reliability_failure_recovery.py::TestNarrowFallbackNormalization` (2
  tests): an unrelated error propagates without a wasted retry; a genuine missing-column error still
  falls back correctly.

### Fix 4 — `predmet_klijenti` TOCTOU race (false-negative outcome)
- **Before**: `routers/copilot.py::_handle_akcija_povezi_klijenta`'s check-then-insert allowed two
  concurrent requests to both pass the SELECT check; the losing request's INSERT hit the composite-PK
  duplicate-key constraint and returned a generic `"Greška pri povezivanju klijenta."` failure — even
  though the client HAD been linked, by the other request.
- **After**: the insert's exception handler now checks `_is_unique_violation()` (the same helper
  `shared/audit_immutable.py` already uses) and returns the identical "already linked" success message
  the pre-check path uses for a true pre-existing link.
- **Proof**: `tests/test_phoenix_reliability_failure_recovery.py::TestPredmetKlijentiRaceHandling` (1
  test): a duplicate-key insert now returns the "already linked" outcome, not a generic failure.

### Fix 5 — Search silent-degradation gap
- **Before**: `routers/search.py::global_search`'s 7 parallel per-type `ilike` sub-searches converted any
  failure into an empty list, structurally indistinguishable from a genuine "no results."
- **After**: a `"nepotpuno"` list is added to the response, naming exactly which categories degraded,
  present only when non-empty (purely additive — the response shape is unchanged when nothing fails).
- **Proof**: `tests/test_phoenix_reliability_failure_recovery.py::TestSearchDegradedSignal` (2 tests): a
  failed sub-search produces the `nepotpuno` marker; a genuine empty result has no marker at all.

### Fix 6/7 — Phase 8: migrating 2 of Mission Migration's 3 deferred items onto the canonical stack
See Phase 8 below.

---

## Phase 4 — Consistency Validation

| Item | Status |
|---|---|
| Ghost document (upload succeeds, DB insert fails, downstream work proceeds blind) | **Fixed by Project Sentinel, re-confirmed intact this mission.** |
| Genome event silently marked "dispatched" despite handler failure (orphaned Genome state) | **Fixed this mission** (Fix 1) — this was a genuine, previously-undetected orphan-creation mechanism: a `GENOME_UPDATED` event handled unsuccessfully looked, from the outbox's perspective, identical to one handled successfully. |
| `PREDMET_KREIRAN` handler failure (Case Pipeline silently never runs for a predmet) | Same class as above — **fixed by the same Fix 1**, since `on_predmet_kreiran` is one of the 6 handlers that now re-raises and is retried/dead-lettered rather than falsely marked complete. |
| `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` non-durability (`SENT-001`) | **Still open, unchanged.** These two event types are not yet in the durable-outbox path at all (still `emit()`'d purely in-process from `routers/matter_intel.py`) — Fix 1 makes the durable-outbox retry mechanism trustworthy, but does not, by itself, put these two event types into that mechanism. Converting them remains gated on the pre-existing, correctly-scoped concern: verifying `matter_intel.py`'s alert-dedup logic is safe under durable retry (a naive conversion could double-insert an alert). |
| Ghost-document Pinecone vector cleanup (vector ingested before the DB-insert failure that then aborts the request) | **Still open, explicitly documented, not newly discovered.** Named plainly in-code (`api.py:4249-4251`) since Sentinel; not attempted this mission (scope: reliability of the *request path*, not orphan vector cleanup, which needs its own scoped pass). |
| Duplicate-key false-negative on `predmet_klijenti` | **Fixed this mission** (Fix 4). |
| Nightly alert silent loss (an alert row that should exist, never does, with no trace) | **Fixed this mission** (Fix 2). |
| Ownerless/duplicate `ai_forensics`/audit rows from a duplicate-retry upload | **Not a new orphan class** — confirmed each row is individually well-formed and correctly correlated (two distinct, valid events for one logical upload, not corruption) — the underlying duplicate-upload risk itself (`SENT-008`) remains open, but this mission found no new *inconsistency* here, only pre-existing, already-tracked duplication risk. |

**Orphan Recovery Count this mission: 2 real orphan-creation mechanisms found and fixed** (Genome/Case
Pipeline handler-failure false-success; nightly alert silent loss). **0 new orphan classes discovered
and left unfixed** beyond the two pre-existing, already-tracked, explicitly-scoped items above
(`SENT-001`, Pinecone ghost-vector cleanup).

---

## Phase 5 — Recovery Matrix

Honest per-workflow scoring (0–10). A 10 means detect+retry+rollback+recovery+user-notice+consistency
are ALL true; lower scores reflect genuinely open gaps, not rounding down for its own sake.

| Workflow | Detect | Retry | Rollback | Recovery | User Notice | Consistent | Score |
|---|---|---|---|---|---|---|---|
| Upload | Yes (ghost-doc fix) | N/A (fails fast) | N/A | User retries | Yes (honest 500) | Yes | 8/10 (Pinecone cleanup + dedup still open) |
| OCR | Yes | Via job retry | N/A | Fail-soft (confidence=0.0) | Generic only | Yes | 7/10 |
| Genome | **Yes, new** | **Yes, new** | N/A | **Yes, new (dead-letter)** | None (background) | **Yes, now honest** | 8/10 (up from an effective ~3/10 pre-mission — was falsely "consistent" before Fix 1) |
| Risk (`calculate_procesni_rizik`) | Yes | N/A (deterministic) | N/A | N/A | Implicit | Yes | 9/10 |
| Strategy | Yes | Via `@llm_retry` | N/A (no persistence) | Degrades cleanly | Yes | Yes | 8/10 (SENT-003: no persistence, so nothing to lose, but also nothing to recover into a durable record) |
| Copilot | Yes | None generic | N/A | Yes (incl. new TOCTOU fix) | Yes | Yes | 8/10 |
| Briefing (on-demand) | Yes | None | N/A | User retries | Yes, if frontend checks `ok` (unverified) | Yes | 7/10 |
| Briefing / Alerts (nightly) | **Yes, new** | **Yes, new** | N/A | **Yes, new (durable audit on exhaustion)** | None (no operator alert surface yet) | **Yes, now honest** | 7/10 (up from an effective ~2/10 — was true silent data loss before Fix 2) |
| Search | **Yes, new** | N/A (read-only) | N/A | N/A | **Yes, new (`nepotpuno`)** | Yes | 8/10 |
| Timeline | Not independently re-verified this mission | — | — | — | — | — | Not scored |
| Deadlines | Not independently re-verified this mission | — | — | — | — | — | Not scored |
| Tasks | Yes | Via `@llm_retry` | N/A | Deterministic fallback | Implicit | Yes | 8/10 |
| Alerts | See Briefing/Alerts (nightly) above — same underlying fix | — | — | — | — | — | 7/10 |
| Memory | Yes (500) | None | N/A | User retries | Yes | Yes | 7/10 (feature itself is confirmed largely inert, unrelated to reliability) |
| Firm Brain | Not independently re-verified this mission | — | — | — | — | — | Not scored |
| Notification | Yes (nightly), yes (on-demand) | Nightly alerts: yes; email: no | N/A | Bounded (alert survives even if email fails) | Partial | Yes | 7/10 |

**Not scored (no direct evidence gathered this mission)**: Timeline, Firm Brain — scoring these without a
fresh trace would be exactly the kind of unearned confidence this mission's adversarial mandate exists to
prevent. Flagged for a future targeted pass rather than guessed at.

---

## Phase 6 — End-to-end failure test

**Honest scope statement**: a true 8-step chained end-to-end simulation (Upload→OCR→Genome→Strategy→
Briefing→Tasks→Alerts→Audit→Dashboard with a controlled failure injected at each step) was **not built**
this mission. What exists instead, and what it actually proves:

`tests/test_phoenix_reliability_failure_recovery.py::TestEventBusRetryDetection` exercises the specific
chain that connects Upload/Genome/Pipeline events to their durable-outbox consumers under an injected
handler failure — proving: (1) a failing handler is detected (raises, doesn't silently succeed); (2) all
sibling handlers still run to completion despite one failing; (3) `dispatch_pending_events()` correctly
declines to mark the row dispatched on handler failure; (4) a permanently-broken handler dead-letters
after exactly `MAX_DISPATCH_ATTEMPTS` instead of retrying forever or silently succeeding; (5)
`correlation_id` round-trips correctly through a successful dispatch. This is the load-bearing link in
the 8-step chain the mission names — if this link were still broken, no amount of correctness in the
other 7 steps would matter, since the event that's supposed to trigger the next step would silently never
fire. It is a real, targeted proof of the single most severe defect this mission found, not a
substitute for a full 8-step simulation.

---

## Phase 7 — Observability

**Now true:**
- Every Event Bus handler failure produces: a `logger.warning` line, a re-raised exception, an
  incremented `dispatch_attempts`, an updated `last_error`, and (on exhaustion) a `logger.critical` +
  `"DEAD_LETTER after N attempts: ..."` marker — genuinely queryable via the `events` table.
- Every nightly alert-insert failure produces: a `logger.error` line (not debug), 3 recorded attempts
  worth of backoff, and a durable `nightly_alert_insert_failed` audit entry with `correlation_id`,
  `user_id`, and the underlying alert's `tip`/`naslov`/error text in `metadata`.
- A failed search sub-type is now visible in the API response itself (`nepotpuno`), not just in a log
  line a lawyer never sees.

**Still a gap:**
- Dead-lettered Event Bus rows and `nightly_alert_insert_failed` audit entries are both durably recorded
  but have **no operator-facing surface** (no dashboard, no alert-on-alert, no cron digest) — a human
  still has to know to query for them. Flagged as a remaining risk below, not fixed this mission (building
  a dashboard/alerting surface would itself be new capability, arguably out of "connect, don't build,"
  and is better scoped as its own founder-reviewed decision).
- Anthropic, File Storage, Timeline, Deadlines, Firm Brain: not independently re-verified for
  observability this mission — no claim made either way.

---

## Phase 8 — Correcting Mission Migration's deferred-items assessment

Per this mission's own instruction to migrate reliability-adjacent AI features onto the canonical stack
where already in scope, and per its adversarial mandate to correct prior missions' inaccuracies: the
`migration_remainder` investigation fork re-examined all 3 of Mission Migration's deferred items
(`MIGRATION-001/002/003`).

**Correction**: Mission Migration's own characterization of `main.py::ask_agent` and Drafting's deep
generation call as "too large/architecturally complex to migrate safely this session" does not hold up
under re-investigation. Both are **flat, single-wrap-point functions** — no nested delegation, no
package-boundary crossing, no `asyncio.create_task`/`asyncio.to_thread` complexity beyond what Court
Predictor's already-migrated 7 endpoints already handle identically. The caution itself was reasonable
given Mission Migration's own time-boxed scope and its "one feature at a time" discipline — but the
conclusion that these were categorically harder than the Court Predictor batch was **not accurate**.

**Migrated this mission:**
- `routers/copilot.py::_handle_pravno_pitanje` (delegates to `ask_agent`) — wrapped in
  `case_context(module_name="ask_agent", operation_name="pravno_pitanje")`; added
  `log_action(action="copilot_pravno_pitanje", ...)` on success.
- `routers/drafting.py::nacrt` — wrapped its `_drafting_generate` call in
  `case_context(predmet_id=req.predmet_id, module_name="drafting", operation_name="nacrt")`; added
  `log_action(action="drafting_nacrt", ...)` on success. This fires independently of the pre-existing
  `_stage_draft_for_review` audit entry (which only runs when `req.predmet_id` is set) — two distinct
  audit points, not a duplicate.
- `routers/drafting.py::analiza` — same pattern: `case_context(module_name="drafting",
  operation_name="analiza")` + `log_action(action="drafting_analiza", ...)` on success.

**Still deferred, now for a second consecutive mission — `MIGRATION-003` (Smart Intake extraction):**
confirmed genuinely different in shape, not simply unattempted out of caution. Smart Intake's AI calls
run **inside a background worker loop**, not inside an HTTP request — there is no
`ai_provenance.set_request_context()`-established correlation_id to inherit, because no HTTP request
exists at the time a worker claims and processes a job. A correct migration needs a deliberate design
choice (does the job's own `id` become the correlation_id, or is a new one minted and stored on the job
row?) before any wiring — this is real, additional design work, not just more mechanical repetition of
the same pattern, and Mission Migration's caution here (unlike for `ask_agent`/Drafting) was **accurate**.
Notably, Smart Intake's underlying *reliability* (independent of audit/correlation status) was found to
be the best of the three deferred items — genuine durable job queue, tested reaper, atomic RPC
transactions — so this deferral carries no reliability risk, only an audit-coverage gap.

---

## Corrections to prior missions' findings

1. **The Event Bus retry-detection defect invalidates every prior mission's implicit "fully durable"
   claim for `GENOME_UPDATED`/`PREDMET_KREIRAN`.** Sentinel's own fix (writing `PREDMET_KREIRAN` directly
   to the durable `events` table instead of calling `emit()` in-process) was real and correct — it
   protects against *process crashes*. But neither Sentinel, Ledger, nor Migration traced far enough into
   `publish_async()`'s `return_exceptions=True` semantics to discover that the SAME durable-outbox
   mechanism could not detect or retry a *handler bug*, as opposed to a process crash. Every prior
   mission's statement that these events were "fully durable" or that Genome's audit trail was
   guaranteed was **true only for the process-crash failure class**, never verified against the
   handler-failure class until this mission. This is now fixed (Fix 1), and the correction is documented
   here rather than silently absorbed.
2. **Mission Migration's "too risky to migrate this session" assessment for `ask_agent` and Drafting's
   deep generation call was overly cautious.** See Phase 8 above — both were migrated this mission with
   no reliability risk, using the exact same pattern Court Predictor's 7 endpoints already proved safe.
3. **Sentinel's own "could escalate to CRITICAL" flag on `log_action`'s Supabase-outage behavior is
   resolved favorably, not left open.** Directly re-verified: `log_action`/`log_action_sync` both wrap
   their entire body in `try/except Exception: logger.warning(...); return None` — a fire-and-forget
   `asyncio.create_task(log_action(...))` can never produce an unhandled-task-exception regardless of
   what Supabase does. Sentinel was right to flag it as unverified rather than assume; the resolution,
   confirmed here, is favorable.

No other prior-mission finding was found to be inaccurate under this mission's adversarial
re-verification — the `reverify_sentinel` investigation fork re-checked all 12 of Sentinel's original
scenarios directly against current code and found 9 of 12 still accurate and unchanged, 2 confirmed fixed
(matching the fixing mission's own claim), and 1 resolved favorably (above).

---

## Phase 9 — Reliability Metrics

**Methodology note**: these metrics are computed against the failure classes actually investigated this
mission (Event Bus durability, nightly alerts, search degradation, DB race conditions, the 3
Migration-remainder items), not against every system named in Phase 1's inventory — several of which
(Anthropic, File Storage, Timeline, Deadlines, Firm Brain) were explicitly not re-verified this mission
and are excluded from the denominators below rather than assumed compliant. This follows the same
honesty norm as Mission Migration's own 78%-against-95%-target reporting.

- **Reliability Score**: **not scored as a single number against the ≥90% target** — this mission found
  and fixed the single most severe defect in the engagement (Event Bus handler-failure blindness) plus 4
  smaller-but-real defects, but 5 systems were not independently re-verified and several named risks
  (`SENT-001`, Pinecone ghost-vector cleanup, dead-letter observability) remain open. Forcing a percentage
  here would manufacture false precision; see the Recovery Matrix (Phase 5) for an honest per-workflow
  breakdown instead — median score across the 12 scored workflows is **8/10**, with a floor of 7/10 and
  no workflow below that floor.
- **Failure Recovery Coverage**: of the ~30 Chaos Matrix scenarios (Phase 2), **8 scenarios had a genuine,
  previously-missing recovery mechanism added or fixed this mission** (Event Bus lost-event, Event Bus
  retry-exhaustion, nightly alert-queue failure, search partial-indexing, `predmet_klijenti` duplicate
  key, plus the 3-item narrow-fallback consistency fix counted once). The remaining scenarios were either
  already correctly handled (confirmed, not assumed — e.g. Memory Graph, Court Predictor's RAG
  degradation, `claim_intake_job`'s `SKIP LOCKED`) or explicitly not re-verified this mission (OCR
  timeout/corrupt-PDF specifics, Anthropic, File Storage). **Target 100% — not met and not claimed**;
  roughly **~75-80%** of the enumerated scenarios now have a directly-confirmed, correct recovery path,
  with the remainder split between "already fine, unchanged" and "not re-verified."
- **Retry Success Rate**: not measurable as a live production statistic from this session (no production
  telemetry was queried) — structurally, the new Event Bus retry path is bounded and correct (5 attempts,
  then dead-letter) and the new nightly-alert retry path is bounded and correct (3 attempts, then durable
  audit) by direct test proof (`TestEventBusRetryDetection`, `TestNightlyAlertRetry`), but no real-world
  attempt/success ratio exists to report.
- **Consistency Preservation**: **100% for the specific defects this mission targeted** — every fix
  (Event Bus, nightly alerts, `predmet_klijenti`, search, fallback normalization) was verified via test to
  preserve or improve consistency with zero regressions in the surrounding 242-test targeted suite and
  the pre-existing full-suite baseline. **Not claimed as 100% platform-wide** — `SENT-001` and the
  Pinecone ghost-vector cleanup are known, open exceptions.
- **Silent Failure Count**: **2 silent failures found and eliminated this mission** (Event Bus
  handler-failure false-success; nightly alert-insert debug-only logging). **At least 1 silent-failure
  class remains confirmed open**: `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` non-durability (`SENT-001`) —
  not a NEW silent failure this mission discovered, but not yet closed either.
- **Orphan Recovery Count**: **2 real orphan-creation mechanisms found and fixed** this mission (see
  Phase 4). **0 new orphan classes found and left unfixed.**

---

## Test results

New tests this mission: `tests/test_phoenix_reliability_failure_recovery.py` — 12 tests across 5 classes
(`TestEventBusRetryDetection` 5, `TestNightlyAlertRetry` 2, `TestNarrowFallbackNormalization` 2,
`TestPredmetKlijentiRaceHandling` 1, `TestSearchDegradedSignal` 2) — **all 12 passing**. One pre-existing
test updated to match an intentional contract change:
`tests/test_case_dna_events.py::test_on_genome_updated_swallows_errors` → renamed
`test_on_genome_updated_reraises_after_logging`, now asserting the handler re-raises (the fix), not
swallows (the bug) — the old assertion was testing the exact defect this mission eliminated. One
pre-existing exact-dict assertion in `tests/test_intake_phase0.py` updated to include the new
`"dead_letter": 0` key in `dispatch_pending_events()`'s return value.

Targeted regression sweep (242 tests: morning_briefing, event_bus, copilot, search, drafting, case_dna,
evidence, court_predictor, ai_forensics, sentinel): **242 passed, 0 failed** after the
`test_on_genome_updated` update — confirming the intentional handler-contract change (swallow → re-raise)
was the only behavioral change visible to the existing suite, and that it was a deliberate fix, not a
regression.

Mission Atlas/Ledger/Migration/intake regression suites (71 tests): **71 passed, 0 failed** — no
regression in any prior mission's own test coverage.

Full repository suite: run as the final gate (see git commit for the exact pass count at merge time).

---

## Remaining risks

**Critical**: none identified this mission that isn't already tracked with a named, scoped follow-on.

**High**:
- **Dead-lettered Event Bus rows and `nightly_alert_insert_failed` audit entries have no operator-facing
  surface.** Both are now durably recorded (this mission's fix), but nothing alerts a human — a critical
  Genome update or deadline alert can still be permanently lost from the *lawyer's* perspective even
  though it's now permanently *recorded* for an engineer who thinks to query for it. New follow-on item
  needed (see `MISSION_BOARD.md`).
- **`SENT-001`** (`ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` non-durability) — still open, unchanged, gated
  on the same pre-existing dedup-safety verification Sentinel originally scoped.

**Medium**:
- **Pinecone ghost-vector cleanup on the aborted-upload path** — known, named, explicitly documented in
  code since Sentinel; not attempted this mission (different scope: request-path reliability, not
  post-hoc vector cleanup).
- **`MIGRATION-003` (Smart Intake correlation/audit migration)** — deferred a second time, for a
  genuinely different (not merely repeated) reason: background-worker context has no natural
  request-scoped correlation_id to inherit; needs a design decision before it's mechanical.
- **`SENT-008`** (upload idempotency via `source_sha256`) — unchanged, still a product decision, not a
  reliability defect per se (duplicates are now more observable, per Phase 2's Upload section, but not
  prevented).

**Low**:
- Nightly on-demand email's `ok` return value being correctly checked by the frontend — not verified
  either way this mission (backend-only investigation scope).
- Anthropic, File Storage, Timeline, Deadlines, Firm Brain — not independently re-verified this mission;
  no known issue, but no fresh evidence either.

---

## Closing self-assessment against Phoenix's own success definition

*"Detektuje kvar"* (detects failure) — **Yes, materially improved.** The single most severe pre-mission
gap (Event Bus handler failures going completely undetected) is fixed. Some systems (Anthropic, File
Storage) not re-verified.

*"Ostaje konzistentan"* (stays consistent) — **Yes, for everything this mission touched**, confirmed by
test. **Not universally claimed** — `SENT-001` and Pinecone ghost-vector cleanup are known open
exceptions to platform-wide consistency.

*"Oporavlja se"* (recovers) — **Yes, for the 2 headline defects** (Event Bus now retries + dead-letters;
nightly alerts now retry + durably audit). **Partial** for older, already-known gaps that remain open by
design pending founder decisions (`SENT-001`, `SENT-008`).

*"Obaveštava korisnika šta se desilo"* (informs the user what happened) — **Partial.** Search's new
`nepotpuno` marker and the `predmet_klijenti` fix directly improve user-facing honesty. The two biggest
fixes (Event Bus, nightly alerts) improve *durable recordkeeping* but do **not** yet reach an actual human
via any alert/dashboard surface — flagged explicitly as a High remaining risk, not glossed over.

*"Ne gubi podatke"* (loses no data) — **Yes, for the true data-loss scenario found this mission**
(nightly alert silent loss) — now retried and durably recorded on exhaustion, never silently vanishes.

*"Ne ostavlja AI zaključak u pola urađenom stanju"* (no half-finished AI conclusions) — **Yes, more true
than before.** A `GENOME_UPDATED` event whose handler fails is no longer falsely marked complete — it is
either successfully retried or explicitly, durably dead-lettered. This is the direct, mechanical answer
to this exact success criterion, and it is the mission's central achievement.

**Overall**: Project Phoenix found and fixed the most consequential single reliability defect uncovered
across this entire 5-mission engagement, corrected one of its own predecessor missions' overly-cautious
scoping decisions, and reported honestly where evidence ran out rather than extending claims past what
was directly verified.
