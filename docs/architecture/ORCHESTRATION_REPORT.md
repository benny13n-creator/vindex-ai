# Orchestration Report

**Mission:** Project Synapse, 2026-08-03. Verification record for every change implemented this
mission, per the mandatory checklist: existing APIs reused, authorization preserved, billing
preserved, tenant isolation preserved, tests passing, zero regression, Beta Critical Path preserved.

---

## Change 1: `services/risk_engine.py::calculate_procesni_rizik` — additive return field + bug fix

**What**: added `kriticni_rocista` (the actual critical-hearing rows) to the function's return dict,
alongside the pre-existing `kriticni_rokovi` count. Also fixed a real, pre-existing bug in the date
comparison (naive-vs-aware datetime subtraction, silently swallowed, made every plain-date-string
hearing invisible to both `predstojeći_rokovi` and `kriticni_rokovi`).

- **Existing APIs reused**: none needed — this is the deterministic core the platform already treats
  as its "one algorithm" (Core Consolidation Sec 1.2).
- **Authorization / billing / tenant isolation**: not applicable — this function takes no user
  identity, no auth context; it's a pure function over data already fetched by its callers, who
  already enforce their own isolation.
- **Regression risk**: the return dict gained one new key; no existing key was renamed or removed.
  Confirmed no test in the repo asserts exact dict equality against this function's output (checked
  `tests/test_case_pipeline.py`, the only other consumer's test file).
- **Tests**: 3 new (`tests/test_synapse_health_deadline_events.py`), plus all 12 pre-existing
  `tests/test_matter_intel.py` tests re-run and confirmed passing unchanged.

## Change 2: `routers/matter_intel.py` — emit `HEALTH_SCORE_PROMENJEN` and `ROK_KRITICAN`

**What**: `get_matter_intel` now fires a non-blocking background task
(`_maybe_emit_health_and_deadline_events`) after computing risk, which emits both events through the
existing `services/event_bus.py::emit()` — the exact same function `PREDMET_KREIRAN` already uses in
production.

- **Existing APIs reused**: 100% — `emit()`, `EventType`, and both handlers (`on_health_score_promenjen`,
  `on_rok_kritican`) already existed and were already registered; this change adds zero new event-bus
  code.
- **Authorization preserved**: the background task receives `uid` from the already-authenticated
  request (`user["user_id"]`, derived from the JWT by `Depends(get_current_user)` on the endpoint) —
  no new authorization surface.
- **Billing preserved**: `get_matter_intel` already consumes a `matter_intel` credit exactly as it did
  before this change; the new emit calls consume no additional credit (the handlers themselves don't
  bill).
- **Tenant isolation preserved**: the dedup check (`proactive_alerts.eq("predmet_id", predmet_id)`)
  and the emit itself both use the `predmet_id`/`uid` already validated by `get_matter_intel`'s own
  ownership check earlier in the same function — no new lookup that could cross a tenant boundary.
- **Regression risk mitigated by design**: this endpoint runs on EVERY case-open
  (`matter_intel_load()` auto-fires from `pred_select()`). Emitting unconditionally would create a new
  duplicate proactive alert on every page view — a real, considered risk, not an oversight. Mitigated
  by checking for an existing UNREAD alert of the same type before emitting; explicitly tested (see
  below).
- **Tests**: 6 new (`test_emits_health_score_event_when_low_and_no_existing_alert`,
  `test_does_not_emit_health_score_event_when_score_is_healthy`,
  `test_does_not_emit_health_score_event_when_unread_alert_already_exists` — the core dedup guard —
  `test_emits_rok_kritican_event_with_correct_payload`,
  `test_does_not_emit_rok_kritican_when_no_critical_hearings`, `test_emit_failure_does_not_raise`).

## Change 3: `routers/copilot.py::_handle_analiza_predmeta` — reads Case Genome

**What**: the `predmeti` select now also fetches `case_dna`; if present and error-free, a compact
summary is folded into the same context string this handler already builds for its one existing GPT
call.

- **Existing APIs reused**: 100% — no new endpoint, no new GPT call, no new table. Reads a column that
  already exists on a row this function already fetches.
- **Authorization / tenant isolation preserved**: the select still carries `.eq("id", predmet_id).eq("user_id", user_id)` unchanged — the added column doesn't change the query's scoping.
- **Billing preserved**: exactly one GPT call before, exactly one GPT call after — no new cost.
- **Tests**: 3 new, including explicit backward-compatibility coverage for the (currently most common)
  case where `case_dna` doesn't exist yet, and for a Genome that failed to generate (`greska` set) —
  confirming a broken Genome is never surfaced as if it were real signal.

## Change 4: `routers/precedenti.py::get_precedenti` — reads Case Genome

**What**: same pattern as Change 3 — the `predmeti` select gains `case_dna`; a compact summary is
appended to the existing `ctx_predmet` string.

- **Existing APIs reused / billing / authorization / tenant isolation**: identical reasoning to Change
  3 — additive context only, no restructuring, no new cost, no new scoping.
- **Tests**: 2 new, covering both the enriched and unenriched cases.

---

## Full-suite verification (final gate, run after all four changes)

**2329 passed, 1 skipped, 0 failed** — 14 new tests total across this mission
(`test_synapse_health_deadline_events.py` ×9, `test_synapse_copilot_genome_context.py` ×3,
`test_synapse_precedenti_genome_context.py` ×2), zero regressions to the 2315 tests that existed
before this mission started tonight.

## Beta Critical Path preserved

None of the 4 changes touch any endpoint's request/response contract in a breaking way — every
change is either a purely-additive return field, a non-blocking background task, or additive prompt
context. The workflows traced in `docs/product/LAWYER_DAY_REPORT.md` and
`docs/product/BETA_LOCKDOWN_REPORT.md`'s Beta Acceptance Test are unaffected: case-open, document
upload, AI Briefing, Firm Brain, and Copilot chat all still return the same response shape they did
before, with richer content where Genome data exists.

## What was deliberately NOT implemented this mission (see Cognitive Islands Report for full detail)

A new `DOCUMENT_JOB_FAILED` handler, Outcome Intelligence / Judge-Court Profiler reading Case Genome,
writing Smart Intake's extracted judge/opponent entities onto `predmeti.tuzilac`/`tuzeni`, and any
fix to the `knowledge_profiles` phantom-data-source problem — each requires either new logic (outside
this mission's "prefer orchestration" charter) or a founder decision, and each is documented precisely
rather than attempted speculatively.
