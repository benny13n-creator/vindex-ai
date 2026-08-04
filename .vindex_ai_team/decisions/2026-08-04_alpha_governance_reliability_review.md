# Program Alpha — Reliability & Chaos Review (Agent 20)

**Agent**: 20 — Reliability & Chaos Agent (`agents/20_reliability_chaos_agent.md`)
**Mission under review**: Program Alpha (2026-08-04) — elimination of 6 classes of duplicate business logic
**Date**: 2026-08-04
**Format**: mandatory 7-field (`AGENT_COMMUNICATION_PROTOCOL.md`)
**Gate vocabulary**: `PROTECTED` / `PARTIAL` / `VULNERABLE` (`QUALITY_GATES.md`, row Agent 20)

---

## 1. Scope

### Reviewed (read fresh from the working tree, not from any prior mission's report)
- `shared/proactive_alerts.py` (new file, 87 lines) — the canonical `create_proactive_alert()`.
- All 12 call sites of `create_proactive_alert` across 7 files (`services/event_bus.py` ×3,
  `routers/case_dna.py` ×3, `routers/zakon_monitoring.py` ×2, `routers/morning_briefing.py`,
  `routers/smart_intake.py`, `routers/workflow.py`, `routers/zadaci.py`).
- `services/event_bus.py` in full — `publish()`, `publish_async()`, `emit()`,
  `dispatch_pending_events()`, `MAX_DISPATCH_ATTEMPTS`, dead-letter path, `DispatchLoop`.
- `api.py::correlation_id_middleware` (lines 984–1008), `api.py::_require_auth` (lines ~3075–3115) and
  its 11 `asyncio.to_thread` call sites, `shared/deps.py::get_current_user` (lines 280–316),
  `shared/ai_provenance.py` in full, `shared/audit_immutable.py::log_action`.
- `migrations/090_ledger_correlation_id.sql`, `migrations/091_event_bus_atomic_claim.sql`,
  `gunicorn.conf.py`, `api.py`'s CORS configuration.
- Precedent chaos coverage, per charter ("extend rather than re-derive"):
  `tests/test_phoenix_reliability_failure_recovery.py`,
  `tests/test_program_alpha_canonical_architecture.py`,
  `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` (ALPHA-001 confirmed registered).

### Chaos experiments actually executed (not reasoned about — run)
Two standalone repro scripts were written and executed against this machine's real runtime
(Python 3.13.12, FastAPI 0.135.3, Starlette 1.3.1 — the versions this repo resolves):

- **EXP A** — `asyncio.to_thread` contextvar propagation, both directions.
- **EXP B** — a real FastAPI app carrying a byte-identical copy of `correlation_id_middleware`, plus
  an async-`Depends` auth path, a `to_thread` auth path, an unauthenticated path, a 20-way concurrent
  interleaved-request probe, and an unhandled-exception path, driven through `httpx.ASGITransport`.
- **EXP C** — fire-and-forget `asyncio.create_task(log_action(...))` survival under a closing loop.
- **EXP D** — unreferenced-task garbage-collection risk (50 tasks, forced `gc.collect()`).

### Explicitly NOT reviewed this pass
- The other 3 of Program Alpha's 6 consolidations (risk-band/percentage helpers etc.) — out of the
  scope handed to this agent.
- Live production behaviour. Nothing here was executed against real Supabase; every DB interaction was
  reasoned from code plus the migration DDL. **Production Reality Gate is not this agent's job**
  (`feedback_engineering_rigor_methodology`).
- Whether migrations 090 / 091 have actually been run in production — treated as unknown (see Open
  Questions). Both files carry "DRAFTED, NOT applied" headers.
- Security/privacy adjudication of F-6 — raised here for its reliability impact only, routed to
  Agent 05 / Agent 26.

---

## 2. Findings

### F-1 — The "3 handlers re-raise so the Event Bus retry sees it" rationale holds for only 1 of the 3 (High)
`on_rok_kritican` and `on_health_score_promenjen` are, in the *current* repository, produced by exactly
one thing: `routers/matter_intel.py::_maybe_emit_health_and_deadline_events`, which calls the **in-memory**
`emit()` → `bus.publish()` → `loop.create_task(_run())`. `_run()` catches every handler exception and only
`logger.error`s it. There is no `events` row, no `dispatch_attempts`, no `claimed_at`, no `DEAD_LETTER`
line, and no retry for that path at all. The newly added `raise RuntimeError(...)` in those two handlers
is therefore swallowed one stack frame later; the only durable trace of a permanently failed critical-
deadline alert remains `create_proactive_alert()`'s own `proactive_alert_insert_failed` audit row.

Only `on_document_job_failed` is genuinely reached by `dispatch_pending_events()`, because
`DOCUMENT_JOB_FAILED` rows are written into `events` by migration 073's `fail_intake_job` RPC and never
emitted in-process.

The code is not wrong — the raise is harmless and becomes correct the moment either producer moves to the
outbox. What is wrong is the **claim**. A final report asserting that these three handlers' failures reach
the Phoenix retry/dead-letter mechanism would leave a future engineer believing a critical-deadline alert
loss is dead-lettered and queryable from `events`, when for 2 of 3 it is not. This is the exact failure
class my charter forbids ("treating a try/except as proof of resilience without tracing the exception
path"), applied one level up: treating a `raise` as proof of retry without tracing where it lands.

### F-2 — The new retry backoff can exceed the 30s claim window, causing cross-worker duplicate dispatch (High)
Answering the brief's explicit question — *does the canonical function introduce a race the 12 old
independent implementations did not have?* — **yes, quantifiably.**

- `create_proactive_alert` sleeps `0.5 + 1.0 = 1.5s` per permanently-failing insert (plus 3 network round
  trips), where the pre-Alpha `event_bus.py` inline inserts failed in ~1 RTT with **zero** deliberate sleep.
  (Only `morning_briefing.py`'s site had a backoff before, and that site is not inside the dispatch loop.)
- `dispatch_pending_events()` processes rows **sequentially** (`for row in rows: await ...`), with
  `DISPATCH_BATCH_SIZE = 50`.
- `claim_pending_events(p_batch_size, p_stale_claim_seconds=30)` stamps `claimed_at = now()` **once**, at
  claim time. Nothing refreshes it mid-batch; the RPC re-includes any claim older than 30s.
- `gunicorn.conf.py` runs 4 workers by default, each starting its own `DispatchLoop` (`api.py:829-831`).

**Threshold: ~30s / 1.5s ≈ 21 rows.** A batch containing ≥21 consecutively-failing alert-bearing events
takes longer than the claim window; worker B then legitimately re-claims rows worker A has not yet reached
and re-dispatches them — duplicate `proactive_alerts` rows and duplicate audit entries for one real
business event, the precise defect migration 091 was written to eliminate. The triggering condition is
*exactly the Supabase-degradation scenario the retry exists to survive*: the mitigation creates the
window under the failure it mitigates.

The **currently live** state is worse, not better: 091 is drafted-not-applied, so the plain-SELECT fallback
is in force, where a row worker A is sleeping on is still `dispatched_at IS NULL` and is simply re-selected
by worker B's next 3s poll. Alpha widens an already-open, already-known hole (Keystone Phase 4).

### F-3 — Retry amplification: 15 insert attempts and 5 audit rows per one logical event (Medium)
For `on_document_job_failed`, the two retry layers now compose multiplicatively: 5 dispatch attempts ×
3 internal attempts = **15 insert attempts**, and **5 separate `proactive_alert_insert_failed` audit rows**
plus one `DEAD_LETTER` for a single failed document job. Retry is correctly **bounded** — I traced it and
confirm no infinite-retry/resource-exhaustion path exists (dead-letter caps at 5, `claimed_at` clearing
keeps cadence but does not bypass the counter). The cost is audit-trail inflation at a 5:1 ratio, which
matters specifically because Mission Ledger/Atlas metrics are computed by counting audit rows.

Secondary: `attempts = (row.get("dispatch_attempts") or 0) + 1` is a read-modify-write with no atomicity.
Two workers reading the same value both write the same increment, so `MAX_DISPATCH_ATTEMPTS = 5` is a soft,
not exact, bound under concurrency. Pre-existing, but F-2's widened overlap window makes it likelier.

### F-4 — The caller split is three-way, not two-way: the `bool` is discarded at 6 of 12 sites (Medium)
The brief describes a two-way split (raise vs. check-and-continue). The actual state is three-way. Six
call sites `await create_proactive_alert(...)` and **discard the return value entirely**:
`routers/case_dna.py` ×3, `routers/smart_intake.py`, `routers/workflow.py::_notify`,
`routers/zadaci.py::_posalji_notifikaciju`.

The highest-stakes of these is `routers/smart_intake.py:553` — the **`"BLOKIRAJUĆI sukob interesa"`**
conflict-of-interest alert (`urgentnost="hitna"`), a legal-ethics-critical notification, whose permanent
failure is discarded inside a fire-and-forget `asyncio.create_task(_conflict_check_bg())`.

This is not a regression — the pre-Alpha code swallowed the same failure — but Alpha newly *created* a
truthful failure signal and then left half the call sites throwing it away. That is the "false success"
shape my charter names as a veto trigger; it does not trigger the veto here only because the canonical
function itself returns honestly and the loss is independently audited.

### F-5 — The durable failure audit is a fire-and-forget task and is provably lost if the loop closes (Medium, latent)
`shared/proactive_alerts.py:81` does `asyncio.create_task(log_action(...))` — unawaited, unreferenced.
EXP C reproduced total loss of that audit write deterministically: under `asyncio.run()`, the task is
cancelled at loop close and never runs. That is exactly the shape of `event_bus.py:307-308`'s
`except RuntimeError: asyncio.run(_run())` fallback in `publish()`.

I am rating this **latent, not live**: the only in-repo `emit()` producer (`matter_intel.py`) is `async`,
so it takes the `loop.create_task` branch and the audit survives (EXP C2 confirms). It *is* live on
process shutdown — gunicorn SIGTERM cancels untracked tasks, and `stop_dispatch_loop()` awaits only the
DispatchLoop task, never handler tasks or this audit task. The task's exception is also never retrieved.

Honest negative result: I tested the "unreferenced task gets garbage-collected mid-flight" hypothesis
(EXP D, 50 tasks + forced `gc.collect()`) and **50/50 completed**. I do not claim that risk here.

### F-6 — `X-Correlation-ID` is client-controlled and unvalidated (Medium — reliability of the join key)
`api.py:1005` passes `request.headers.get("X-Correlation-ID")` straight into `set_request_context()` with
no validation, and migrations 089/090 store it as `TEXT` in `ai_forensics`, `events`, and the hash-chained
`audit_immutable`. A client can send one constant value on every request (collapsing the join key this
entire change exists to make trustworthy), a value colliding with another user's trail (polluting an
immutable audit's correlation graph), or a CRLF/oversized value that lands verbatim in
`logger.critical("... correlation_id=%s ...", ...)` at `event_bus.py:485`. Reliability framing:
the id is externally forgeable, so "search this header's value in the audit table" is not a sound support
procedure without a uniqueness caveat. Routed to Agent 05 / Agent 26 for their own adjudication.

### F-7 — A 500 loses the header, and browsers cannot see or send it cross-origin (Low)
EXP B6: an endpoint raising an unhandled exception returns **500 with no `X-Correlation-ID`**, because
`response.headers[...] = cid` (`api.py:1007`) is never reached. The one moment a support engineer most
needs the id is the one moment the client does not receive it. Additionally, `CORSMiddleware`
(`api.py:907-913`) sets no `expose_headers` and does not list `X-Correlation-ID` in `allow_headers`, so a
cross-origin browser client can neither read the response header nor send one. Pre-existing, not an Alpha
regression, but it bounds the value of the fix Alpha is claiming credit for.

### F-8 — All three claims I was asked to independently verify are ACCURATE (no defect; positive result)
Verified empirically, not accepted on assertion:

- **(a) `to_thread` isolation (the deliberately-unfixed finding) is real and correctly characterised.**
  EXP A: a contextvar *read* inside the offloaded function sees the caller's value; a *mutation* does not
  propagate back. So `api.py:3111`'s `set_request_context` is genuinely inert for `user_id`, while
  `current_correlation_id()` inside the thread correctly returns the middleware's id.
- **(b) `get_current_user` is genuinely different, not merely assumed different.** EXP B3: it is
  `async def`, resolved as a FastAPI dependency in the request's own coroutine with no thread hop, and its
  `user_id` stamp *is* visible to the endpoint.
- **(c) No cross-request correlation-id leakage.** EXP B5: 20 concurrent interleaved requests, each with a
  distinct client-supplied id, held its own id across an `await` boundary — 0 leaks, 0 header mismatches.
  I also confirmed the middleware's contextvar actually *reaches* the endpoint through Starlette 1.3.1's
  `BaseHTTPMiddleware` (EXP B1) — worth testing rather than assuming, given that class's documented history
  of context-propagation surprises. It works.
- **(d) Unauthenticated endpoint, no inbound header.** EXP B1: gets a freshly minted, valid id in **both**
  the response header and the endpoint's own context. This case is correct.
- I also checked the mutable-default hazard on `contextvars.ContextVar(..., default={})`
  (`ai_provenance.py:56-57`): both `set_request_context` and `case_context` always `.set()` a brand-new
  dict and never mutate in place, so the shared default is never written through. Clean.

**On the brief's question — "does leaving this unfixed undermine the correlation-id fix's own value more
than the report admits?"** No, and the distinction matters: the middleware runs in the request's own
coroutine *before* the thread hop, so the correlation half survives intact on all 11 endpoints (EXP B4
confirms the header and the endpoint context both carry the right id). What is lost is the **user_id**
half — those 11 endpoints' AI provenance and `log_action` rows carry a correct correlation_id with
`user_id=None`. That is an *attribution* gap, not a *correlation* gap. ALPHA-001 in
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` registers it properly. My only ask is that the final
report state the residual in those terms — "who triggered it is missing on 11 endpoints", not "correlation
is degraded" — because the two have very different remediation urgency.

---

## 3. Evidence

| # | Evidence |
|---|---|
| F-1 | `services/event_bus.py:297-302` (`_run`'s `except Exception: logger.error(...)`, no re-raise); `services/event_bus.py:343-369` (`emit()` → `bus.publish()`); `routers/matter_intel.py:143,153,166` (the only in-repo producers of `HEALTH_SCORE_PROMENJEN` / `ROK_KRITICAN`, both via `emit()`); `services/event_bus.py:465-512` (the retry/dead-letter path, reachable only from `dispatch_pending_events`); `migrations/073_intake_foundations.sql`'s `fail_intake_job` as the sole `DOCUMENT_JOB_FAILED` producer; repo-wide grep for `emit(`/`bus.publish(` returning only `matter_intel.py` and `event_bus.py` itself. New handler code at `services/event_bus.py:100-105`, `162-163`, `209-210`. |
| F-2 | `shared/proactive_alerts.py:32,57,73-74` (`_MAX_ATTEMPTS=3`, `0.5*(attempt+1)` → 1.5s total); `services/event_bus.py:447` (sequential per-row loop), `:380` (`DISPATCH_BATCH_SIZE=50`), `:426-431` (RPC called with `p_stale_claim_seconds=30`); `migrations/091_event_bus_atomic_claim.sql:~52-70` (`SET claimed_at = now()` once, `claimed_at < now() - make_interval(...)` reclaim predicate, no mid-batch refresh); `gunicorn.conf.py:4` (`workers = int(os.getenv("WEB_CONCURRENCY", 4))`); `api.py:829-831` (per-worker `start_dispatch_loop()`); migration 091 header "DRAFTED, NOT applied". |
| F-3 | `services/event_bus.py:388` (`MAX_DISPATCH_ATTEMPTS=5`) × `shared/proactive_alerts.py:32` (`_MAX_ATTEMPTS=3`); `shared/proactive_alerts.py:80-85` (one audit write per exhaustion); `services/event_bus.py:471` (`attempts = (row.get("dispatch_attempts") or 0) + 1`, non-atomic RMW); `services/event_bus.py:562-575` (`DispatchLoop._run` skips its sleep whenever `obradjeno > 0`, so failing rows retry back-to-back). |
| F-4 | `routers/case_dna.py:438`, `:766`, `:917`; `routers/smart_intake.py:553` (inside `_conflict_check_bg`, launched fire-and-forget at `:564`, alert title `"BLOKIRAJUĆI sukob interesa"`, `urgentnost="hitna"`); `routers/workflow.py:81` (`_notify`, 4 in-file callers); `routers/zadaci.py:124` (`_posalji_notifikaciju`) — all `await create_proactive_alert(...)` with the `bool` discarded. Contrast `routers/morning_briefing.py:748` and `routers/zakon_monitoring.py:264,544`, which do check it. |
| F-5 | `shared/proactive_alerts.py:80-85`; `services/event_bus.py:304-308` (`except RuntimeError: asyncio.run(_run())`); `services/event_bus.py:551-560` (`stop()` awaits only `self._task`). EXP C output: `C audit task completed? [] -> LOST`; EXP C2 (long-lived loop): `['audit-written']`. EXP D: `D tasks completed: 50 /50` (GC hypothesis **not** supported). Note `tests/test_program_alpha_canonical_architecture.py:226` already needs an explicit `await asyncio.sleep(0)  # let the fire-and-forget audit task run` — the test itself documents the unawaited hand-off. |
| F-6 | `api.py:1005`; `shared/ai_provenance.py:71-73`; `migrations/090_ledger_correlation_id.sql:19-20` (`ADD COLUMN ... correlation_id TEXT` on `events` and `audit_immutable`); `migrations/089_ai_provenance_extension.sql:47` (same on `ai_forensics`); `services/event_bus.py:484-487` (unsanitised `%s` interpolation of the id into a `logger.critical` line). EXP B2: `B2 header echo honored: client-supplied-123`. |
| F-7 | `api.py:1006-1008`; `api.py:907-913` (`allow_headers=["Content-Type","Authorization"]`, no `expose_headers`). EXP B6: `B6 /boom status: 500 | X-Correlation-ID present? False`. |
| F-8 | EXP A: `A VERDICT: mutation propagates back? False` / `A VERDICT: cid readable inside thread? True`. EXP B1: endpoint context correlation_id == response header, for an unauthenticated route with no inbound header. EXP B3: `{'user_id': 'user-abc', ...}` — async `Depends` stamp visible. EXP B4: `{'user_id': None, ...}` with a correct correlation_id — the `to_thread` path, exactly as claimed. EXP B5: `concurrent leaks: []`, `header mismatches: 0` across 20 interleaved requests. Code refs: `api.py:3109-3113` + its 11 `await asyncio.to_thread(_require_auth, authorization)` call sites (e.g. `api.py:3121`); `shared/deps.py:304-315`; `shared/ai_provenance.py:56-57,71-73,93-107`; `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md:10-40` (ALPHA-001, confirmed present). |

Repro scripts: `<scratchpad>/chaos1.py` (EXP A/C/C2/D), `<scratchpad>/chaos2.py` (EXP B1–B6). Both are
self-contained and re-runnable; chaos2 imports this repo's real `shared/ai_provenance.py`.

---

## 4. Risk Classification

| # | Finding | Severity | Live today? |
|---|---|---|---|
| F-1 | Re-raise rationale holds for only 1 of 3 handlers; rok/health alert failures are not dead-lettered | **High** | Yes (claim risk, not code defect) |
| F-2 | Retry backoff can exceed the 30s claim window → cross-worker duplicate dispatch | **High** | Yes (worse in the current pre-091 plain-SELECT state) |
| F-3 | 15 insert attempts / 5 audit rows per event; non-atomic `dispatch_attempts` increment | Medium | Yes |
| F-4 | `bool` discarded at 6 of 12 call sites, incl. the blocking conflict-of-interest alert | Medium | Yes (not a regression) |
| F-5 | Durable failure audit is an unawaited task; provably lost when the loop closes | Medium | Latent + on shutdown |
| F-6 | `X-Correlation-ID` client-controlled, unvalidated, lands in immutable audit and logs | Medium | Yes (route to 05/26) |
| F-7 | 500 responses carry no correlation header; header invisible/unsendable cross-origin | Low | Yes (pre-existing) |
| F-8 | All three verification targets confirmed accurate | — | No defect |

No finding in this review meets my veto bar. Specifically confirmed **absent**: unbounded/infinite retry
(dead-letter caps it), resource exhaustion via the dispatch loop, a false-success return from
`create_proactive_alert()` itself (it returns `False` honestly), and unrecoverable data loss (F-2 produces
duplicates, not loss; F-5's loss is latent and has a surviving `logger.error` companion at
`shared/proactive_alerts.py:76-79`).

---

## 5. Recommendation

### Gate state: `PARTIAL`

Per `QUALITY_GATES.md` rule 1, `PARTIAL` is **not a pass**. It is contingent on the following named,
checkable conditions:

**C1 (blocks the final report's language, F-1).** Correct the claim. The report may say
`on_document_job_failed`'s failure reaches `dispatch_pending_events()`'s retry/dead-letter mechanism. It
may **not** say that of `on_rok_kritican` / `on_health_score_promenjen` unless and until their producer
(`routers/matter_intel.py`) is moved to the durable outbox. Either fix the sentence or fix the producer —
Agent 20 does not implement either.

**C2 (blocks, F-2).** File the claim-window race as an explicit entry in
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` alongside ALPHA-001, with the ~21-row threshold stated.
The cheapest correct fix is to bound the interaction rather than remove the retry — e.g. skip the internal
backoff when called from the dispatch path, or refresh `claimed_at` per row, or lower
`DISPATCH_BATCH_SIZE` below the window. Assign to Agent 09 / Backend Engineering (18); a *different*
instance of Agent 20 re-verifies, per my charter's Forbidden section.

**C3 (non-blocking, F-4).** Decide the contract explicitly and record it: either every call site checks
the `bool`, or the docstring states that discarding it is sanctioned and that the audit row is the
system of record. Today it is neither stated nor uniform. `routers/smart_intake.py:553`'s
conflict-of-interest alert should check it regardless of what is decided for the rest.

**C4 (non-blocking, F-5).** Either `await` the audit write, or retain a module-level strong reference set
and drain it during shutdown. `logger.error` at `:76` means the loss is not fully silent today, which is
why this is a condition and not a veto.

**C5 (routed, F-6).** Hand to Agent 05 (Security) and Agent 26 (Evidence Integrity). My reliability-side
recommendation: accept the inbound header only when it parses as a UUID, otherwise mint fresh.

**Positive assessments this agent will sign.** The canonical function's own failure semantics are correct
(honest `False`, ERROR-level log, durable audit, no exception swallowed into a false success,
`CancelledError` correctly not caught by `except Exception` on 3.13). The correlation-id unification is
sound under concurrency and correct for unauthenticated requests — both verified empirically, not assumed.
The named-parameter design does structurally prevent the recurrence of the `case_dna.py`
wrong-column-names silent-failure class the module docstring cites. The retry is bounded. The three
claims I was asked to falsify all survived falsification.

---

## 6. Confidence

| Finding | Confidence | Basis |
|---|---|---|
| F-1 | **High** | Traced every producer of the two event types in the repo; the swallow at `event_bus.py:297-302` is unambiguous. Residual: a producer outside this repo (external `events` inserts) would change the picture — see Open Questions. |
| F-2 | **Medium-High** | Arithmetic is High confidence; the *frequency* is Medium — I could not measure real Supabase failure-batch sizes or per-call latency, so the ~21-row threshold is a floor derived from the deliberate sleeps alone (real RTTs make it fewer rows, not more). |
| F-3 | **High** | Direct arithmetic from two constants and a traced control flow. |
| F-4 | **High** | Read all 12 call sites. |
| F-5 | **High** for the mechanism (deterministically reproduced); **Medium** for live impact (I classify it latent and say so). |
| F-6 | **High** for the mechanism; **Medium** for severity, which is Agent 05's call, not mine. |
| F-7 | **High** — directly observed. |
| F-8 | **High** — four independent empirical confirmations on the resolved library versions. |
| Report overall | **High** on what was tested; **Medium** overall, bounded by the absence of any production-runtime observation. |

---

## 7. Open Questions

1. **Have migrations 090 and 091 actually been run?** Both carry "DRAFTED, NOT applied" headers, and
   project convention is that the founder runs migrations himself
   (`feedback_migrations`). F-2's exact shape depends on the answer: with 091 applied it is a
   claim-window expiry; without it, it is the wider plain-SELECT race Keystone Phase 4 already logged.
   Founder input required — not derivable from the repo.
2. **Is `routers/matter_intel.py` intended to stay on the in-memory `emit()` path?** If moving it to the
   durable outbox is planned, F-1 self-resolves and the re-raises become correct as written. If not, the
   two raises are permanently decorative and the report's wording must change. Product/architecture
   decision, not a reliability one — routed to Agent 17.
3. **Does any producer outside this repository insert `ROK_KRITICAN` / `HEALTH_SCORE_PROMENJEN` rows
   directly into `events`?** (An external cron, a Supabase trigger, a manual insert.) I searched the
   Python tree only. If one exists, those handlers *would* reach the dispatch retry and F-1 narrows.
4. **Is there a client-side timeout on the Supabase client?** `shared/deps.py:72-81` calls
   `create_client()` with no timeout configuration, so `create_proactive_alert`'s `asyncio.to_thread`
   inserts inherit the library default. If that default is generous, a *hung* (as opposed to *failing*)
   Supabase connection holds a default-executor thread for its full duration ×3 attempts, and F-2's window
   math becomes far worse than 1.5s/row. I did not verify the resolved postgrest/httpx default and will
   not assert one. Worth a Performance & Scalability (32) pass.
5. **Should `proactive_alerts` have a dedup key at all?** No unique constraint exists. Under the
   "insert committed but the response was lost" failure mode, the internal retry inserts a duplicate the
   old single-attempt implementations could not — a 3× amplification of that specific duplicate class.
   I could not size how often that mode occurs against Supabase and am filing it as a question rather than
   a finding, since I have no evidence it has ever happened.
6. **Is 5:1 audit-row inflation (F-3) acceptable to the metrics owners?** Mission Ledger/Atlas coverage
   percentages are computed from audit-row counts; a dead-lettering document job now contributes 5 rows.
   Routed to Agent 31 (Metrics Guardian).

---

**GATE STATE: `PARTIAL`** — conditions C1 and C2 are blocking and must be verified satisfied before the
final recommendation, per `QUALITY_GATES.md` rule 1.
