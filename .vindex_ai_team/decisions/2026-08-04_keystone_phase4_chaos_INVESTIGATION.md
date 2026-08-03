# Mission Keystone — Phase 4 Chaos Investigation (Adversarial Re-verification)

**Scope**: independent, read-only re-verification of Project Phoenix's chaos-testing pass, per Keystone's
explicit mandate not to assume Phoenix's fixes are as complete as Phoenix's own report claims. Zero code
edits, zero git commands. Method: direct source reading + grep sweeps; no throwaway scripts were needed
(static reading was sufficient to reach a confident verdict on every scenario below).

---

## AI Failure

| Scenario | Verdict | Evidence |
|---|---|---|
| Timeout / rate-limit / server error | **Protected** | `shared/llm_retry.py`'s `llm_retry` decorator (`tenacity`, `stop_after_attempt(3)`, `wait_exponential(1,8)`, retries only `RateLimitError/InternalServerError/APITimeoutError/APIConnectionError`, `reraise=True` — never swallows after exhaustion). Confirmed applied at **every** direct `chat.completions.create` call site found in the codebase: `routers/court_predictor.py` (6 sites), `routers/strategija.py`, `main.py::ask_agent` (line 2240), `routers/drafting.py` (2 sites), `drafting/router.py`, `shared/intake_classify.py`, `shared/intake_extract.py`, `services/case_pipeline.py`, `services/learning_engine.py`, `services/ambient_analyzer.py`, `services/agent_tasks/{court_portal_watcher,precedents_radar}.py`. Zero direct-call sites found unprotected. |
| Invalid JSON response | **Protected** | Every `json.loads(raw)` site checked (`routers/court_predictor.py:186,681,818,980,1189`, `routers/strategija.py:421`, `routers/drafting.py:405,742`, `main.py:2786`) sits inside an outer `try/except Exception` that converts a `JSONDecodeError` into a clean `HTTPException(500, ...)` — confirmed for `prediktuj_ishod` (except block at `court_predictor.py` ~line 224: `except Exception as e: raise HTTPException(500, f"Greška pri analizi: {str(e)}")`) and `strategija.py:430`'s dedicated `except _json.JSONDecodeError`. No path returns a fabricated 200 on malformed model output. Minor, non-blocking note: `str(e)` is echoed into the HTTP detail — low-severity info-disclosure, a Phase 6 (security) item, not a reliability failure. |
| Hallucination detection | **Partial** | `services/quality_gate.py::evaluate_draft_quality` is a real, honest anti-hallucination check for Drafting specifically: it extracts every "Član N" citation from generated text and verifies each against the actually-indexed legal corpus via `app.services.retrieve._direktan_fetch_clana` (not just trusting the model), producing `citation_score`. This gate exists **only for Drafting's staging path** (`routers/drafting.py::_stage_draft_for_review`) — Court Predictor, Strategy Engine, and `ask_agent` have no equivalent citation-verification step. |
| Low confidence handling | **Partial** | Drafting: `confidence_score = 0.6*citation_score + 0.4*completeness_score`, gated at `_APPROVAL_CONFIDENCE_THRESHOLD = 0.85` before a draft can be lawyer-approved/promoted to Pinecone (`routers/drafting.py:1076`, explicit rejection message at line ~1094 if below threshold). No equivalent numeric confidence gate found for Court Predictor's percentage outputs or Strategy Engine's analyses — they return whatever the model produces without a comparable "are we sure enough" check. |
| Partial completion | **Protected** (for the one case tested) | Upload's 3-parallel-GPT-call background analysis: each of the 3 calls has its own try/except: a failure in one does not corrupt or block the other two, confirmed by Phoenix and unchanged this pass. |

**Net**: AI-failure *transport* concerns (timeout/rate-limit/malformed-JSON) are uniformly solved codebase-wide via one shared mechanism — the strongest category in this investigation. AI-failure *quality* concerns (hallucination/low-confidence) are solved rigorously but only for one of several AI features (Drafting) — this is a real, honestly-scoped gap, not a false claim by Phoenix (Phoenix's own report never claimed universal confidence-gating; it's called out here for Keystone's Phase 5 AI Quality Validation to weigh).

---

## Database Failure

| Scenario | Verdict | Evidence |
|---|---|---|
| Constraint violation / duplicate insert | **Protected** where touched by Mission Ledger/Phoenix | `shared/audit_immutable.py::_is_unique_violation` (Postgres 23505 check) reused correctly by Phoenix's `routers/copilot.py::_handle_akcija_povezi_klijenta` TOCTOU fix — re-read and confirmed still intact, still narrow (checks the specific Postgres error code, not a bare `except`). |
| "Try wide, fall back narrow" schema fallback | **Protected** | `_is_missing_column_error()` (Postgres 42703 check) re-confirmed used consistently in `routers/case_dna.py::_emit_genome_event`, `api.py::kreiraj_predmet`, `security/ai_forensics.py::log_provenance_from_wrapper` — all 3 normalized copies re-read, no bare `except Exception:` regression found. |
| Deadlock | **Protected** (for the one real contended row-lock use) | `claim_intake_job`'s `SKIP LOCKED` (migration 073) makes classic deadlock structurally impossible for that path — re-confirmed unchanged. |
| Connection loss / lost connection generally | **Not independently re-traced this pass** — Phoenix's own db_transaction_chaos investigation is the evidence base; this pass did not find reason to doubt it, but did not re-derive it from scratch either. |

---

## Event Failure — **the headline new finding of this investigation**

| Scenario | Verdict | Evidence |
|---|---|---|
| Handler crash (detection) | **Protected** | Phoenix's fix re-read in full (`services/event_bus.py:302-323`): `publish_async()` correctly inspects `asyncio.gather(..., return_exceptions=True)`'s results and re-raises if any handler failed, while still running every handler to completion. All 6 handlers re-raise after logging. Confirmed correct, not just present. |
| Retry exhaustion | **Protected** | `MAX_DISPATCH_ATTEMPTS = 5` dead-letter cap (`dispatch_pending_events`, `event_bus.py:378,428-451`) re-confirmed: on exhaustion, marks `dispatched_at` (stops the poller) but tags `last_error` with an explicit `"DEAD_LETTER after N attempts: ..."` prefix and logs `logger.critical` — genuinely not a silent vanish. |
| **Duplicate event (redelivery)** | **Vulnerable — new finding, not covered by Phoenix's fix** | `dispatch_pending_events()` (`event_bus.py:419-421`) does `await bus.publish_async(event)` **then** `await _mark_dispatched(supa, row_id)` as two separate awaits inside the *same* `try` block. If `publish_async` succeeds in full (every handler already ran and wrote its side effects) but `_mark_dispatched`'s own DB write then fails (transient network blip, or a process crash landing exactly between the two awaits), the exception lands in the **same** `except Exception as exc:` block that handles genuine handler failures (`event_bus.py:423`) — the row's `dispatched_at` stays `null`, so the *next* poll tick (3s later) fetches the same row again and calls `bus.publish_async(event)` a **second time**, re-running every handler for an event that already fully executed once. None of the 4 handlers subscribed to non-`PREDMET_KREIRAN` event types are idempotent against redelivery: `on_rok_kritican`/`on_health_score_promenjen`/`on_document_job_failed` unconditionally `.insert()` a new `proactive_alerts` row every call (→ a lawyer would see a duplicate deadline/health-score/failed-document alert), and `on_genome_updated` unconditionally `log_action`s a new `audit_immutable` row (→ a misleading hash-chain entry claiming the Genome was refreshed twice when it was refreshed once). This is exactly Keystone's "duplicate event" scenario, and Phoenix's fix — which targeted failure *detection*, not delivery *idempotency* — does not close it. **One event type is confirmed safe**: `PREDMET_KREIRAN`'s handler (`on_predmet_kreiran` → `run_case_pipeline`) is explicitly marker-based idempotent per step (documented at `api.py:3168` and `services/case_pipeline.py`'s own module docstring: "Every step checks for an existing marker before running (idempotency)") — a duplicate dispatch of this one event type produces no duplicate rows, by design and by direct code confirmation. |
| Delayed event | **Protected (bounded)** | `DispatchLoop`'s 3s poll interval bounds worst-case delay; no evidence of unbounded queuing. |
| Genuine duplicate event from a retried client HTTP request (e.g. double-click "create predmet") | **Not covered — no idempotency key** | `api.py`'s predmet-creation endpoint (`api.py:3143` area) has no `Idempotency-Key`/dedup check on the insert itself — a client-side retry of the same POST (e.g. a flaky network causing a duplicate submit) would create two `predmeti` rows and two `PREDMET_KREIRAN` durable events, each running its own full case pipeline. This is a distinct gap from the event-bus-internal one above (it's at the HTTP-request layer, not the outbox layer) — grep confirmed zero occurrences of "Idempotency-Key" or comparable dedup logic anywhere in `api.py`. |

**Severity assessment for the risk register**: Medium, not Critical — the redelivery window requires a second, independent failure (the mark-dispatched write itself failing) landing in the narrow gap after a fully-successful handler run; it is not triggered by ordinary handler bugs (which Phoenix's fix now correctly prevents from reaching this state at all, since a genuine handler failure means `publish_async` raises *before* `_mark_dispatched` is ever reached, so the row correctly stays undispatched for a real retry, not a "already succeeded, redelivered anyway" duplicate). The consequence (duplicate alert, duplicate audit line) is a trust/annoyance issue, not data loss or a false success at the business-outcome level.

---

## Storage Failure

| Scenario | Verdict | Evidence |
|---|---|---|
| Ghost document (DB insert fails after Pinecone succeeds) | **Protected, re-confirmed intact** | `api.py` upload path re-read in full: `if not _dok_id: raise HTTPException(500, "Dokument je otpremljen, ali nije uspešno sačuvan...")` still present and unchanged, immediately after the `predmet_dokumenti` insert attempt, before any AI analysis runs. |
| Pinecone vector orphaned on the same failure | **Still open, unchanged, correctly self-reported by Phoenix** | The same code block's own comment states cleanup "nije implementiran ovde" — re-confirmed true, not a regression, not mischaracterized by Phoenix. |
| Upload interrupted / missing file / corrupted document | **Not independently re-traced this pass** — no new evidence gathered beyond Sentinel's original finding, which Phoenix also left untouched. |

---

## Worker Failure

| Scenario | Verdict | Evidence |
|---|---|---|
| Dispatch loop crash mid-tick | **Protected** | `DispatchLoop._run()` (`event_bus.py:511-524`) wraps its call to `dispatch_pending_events()` in its own `try/except Exception: logger.exception(...); did_work = False` — an unexpected error in one poll tick is logged and the loop continues to the next tick rather than dying silently. |
| Dispatch loop crash mid-batch (between rows) | **Protected (no data loss)**, though see the redelivery finding above for the "already-succeeded-row" edge case | Since `dispatched_at` is only set after each row's own processing completes, an abort mid-batch leaves the remaining rows untouched (`dispatched_at` still `null`) and they are simply picked up whole on the next 3s tick — no row is skipped or lost. |
| Smart Intake worker/job crash | **Protected** | `intake_jobs`' `max_attempts`/backoff/dead-letter pattern (migration 073) plus `intake_worker_heartbeat` table for health-check visibility — unchanged, re-confirmed present, not re-derived from scratch this pass (Phoenix's own migration_remainder investigation is the deeper evidence base here). |

---

## Gaps Phoenix missed or mischaracterized

1. **Anthropic — mischaracterized as "not independently re-verified" when it should be "not applicable."** Phoenix's report lists Anthropic in its Failure Inventory as an unverified external dependency. This investigation ran `grep -rln "anthropic|Anthropic"` and `grep -i anthropic requirements.txt` and `grep -rln "claude-3|claude-2|ANTHROPIC_API_KEY"` across the entire repository (excluding tests/pycache): **zero matches, all three searches**. There is no Anthropic SDK dependency, no API key variable, and no model-string reference anywhere in this codebase. "Anthropic" in the mission briefs' enumerated system list appears to be boilerplate (or forward-looking) that does not correspond to anything actually built. Recommendation for the final Keystone report: mark Anthropic **N/A (not integrated)**, not "unverified" — an important distinction, since "unverified" implies a real gap in test coverage where none exists.

2. **The Event Bus redelivery/idempotency gap (detailed above)** — genuinely new, not present in Phoenix's report at all. Phoenix's own investigation focused entirely on failure *detection* (the `return_exceptions=True` swallowing bug) and correctly fixed that; it did not separately examine whether the dispatch-then-mark sequence is atomic, or whether the 4 non-`PREDMET_KREIRAN` handlers are safe under at-least-once delivery. This is the correct kind of finding Keystone's adversarial mandate exists to surface — a defect in the *shape* of a fix that was otherwise entirely correct in what it set out to do.

3. **HTTP-layer request-retry duplication (predmet creation)** — a smaller, related-but-distinct gap: no idempotency key on the client-facing create-predmet endpoint. Not previously flagged by any of the 5 prior missions this session (Sentinel/Atlas/Ledger/Migration/Phoenix all focused on server-side event/audit/provenance plumbing, not client-retry semantics).

---

## Summary for the parent (Mission Keystone)

**New vulnerability found**: Event Bus's `dispatch_pending_events()` performs handler-execution and mark-dispatched as two non-atomic steps; if the mark-dispatched write itself fails after a fully successful handler run, the same event redelivers on the next poll and re-executes non-idempotent handlers, producing duplicate `proactive_alerts` rows or a duplicate `audit_immutable` entry. Severity: Medium (narrow trigger window, no data loss, trust/annoyance-level consequence, not a false-success-at-business-outcome-level defect). `PREDMET_KREIRAN` is confirmed exempt (marker-based idempotent pipeline). A second, smaller, related gap: no idempotency key on the predmet-creation HTTP endpoint itself, so a client-side request retry can create duplicate predmet rows independent of the event-bus issue.

**Phoenix's previously-unverified items, resolved this pass**: (1) Anthropic — confirmed N/A, zero usage anywhere in the codebase, Phoenix's framing corrected from "unverified" to "not integrated." (2) AI invalid-JSON-response handling — confirmed Protected across all checked call sites (clean 500, no false success). (3) Hallucination/low-confidence handling — confirmed real and rigorous but Drafting-only, not universal; flagged for Phase 5. File Storage/upload-interrupted/corrupted-document and general DB connection-loss were not independently re-traced this pass (time-boxed scope) — no new evidence either confirming or contradicting Phoenix's prior characterization.
