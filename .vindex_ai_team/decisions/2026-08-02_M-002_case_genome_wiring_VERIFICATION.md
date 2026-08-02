# M-002 — Case Genome Wiring Verification

**Mission:** `.vindex_ai_team/MISSION_BOARD.md`, M-002. Read-only investigation, no code changed.
**Method:** every claim below re-derived from current code (2026-08-02), not from the 2026-07-21
finding's own text or any memory file.

---

## 1. Summary verdict

**Partially safe to build on — better than the 2026-07-21 finding described, but with one real gap
still open.** The core refresh mechanism (background regeneration after a new document) is live on
**both** major upload paths, and the specific output fields Beta Critical Path scenario #5 needs
(`zakljucak`, `pravna_teorija`, `dokazi_rang`, `kontradikcije`, `najslabija_tacka`/`upozorenja`,
`strategija`, `nedostaje`) are genuinely produced and genuinely consumed by two real downstream
features (`case_intelligence.py`, `cio.py`). The 9-step **Case Pipeline** (a distinct system from
Genome refresh — see below) now auto-fires on the plain `/api/predmeti` case-creation route, fixed
2026-07-22 per its own code comment (one day after the finding). **What's still true and blocking**:
`/api/intake/kreiraj` — the primary AI-assisted case-creation endpoint — does **not** trigger the
Case Pipeline, and of the Event Bus's 9 original event types, only 2 (`PREDMET_KREIRAN`,
`GENOME_UPDATED`) are ever actually emitted anywhere; the other 7 either have no handler, are never
emitted, or both. Sprint 4 work can proceed on Genome's *output* safely; it should not assume the
Case Pipeline or the wider event bus are reliable general-purpose infrastructure yet.

---

## 2. Per-claim findings

### 2.1 — "Case Pipeline (9-step) never auto-fires"
**Status: PARTIALLY TRUE — fixed for one entry point, still true for the primary one.**

The 9-step pipeline is real: `services/case_pipeline.py` — `_step_analiza_dokumenata`,
`_step_auto_linking`, `_step_ekstrakcija_rokova`, `_step_kalendar`, `_step_strategija`, `_step_hcc`,
`_step_risk_snapshot`, `_step_copilot_preporuka`, `_step_istorija` (9 steps, confirmed against
`tests/test_case_pipeline.py`'s own per-step test sections). Manually triggerable via
`POST /api/predmeti/{predmet_id}/pipeline` (`routers/case_pipeline.py:25-62`).

**Auto-fire, found live:**
- `api.py:3242-3268` (`POST /api/predmeti`, the plain "+ Novi predmet" flow) — emits
  `EventType.PREDMET_KREIRAN` via the event bus, whose registered handler
  (`services/event_bus.py:98-107`, `on_predmet_kreiran`) calls `run_case_pipeline` directly. The
  code comment at `api.py:3259-3262` cites this as a **2026-07-22** fix ("D3,
  `VINDEX_2_1_ARCHITECTURE_ROADMAP.md`") — one day after the 2026-07-21 finding. **This part of the
  original claim is fixed, and the fix is dated to right after the finding that identified it.**
- `routers/intake.py:775-783` (`POST /api/intake/from-template`) — calls `run_case_pipeline`
  directly via `asyncio.create_task`, not through the event bus. Also live.

**Auto-fire, confirmed still absent:**
- `routers/intake.py`'s `intake_kreiraj` (`POST /api/intake/kreiraj`) — the primary, most-used
  AI-assisted case-creation endpoint (per this session's Bojan Gap Analysis) — has **no** call to
  `run_case_pipeline` and does not emit `PREDMET_KREIRAN`. Grepped the full file: the only
  `run_case_pipeline` reference is inside `post_from_template`.
- `POST /api/intake/bulk-import` — same file, also no pipeline trigger.
- `routers/smart_intake.py`'s finalize endpoint — triggers a Genome refresh (see 2.5) but not the
  9-step Case Pipeline; these are two different systems with two different triggers, easy to conflate.

**Recommendation (not implemented):** add the same `emit(EventType.PREDMET_KREIRAN, ...)` call (or a
direct `run_case_pipeline` call, matching the from-template pattern) to `intake_kreiraj` — this is
the highest-traffic case-creation path per this session's own gap analysis and is the one still
missing it.

### 2.2 — "7/9 event types dead"
**Status: WORSE than described, by the most literal reading — re-counted independently.**

`services/event_bus.py:31-50` defines exactly 9 original event types (excluding 3 newer, separate
Smart-Intake-specific ones added later): `PREDMET_KREIRAN`, `DOKUMENT_UPLOADOVAN`, `ROK_DODAN`,
`ROK_KRITICAN`, `ROCISTE_ZAKAZANO`, `STRATEGIJA_GENERISANA`, `ANALIZA_ZAHTEVANA`,
`HEALTH_SCORE_PROMENJEN`, `GENOME_UPDATED`.

| Event type | Handler registered? | Ever emitted (outside tests)? | Live? |
|---|---|---|---|
| `PREDMET_KREIRAN` | Yes (`:198`) | Yes — `api.py:3265` | **LIVE** |
| `GENOME_UPDATED` | Yes (`:201`) | Yes — written directly to durable outbox, `routers/case_dna.py:516` | **LIVE** |
| `DOKUMENT_UPLOADOVAN` | Yes (`:199`) | **No** — zero emit call sites found repo-wide | Dead (handler orphaned) |
| `ROK_KRITICAN` | Yes (`:197`) | **No** — zero emit call sites found repo-wide | Dead (handler orphaned) |
| `HEALTH_SCORE_PROMENJEN` | Yes (`:200`) | **No** — zero emit call sites found repo-wide | Dead (handler orphaned) |
| `ROK_DODAN` | No | No | Dead |
| `ROCISTE_ZAKAZANO` | No | No (a same-named but unrelated `DecisionType` enum value exists in `services/decision_log.py:29` — different enum, not this one) | Dead |
| `STRATEGIJA_GENERISANA` | No | No | Dead |
| `ANALIZA_ZAHTEVANA` | No | No | Dead |

**2 of 9 fully live, 7 of 9 dead** — matches the original ratio, but the original finding's implicit
framing ("dead" = no handler) undercounts: 3 of the 7 dead ones (`DOKUMENT_UPLOADOVAN`,
`ROK_KRITICAN`, `HEALTH_SCORE_PROMENJEN`) have real, non-trivial handlers already written (decision
logging, proactive alerts) that simply have nothing to trigger them — closer to "wired at one end
only" than "not built." Recommendation (not implemented): these 3 are the cheapest wins if this
infrastructure gets revisited — the handler-side work is already done, only the emit call sites are
missing.

### 2.3 — "Zero connection to Firm DNA/Learning/Confidence/matter_intel risk"
**Status: STILL TRUE for the specifically named modules; PARTIALLY FALSE if read as "nothing outside
Genome ever consumes it."**

- `services/learning_engine.py`, `services/confidence_calibrator.py`, `services/confidence_auditor.py`,
  `routers/matter_intel.py` — grepped each directly for `genome`/`case_dna`: **zero matches in all
  four.** The specific modules named in the original claim genuinely have no connection today.
- **However**, two other, real, live features do read Genome directly from the `predmeti.case_dna`
  column: `routers/case_intelligence.py:88,198-263` (the cross-module "Case Intelligence Briefing,"
  which aggregates Genome + lessons + knowledge profile + communication profile + court predictor +
  decision log into one AI-generated recommendation) and `routers/cio.py:114-167,195` (the
  portfolio-level CIO view, whose own docstring at `:40` claims it also uses "Firm DNA" — present in
  the same file, not independently verified as a real data source in this pass, flagged as
  **unverified**, not confirmed, since this investigation's time did not extend to tracing that
  specific claim to its data source).
- **Correction to a docstring, found and worth noting**: `routers/case_dna.py:6-14`'s own header
  comment already states, in the present tense, that this exact gap (`case_pipeline.py`,
  `learning_engine.py`, confidence calibrator having zero Genome references) was **found and
  corrected as a false claim by "forensic audit isti dan"** — i.e., this specific absence is already
  documented as a known, accepted, in-scope limitation (not a bug nobody noticed), per
  `docs/architecture/VINDEX_CORE_CONSOLIDATION.md`. The 2026-07-21 finding and this file's own
  self-correction appear to be the same event described from two angles.

### 2.4 — `health_index` dead field bug
**Status: COULD NOT LOCATE — likely already fixed by removal, not independently confirmable as
"still true."**

Grepped `case_dna.py` directly for `health_index`: zero matches. `routers/health_index.py` exists but
is a **separate, unrelated feature** (a portfolio/office-level "health" dashboard, gated by a
`PermissionService.require("health_index")` **entitlement name** — confirmed via
`migrations/064_feature_registry.sql` etc., where "health_index" is a subscription-tier feature key,
not a Genome data field). Searched for renamed variants (`zdravlje_predmeta`, `predmet_zdravlje`,
`case_health`) — no matches. **Conclusion: either the field was removed since 2026-07-21 (the
simplest explanation, consistent with the "dead field" diagnosis — deleting a field that computes
nothing is a legitimate fix), or the original finding referred to something under a name not
found by this pass's search terms. This claim cannot be confirmed as still true, and no current
evidence contradicts it having been resolved.**

### 2.5 — Genome's promised output fields, reachability
**Status: FIXED / confirmed genuinely reachable, not just present in a prompt template.**

`zakljucak`, `pravna_teorija`, `dokazi_rang`, `kontradikcije`, `najslabija_tacka`, `upozorenja`,
`strategija`, `nedostaje` are all read back from the stored `case_dna` JSON by two independent real
consumers (`case_intelligence.py`, `cio.py` — see 2.3), which is strong evidence the generation path
actually produces them, not just that the prompt asks an LLM to. The refresh trigger that produces
this object is confirmed to fire automatically (2.6) rather than requiring a manual admin/debug call.

### 2.6 — Refresh trigger(s)
**Status: BETTER than assumed — live on two paths, not one.**

- `routers/smart_intake.py:593-602` — `_run_genome_background` fires ~3s after Smart Intake's
  finalize links a document. Confirmed still present.
- **Newly confirmed, not previously checked this session**: `api.py:4333-4346` — the **older**
  `/api/predmeti/{predmet_id}/upload` auto-analyze endpoint **also** fires `_run_genome_background`
  (same function, `trigger="upload_trigger"`), 3 seconds after a document is classified. So Genome
  does **not** go stale for documents added via the older upload path — both major upload paths
  refresh it.

---

## 3. Newly found (not in the original 2026-07-21 finding)

- The `EventBus`'s durable-outbox dispatch loop (`services/event_bus.py::DispatchLoop`) — the file's
  own comment records a past founder critique that this was "infrastructure that exists but isn't
  used." **That critique is now stale**: `api.py:823-835` confirms `start_dispatch_loop()` is called
  on FastAPI startup (and `stop_dispatch_loop()` on shutdown), alongside the Smart Intake worker. The
  outbox dispatch loop is genuinely running in production today, polling every 3 seconds
  (`_DISPATCH_POLL_INTERVAL_S`).
- `intake_kreiraj` (not `post_from_template`) is the specific, single highest-value place to add the
  missing `PREDMET_KREIRAN` emit — the Bojan Workflow Gap Analysis (this same session) identified
  `intake_kreiraj` as the primary AI-assisted case-creation flow, more central than the template path
  that already has the pipeline wired.
- `routers/cio.py`'s "Firm DNA" claim (docstring `:40`) is unverified, not confirmed, by this pass —
  flagged for a future, narrower check rather than assumed true or false.

---

## 4. Recommended disposition

**M-002: DONE.** Purely investigative per its own Mission Board scoping; the current state is now
known with evidence, regardless of which parts of the original finding held up.

**Recommend adding a new, narrowly-scoped follow-on mission to the board** (not implemented here,
per this mission's read-only constraint):

> **M-013 (proposed) — Wire `intake_kreiraj` into the Case Pipeline / Event Bus**
> Priority: after M-003 (Search Table Mismatch), before M-004 (chronology — larger, unrelated).
> Dependencies: none.
> Complexity: Small — the pattern already exists verbatim in `post_from_template`
> (`routers/intake.py:775-783`); this is copying an established, working pattern to one more call
> site, not new design.
> Completion criteria: `POST /api/intake/kreiraj` triggers the 9-step Case Pipeline in the background
> (either via `emit(EventType.PREDMET_KREIRAN, ...)` matching `api.py:3265`'s pattern, or a direct
> `run_case_pipeline` call matching `post_from_template`'s pattern — either is consistent with
> existing conventions); a regression test confirms the pipeline actually runs after a case is
> created via this specific endpoint (the exact scenario this investigation found missing).

No other remediation is recommended as urgent — the 7 dead event types are a real gap but not
currently blocking any named Beta Critical Path scenario, and are cheaper to revisit later than to
speculatively wire now without a concrete consumer waiting on them.
