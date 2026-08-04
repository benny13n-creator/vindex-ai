# Program Alpha — Backend Engineering Review (Agent 18)

**Date**: 2026-08-04
**Agent**: 18 — Backend Engineering Review Agent (`agents/18_backend_engineering_review_agent.md`)
**Change under review**: Program Alpha — elimination of 6 classes of duplicate business logic
**Format**: 7-field, per `AGENT_COMMUNICATION_PROTOCOL.md`
**Gate state**: `APPROVED WITH CONDITIONS` (condition C-1, below)

---

## 1. Scope

**Reviewed (working-tree state, read directly from disk — not from the briefing):**

- `routers/court_predictor.py` — `_CONFIDENCE_MAX_SCORE`, `_procenat_iz_score()`,
  `_calc_confidence_nivo()` signature change, `confidence_check` endpoint (lines 1018–1264).
- `shared/proactive_alerts.py` — the new canonical `create_proactive_alert()` (whole file, 87 lines).
- All **12** migrated call sites: `services/event_bus.py` ×3, `routers/case_dna.py` ×3,
  `routers/zakon_monitoring.py` ×2, `routers/morning_briefing.py` ×1, `routers/smart_intake.py` ×1,
  `routers/workflow.py` ×1, `routers/zadaci.py` ×1 — each diffed field-by-field against its pre-change form.
- `migrations/036_decision_log.sql` (`proactive_alerts` DDL + CHECK constraint) —
  schema/write-shape conformance.
- `api.py::correlation_id_middleware`, `api.py::_require_auth`, `shared/deps.py::get_current_user`,
  and `shared/ai_provenance.py`'s `set_request_context` / `current_correlation_id` /
  `new_correlation_id` signatures.
- `services/event_bus.py::dispatch_pending_events()`, `EventBus.publish_async()`,
  `EventBus.publish()`, `DispatchLoop`, `MAX_DISPATCH_ATTEMPTS`, `_is_missing_function_error()`.
- `migrations/091_event_bus_atomic_claim.sql` (`claim_pending_events` RPC semantics).
- Executed: `python -m py_compile` on all 11 changed Python files; `pytest
  tests/test_program_alpha_canonical_architecture.py` (11 passed);
  `pytest tests/test_phoenix_reliability_failure_recovery.py` (12 passed).

**Explicitly NOT reviewed this pass:**

- Frontend consumption of the changed `confidence-check` response (Agent 19's charter).
- The AI-substantive question of whether a 20–80% band is *legally* the right calibration
  (Agents 23/25).
- The deletion of `app/services/audit_log.py` and its `_al.log_response()` call sites — in the same
  diff but outside this brief's 4 named surfaces. I confirmed only that **zero dangling references
  remain** (`grep` for `_al.` / `app.services.audit_log` across all `.py`: no hits; `py_compile`
  clean). Whether losing that response-quality telemetry is acceptable is an **observability**
  question (Agent 33), not adjudicated here.
- Migration 091's deployment state. Per its own header it is DRAFTED, NOT APPLIED. I have **not**
  independently verified whether the founder has since run it in production; finding F-5's severity
  is conditional on that, and I state both branches.
- `routers/case_dna.py`'s `new_correlation_id()` unification (in the diff, correct, trivially
  verified — not a correctness surface, no finding).

---

## 2. Findings

### F-1 — Court Predictor signature change: exactly one call site, correctly updated. **NO DEFECT.**
`_calc_confidence_nivo()` now returns a 5-tuple. A repo-wide search for the identifier returns
exactly one production call site, and it unpacks 5 values. No second, un-updated caller exists — the
silent-breakage class this check exists to catch did not occur. Test coverage exists and passes.

### F-2 — `_CONFIDENCE_MAX_SCORE = 9` is provably the true maximum. **NO DEFECT.**
Traced all four scoring branches. Each is a mutually-exclusive `if/elif/else`, so each contributes at
most its own top value exactly once: rag ∈ {0, 2, 3}, vks ∈ {0, 1, 3}, kancelarija ∈ {0, 1, 2},
dokazi ∈ {0, 1}. Max = 3+3+2+1 = **9**; min = **0**. No path can exceed 9 and no off-by-one exists.
The `max(0, min(...))` clamp is therefore defensive-only and never fires — correct, not masking a bug.

Verified the derived percentage is also *internally consistent with the level it accompanies* — the
exact contradiction the fix targeted (`nivo="NISKO"` next to `procenat=78`) is now structurally
impossible. Full enumeration:

| score | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| procenat | 20 | 27 | 33 | 40 | 47 | 53 | 60 | 67 | 73 | 80 |
| nivo | NISKO | NISKO | NISKO | NISKO | SREDNJE | SREDNJE | SREDNJE | VISOKO | VISOKO | VISOKO |

Monotonic, bounded [20, 80], and the three `nivo` bands map to three disjoint percentage bands
(20–40 / 47–60 / 67–80) with no overlap. Python's banker's rounding is a non-issue here: no
`score/9*60` value lands on a `.5` boundary.

### F-3 — All 12 alert call sites preserve their original field values. **NO DEFECT.**
Field-by-field diff of every site. Every `user_id`, `tip`, `naslov`, `opis`, `urgentnost` value is
byte-identical to its pre-change form; no value swap (the `tip`/`naslov` adjacency is the obvious
swap hazard and it did not happen anywhere); `predmet_id` is passed at every site that previously had
one (case_dna ×3, morning_briefing, smart_intake, event_bus ×3) and correctly omitted at the three
that never had one (`workflow.py::_notify`, `zadaci.py::_posalji_notifikaciju`, both
`zakon_monitoring.py` sites) — no `predmet_id` was dropped.

**CHECK-constraint conformance verified exhaustively.** Every `urgentnost` value reaching the canonical
function is one of `normalna` / `visoka` / `hitna`. This includes the two indirect paths worth checking:
`workflow.py::_notify`'s parameter (traced to all 4 of its callers — three pass `"normalna"`, one
passes `"hitna"`), and `morning_briefing.py`'s AI-assembled `alerts` list (all four construction sites
are hard-coded literals, not LLM output). The nearby `"hitno"/"uskoro"` literals in
`morning_briefing.py:962` belong to a different response object and never reach this table.

The three `event_bus.py` sites previously omitted `procitana` entirely; the canonical function now
sends `False` explicitly. Equivalent — column default is `false`.

### F-4 — `case_dna.py`'s historically-broken site now uses correct field names. **NO DEFECT.**
The site whose own comment documents the 100%-silent-failure bug (wrong columns
`tekst_alerta`/`tip_alerta`/`hitnost`, PGRST204 on every call from the day it was written until the
2026-07-18 Reality Validation pass) is at `routers/case_dna.py:766`. Its migrated form passes
`tip=`/`naslov=`/`opis=`/`urgentnost=` as **named parameters** of a typed function. The claim in the
module docstring is architecturally sound and I confirmed it holds: the same mistake would now be a
Python `TypeError` at the call site, not a Postgres schema mismatch swallowed by a broad `except`.
This is a genuine, structural improvement, not a comment.

### F-5 — **The one real defect.** The new in-function retry can push a dispatch batch past migration 091's 30-second stale-claim window, re-opening the exact duplicate-processing race Mission Keystone closed. **MEDIUM.**

`dispatch_pending_events()` claims up to `DISPATCH_BATCH_SIZE = 50` rows and passes
`p_stale_claim_seconds: 30`. It then processes those rows **serially**, `await`ing each
`bus.publish_async(event)` in a plain `for` loop. `claim_pending_events()` makes any row whose
`claimed_at` is older than 30s claimable again by another worker.

`create_proactive_alert()` adds `asyncio.sleep(0.5)` + `asyncio.sleep(1.0)` = **1.5 seconds of
blocking wall-clock per permanently-failing alert**, on top of 3 network round-trips instead of 1.

Arithmetic: under a sustained `proactive_alerts` insert failure — the *exact* scenario this retry was
written for, and a historically real one per the module's own PGRST204 anecdote — **21 failing
alert-producing events is enough to exceed 30 seconds** (21 × 1.5s = 31.5s), and a full batch of 50
takes ≥75s in sleeps alone. Worker B's poll then re-claims rows Worker A is still grinding through
and re-runs their handlers concurrently.

Consequence (not corruption, which is why this is Medium and not Critical): duplicate execution of
each handler's *pre-alert* side effects — most concretely a duplicate `decision_log` row per re-claim
via `on_rok_kritican`'s `log_decision()` — plus duplicate `proactive_alerts` rows for one real event
once the DB recovers mid-batch. This is precisely the defect class migration 091 exists to prevent.

Pre-Alpha, a failing insert cost one round-trip (~O(100ms)), so a 50-row batch stayed comfortably
inside 30s. Program Alpha converts a safe-under-30s degraded batch into an unsafe one. It is a real,
new interaction, introduced by this change, in the surface my charter names first.

**It does not make *current* production worse**: migration 091 is drafted-not-applied per its own
header, so today's fallback plain-`SELECT` path already permits unconditional duplicate processing —
strictly worse than the window described here. F-5 is a defect in the *post-091* steady state.

### F-6 — Retry amplification against permanent errors. **LOW.**
`create_proactive_alert()` retries on *any* `Exception`, without distinguishing transient from
permanent. A permanently-invalid row (e.g. `on_rok_kritican` passing `event.user_id`, which
`dispatch_pending_events()` sets to `""` when the `events` row has a NULL `user_id` — a real shape,
since migration 073's `fail_intake_job` RPC writes rows without `user_id`) now burns 3 inner × 5 outer
= 15 insert attempts and 7.5s of sleeps before dead-lettering, versus 5 attempts before. It still
dead-letters correctly and nothing is lost; this is wasted work, not incorrectness. Noted, not blocking.

The related "5 outer retries re-run the whole handler, duplicating `log_decision`" behavior is
**pre-existing** (Project Phoenix's re-raise established it) and per my charter's Forbidden section I
do not raise it as a new finding — only its amplification, folded into F-5.

### F-7 — Event Bus `raise` correctly reaches the retry/dead-letter path. **NO DEFECT.**
This was the highest-risk-looking item in the brief: the new `raise RuntimeError(...)` sits inside each
handler's own `try: ... except Exception as exc:` block, which at first read would swallow it. It does
not — all three handlers' `except` blocks end in a bare `raise` (Project Phoenix, 2026-08-03). Traced
the full path end to end and it is correct at every hop:

handler `raise` → `except` logs + re-raises → `publish_async()`'s `asyncio.gather(...,
return_exceptions=True)` collects it, then the `for result in results: if isinstance(result,
BaseException): raise result` loop re-raises it (Phoenix's fix — `return_exceptions=True` deliberately
retained so one broken handler still cannot prevent the *execution* of the others) →
`dispatch_pending_events()`'s `except` increments `dispatch_attempts`, writes `last_error`, clears
`claimed_at` for a fast retry, and at `MAX_DISPATCH_ATTEMPTS = 5` dead-letters with an explicit
`DEAD_LETTER` prefix + `logger.critical`. **No false-success return exists on this path** — the row is
never marked `dispatched_at` on a failure except in the dead-letter branch, which is provably not a
silent success.

`create_proactive_alert()` itself cannot raise into a caller that isn't expecting it: every failure
path is inside its `try`, and its post-loop `asyncio.create_task(log_action(...))` is safe because the
function is `async` (a running loop is guaranteed) and `log_action` is a coroutine function — this is
*not* a recurrence of Mission Migration's `create_task`-in-worker-thread bug.

### F-8 — Correlation-ID unification is signature-correct and semantically sound. **NO DEFECT.**
`set_request_context(user_id=..., correlation_id=...)` matches the real signature
(`shared/ai_provenance.py:60-73`, three optional kwargs, returns `str`).
`current_correlation_id()` (`:120-124`) takes no arguments and returns `Optional[str]`; passing its
`None` result is safe because `set_request_context` mints via `new_correlation_id()` on a falsy value.
The `set_request_context` call *replaces* the whole context dict, so `tenant_id` is reset to `None` —
but it was already `None` pre-change (the prior call also omitted it), so no regression.

The middleware's contextvar does propagate downstream despite Starlette's `BaseHTTPMiddleware` task
hop: `call_next` starts the downstream task from *inside* the middleware's own context, after
`set_request_context` has run, so the child task's copied context carries the id. The `X-Correlation-ID`
response header now returns the same id that lands in `audit_immutable`/`ai_forensics`/`events` — the
disconnect the change describes is genuinely closed for the `get_current_user` path.

`api.py::_require_auth`'s known-inert `to_thread` contextvar-isolation limitation is **disclosed in the
code comment itself** and filed to `ARCHITECTURAL_DEBT_REGISTER.md`. I verified the claim is accurate
(contextvar mutations inside a `to_thread`-offloaded call do not propagate to the awaiting coroutine).
Leaving the call in place is harmless and correct-if-later-made-async. Honest disclosure, not a defect.

### F-9 — Query completeness (charter's post-backtest bullet). **NO DEFECT.**
The only `SELECT` the change touches in a reviewable way is `confidence_check`'s `case_patterns`
query, `.select("faktor,pobede,porazi,uzoraka")` — downstream code reads exactly `pobede`, `porazi`,
`faktor`, and orders by `uzoraka`. Every column read is selected. No `ccc.py`-shaped omission.
`on_document_job_failed`'s `intake_jobs` select is unchanged and complete for its four reads.

---

## 3. Evidence

| # | Evidence |
|---|---|
| F-1 | Sole call site: `routers/court_predictor.py:1182-1184`, unpacking 5 values. Repo-wide search for `_calc_confidence_nivo` returns production hits only in that file. Test: `tests/test_program_alpha_canonical_architecture.py:113-127` (`test_calc_confidence_nivo_returns_score_for_procenat_derivation`) — passing. |
| F-2 | Scoring branches: `routers/court_predictor.py:1054-1090`. Bands: `:1092-1097`. Formula + clamp: `:1031-1040`. Constant: `:1028`. Tests `:97-143` — passing (11/11). |
| F-3 | Schema: `migrations/036_decision_log.sql:40-51` (CHECK at `:47-48`). Canonical write shape: `shared/proactive_alerts.py:59-69`. Call sites: `services/event_bus.py:91,153,200`; `routers/case_dna.py:438,766,917`; `routers/zakon_monitoring.py:264,544`; `routers/morning_briefing.py:748`; `routers/smart_intake.py:553`; `routers/workflow.py:81`; `routers/zadaci.py:124`. `_notify` callers: `routers/workflow.py:278,422,440,543`. Alert-list literals: `routers/morning_briefing.py:557,579,601,616`. Unrelated literals: `routers/morning_briefing.py:962`. |
| F-4 | `routers/case_dna.py:754-774` (migrated form + retained historical comment). |
| F-5 | `DISPATCH_BATCH_SIZE = 50` — `services/event_bus.py:380`. `p_stale_claim_seconds: 30` — `services/event_bus.py:429`. Serial `for row in rows:` + `await bus.publish_async(event)` — `services/event_bus.py:447,466`. Sleep budget — `shared/proactive_alerts.py:73-74` (`0.5*(attempt+1)`, `_MAX_ATTEMPTS = 3` at `:32`). Reclaim predicate — `migrations/091_event_bus_atomic_claim.sql`, `claim_pending_events` body: `claimed_at < now() - make_interval(secs => p_stale_claim_seconds)`. Non-idempotent pre-alert side effect — `services/event_bus.py:76-84` (`log_decision`). |
| F-6 | `shared/proactive_alerts.py:71` (bare `except Exception`). `services/event_bus.py:460` (`user_id = row.get("user_id") or ""`). `MAX_DISPATCH_ATTEMPTS = 5` — `services/event_bus.py:388`. |
| F-7 | Re-raise in handlers: `services/event_bus.py:107-111`, `:165-167`, `:212-214`. Propagation: `:330-333`. Retry accounting: `:469-512`. Dead-letter: `:474-497`. `create_task(log_action(...))` — `shared/proactive_alerts.py:80-85`; `log_action` is `async def` at `shared/audit_immutable.py:127`. Regression suite `tests/test_phoenix_reliability_failure_recovery.py` — 12/12 passing. |
| F-8 | `shared/ai_provenance.py:60-73` (`set_request_context`), `:120-124` (`current_correlation_id`), `:127-128` (`new_correlation_id`). Call sites: `api.py:1004` (middleware), `api.py:3108-3110` (`_require_auth` + its disclosed limitation comment at `:3097-3106`), `shared/deps.py:305-313`. Old removed ContextVar has zero remaining readers (repo-wide search: only a docstring reference and the test asserting its absence, `tests/test_program_alpha_canonical_architecture.py:82-88`). |
| F-9 | `routers/court_predictor.py:1157-1174`; `services/event_bus.py:185-198`. |
| All | `python -m py_compile` clean across all 11 changed files. No dangling `_al.` / `app.services.audit_log` references remain after `app/services/audit_log.py`'s deletion. |

---

## 4. Risk Classification

| Finding | Severity |
|---|---|
| F-5 — retry sleep budget vs. 30s stale-claim window → duplicate handler execution | **Medium** |
| F-6 — retry amplification on permanent errors (wasted work, still dead-letters) | **Low** |
| F-1, F-2, F-3, F-4, F-7, F-8, F-9 | **No defect** |

No Critical or High finding. Specifically, I searched for and did **not** find any of my veto triggers:
no false-success return, no transaction gap that can silently corrupt state, no unhandled race in the
non-degraded path.

---

## 5. Recommendation

### `APPROVED WITH CONDITIONS`

Per `QUALITY_GATES.md` rule 1, this is **not a pass** — it is contingent on the following named,
checkable condition being verified before the final recommendation:

**C-1 (blocking until closed).** Bound the degraded-path dispatch batch so it cannot outlive the
claim. Any *one* of these closes it, and each is mechanically checkable:

- **(a)** Reduce `DISPATCH_BATCH_SIZE` (`services/event_bus.py:380`) so that
  `BATCH_SIZE × worst-case per-event latency < p_stale_claim_seconds` — at the current 1.5s sleep
  budget, ≤15 gives a ~2× margin; **or**
- **(b)** Raise `p_stale_claim_seconds` (`services/event_bus.py:429`) above the worst-case batch
  wall-clock (≥120s for a 50-row batch), accepting the slower crashed-worker recovery; **or**
- **(c)** Skip the inner retry when the caller is the dispatch loop — the outer
  `MAX_DISPATCH_ATTEMPTS = 5` already provides durable retry there, so the inner 3× is redundant
  precisely where it is most harmful. This is my preferred fix: it removes the risk at its source
  rather than tuning around it, and it preserves the full retry benefit for the 9 non-Event-Bus call
  sites that have no outer retry of their own.

**C-1 is verifiable-before-merge and does not require production access.** Note the timing: because
migration 091 is drafted-not-applied, C-1 must be closed **before 091 is run**, not before this merge —
if the founder's sequencing puts 091 later, this may be recorded as a merge-now/fix-before-091
condition at his discretion (`DECISION_ESCALATION_POLICY.md`).

F-6 is advisory: route to `MISSION_BOARD.md`, do not gate on it.

**Everything else in this change is correct.** The Court Predictor fix is mathematically sound and has
exactly one, correctly-updated call site. All 12 alert migrations preserve their values exactly and
conform to the live CHECK constraint. The correlation-ID unification is signature-correct with its one
real limitation honestly disclosed in-code rather than papered over. The Event Bus `raise` reaches the
dead-letter path correctly — the swallowed-exception hazard that the diff's shape suggests does not
exist, because Phoenix's re-raise is already there.

---

## 6. Confidence

| Finding | Confidence | Basis |
|---|---|---|
| F-1 | **High** | Exhaustive repo-wide identifier search; single site; test passes. |
| F-2 | **High** | Full enumeration of all 10 reachable scores; branch structure proves the bound. |
| F-3 | **High** | Every one of the 12 sites diffed field-by-field against the real DDL; all indirect `urgentnost` paths traced to literals. |
| F-4 | **High** | Direct read of the migrated code. |
| F-5 | **Medium** | The code path, batch size, claim window, and sleep budget are all read directly and are certain. The *arithmetic* is certain. What is **not** measured is the real per-insert network latency under a live outage, which sets how many failing events are needed in practice. My 21-event threshold counts sleeps only and is therefore a **lower bound** — the true threshold is smaller, never larger. I have not reproduced this under load; that is a Reliability & Chaos (Agent 20) exercise, not something I can assert from static reading. |
| F-6 | **High** | Direct read; consequence is bounded and self-limiting. |
| F-7 | **High** | Every hop of the propagation chain read directly; 12/12 Phoenix regression tests pass. |
| F-8 | **High** for the signature/semantic check (signatures read directly). **Medium** for the Starlette `BaseHTTPMiddleware` context-propagation reasoning — argued from the framework's task-spawn semantics, and corroborated by a passing test (`test_middleware_sets_the_canonical_ai_provenance_context`), but not verified against a live multi-middleware production request ordering. |
| F-9 | **High** | Both touched queries read directly against their consumers. |

---

## 7. Open Questions

1. **Which C-1 remedy does the founder want?** (a), (b), and (c) have different tradeoffs — (b) slows
   crashed-worker recovery; (c) changes behavior only for the 3 Event Bus sites. My recommendation is
   (c), but this is a design choice, not a correctness one.
2. **Has migration 091 actually been run in production?** I could not determine this from the
   repository (per standing convention, migrations are drafted here and run by the founder). F-5's
   urgency depends entirely on the answer: if 091 is not yet applied, C-1 is a fix-before-091 item;
   if it *is* applied, C-1 should be closed promptly.
3. **Is the loss of `_al.log_response()` telemetry accepted?** `app/services/audit_log.py` was deleted
   and 3 call sites (`/api/bot/ask`, `/api/pitanje`, `/api/pitanje/stream`) removed in this same diff.
   No dangling references remain, so it is *safe*; whether the response-quality signal (confidence /
   top_score / top_article / latency per query) is still needed is an Observability (Agent 33) and
   Metrics Guardian (Agent 31) question. Flagged, not silently dropped — outside my charter to adjudicate.
4. **Does `confidence_check`'s `procenat` visually collide with the separate prediction endpoint's
   LLM-authored `procenat_min`/`procenat_max` (`routers/court_predictor.py:213-214`)?** These are two
   different endpoints expressing two different concepts, so this is *not* a duplicate-author defect
   at the backend layer. But if the UI shows both to a lawyer on one screen, a user could read them as
   contradictory. Routed to Agents 19/21/28.
5. **Pre-existing, noted not raised:** `confidence_check` builds `kancelarija_data["uzoraka"]` as
   `sum(pobede + porazi)` while a distinct `uzoraka` column is selected and used only for ordering
   (`routers/court_predictor.py:1157-1174`). If those two ever diverge the scoring input is not what
   its name implies. Predates this change and is not touched by it — logged for `MISSION_BOARD.md`.

---

**Gate state: `APPROVED WITH CONDITIONS`** — condition **C-1** (bound the dispatch batch's degraded-path
wall-clock below the 30s stale-claim window) must be closed and verified before migration 091 is run.
