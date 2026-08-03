# Nexus Orchestration Report

**Mission:** Project Nexus, 2026-08-03. Verification record for every change implemented this mission —
mirrors Project Synapse's own `ORCHESTRATION_REPORT.md` format for consistency across this engagement.

---

## Change 1: `routers/ccc.py` — eliminate the duplicate health-score formula + fix the missing-column bug

**What**: `dok_count_r`'s select gained `tip_dokaza` (previously absent, meaning the "missing
documents" smart-chip feature always showed every expected document type as missing regardless of
what was actually uploaded — a live, silent bug). `_compute_health()` — a local reimplementation of
Matter Intelligence's exact formula, with a hardcoded `nedostajuci_count = 0` that caused silent
divergence under the identical field name, plus its own independently-duplicated copy of the
naive/aware datetime bug — was deleted entirely; `get_ccc` now calls
`services/risk_engine.py::calculate_procesni_rizik` directly, the same function `routers/matter_intel.py`
uses.

- **Existing APIs reused**: 100% — `calculate_procesni_rizik` already existed and was already the
  canonical source for this exact computation elsewhere in the app.
- **Duplicate logic removed**: `_compute_health` (29 lines) deleted, not deprecated-in-place.
- **Authorization / tenant isolation preserved**: the endpoint's own ownership check
  (`.eq("id", predmet_id).eq("user_id", uid)`) is unchanged; the new function call receives only
  already-scoped data this endpoint already fetched.
- **Tests**: 11 tests in `tests/test_ccc.py` (2 new: a select-call-argument spy proving `tip_dokaza` is
  requested, and a byte-for-byte comparison confirming CCC's `health_score`/`nedostajuci` now exactly
  match `calculate_procesni_rizik`'s own output for identical input — the whole point of removing the
  duplicate). 2 pre-existing tests that imported the now-deleted `_compute_health` directly were
  rewritten to exercise the same guarantees (score drops with critical deadlines; score stays in
  [0,100]) through `get_ccc`'s real response instead.

## Change 2: `routers/zadaci.py::ai_analiziraj_predmet` — ground AI task creation in the canonical risk engine

**What**: the endpoint now computes `services/risk_engine.py::calculate_procesni_rizik` +
`identify_case_problems` from data it already gathers (extended with 2 more parallel queries —
`predmet_dokazi`, `rocista` — and `tip_dokaza` added to its existing document query), and folds the
deterministic findings into the GPT prompt as ground truth, with an explicit instruction not to
re-guess document completeness from raw filenames. The heuristic fallback path (used when the GPT call
itself fails) was updated the same way — it now creates tasks from the same deterministic finding
instead of a cruder, separate `if not docs` check.

- **Existing APIs reused**: 100% — `calculate_procesni_rizik`/`identify_case_problems` already existed;
  no new deterministic logic was written.
- **Authorization / billing / tenant isolation preserved**: unchanged — same `uid`/`predmet_id`
  scoping on every query, same single `UsageService.consume(..., "zadaci_ai")` call site, unchanged.
- **What was NOT changed**: the endpoint's unique value (inactivity detection, unbilled-amount
  detection) — neither is covered by `identify_case_problems`, so both remain GPT-judged exactly as
  before. This is deliberately a grounding fix, not a full replacement of the endpoint's reasoning.
- **Tests**: 3 new (`tests/test_nexus_zadaci_ai_grounding.py`) — confirms the deterministic section
  appears in the GPT prompt when real findings exist, confirms it's correctly absent for a clean case,
  and confirms the GPT-failure fallback path uses the same deterministic source.

## Change 3: `static/vindex.js::_voice_refresh_case_dna` — fix the false-success-toast on Genome failure

**What**: Case Genome's refresh backend correctly returns HTTP 200 with `{"greska": "..."}` on a
genuine LLM failure (a deliberate fail-soft design) — the frontend never checked for this before
choosing which toast to show, so a lawyer would see a green "Procena ažurirana" success notification
and then watch the panel silently show nothing. Now explicitly checks `dna.greska` first and shows an
honest error toast instead.

- **Existing APIs reused**: no backend change at all — pure frontend fix, reusing the already-correct
  `_caseDnaRender` function's own `dna.greska` check (which was already correct) and the existing
  `_friendlyErr`/`showToast` helpers.
- **Tests**: none possible — this repo has no frontend test harness (confirmed repeatedly across this
  engagement). Verified via `node --check` (syntax validity) and manual trace of the exact response
  shape read directly from `routers/case_dna.py`'s refresh endpoint before writing the fix.

---

## Full-suite verification (final gate)

**2334 passed, 1 skipped, 0 failed** — 8 new tests total this mission (5 in `test_ccc.py`'s delta, 3 in
the new `test_nexus_zadaci_ai_grounding.py`), zero regressions to the 2329 tests that existed before
this mission began (2329 was Project Synapse's own final count, earlier the same night).

## Beta Critical Path preserved

No endpoint's request/response contract changed in a breaking way. `get_ccc`'s response shape is
unchanged (`health_score`/`nedostajuci` fields still present, now correct rather than silently wrong).
`ai_analiziraj_predmet`'s response shape is unchanged. The Genome-refresh frontend fix only changes
which toast text appears on an already-rare failure path — no change to the success path any existing
Beta Critical Path scenario exercises.
