# Tau 007 Handover — Rolling Out the Canonical Context Migration Factory

Program Tau, Master Sprint 006 built and proved the Factory: `docs/tau/CANONICAL_CONTEXT_FACTORY.md` (the
pattern), `docs/tau/MIGRATION_TEMPLATE.md` (the operational checklist), 1 real migration (`hearing_cc.py`,
`docs/tau/HEARING_CC_MIGRATION_REPORT.md`), and 3 simulations (`case_commander.py`, `digital_twin.py`,
`zadaci.py`, `docs/tau/FACTORY_CERTIFICATION.md`). This is the priority-ordered handover for whichever
sprint rolls the Factory out next.

## Two migration shapes exist now, not one — pick the right template per module

Phase 7's simulation found the Factory covers 2 genuinely different migration shapes, and a future sprint
should classify each target module before starting:

1. **Context-injection** (`hearing_cc.py`, `case_intelligence.py`, `court_predictor.py`,
   `digital_twin.py`): the module fetches raw rows and builds a prompt; migration means routing that fetch
   through `build_case_context()` and adding whatever canonical fields the module didn't have before.
2. **Duplicate-computation-elimination** (`case_commander.py`, `zadaci.py::ai_analiziraj_predmet`): the
   module already independently calls `services/risk_engine.py`/`shared/gap_engine.py`/
   `shared/case_readiness.py` — the SAME functions `build_case_context()` calls internally — against its
   own separately-fetched data. Migration here means replacing that duplicate call chain with
   `build_case_context()`'s own already-computed `readiness`/`missing_evidence`/`contradictions` fields,
   which is lower-risk in one sense (the values should already match, no new grounding gap to close) but
   needs its own proof that they DO match before cutting over (write a test asserting the 2 independently-
   computed readiness values agree, on real-shaped data, BEFORE deleting the duplicate — if a next sprint
   finds a real drift here, don't fold it into the migration, escalate it as a plain bug first, per the
   Legal Reasoning Engineer's own standing "any conclusion without a provable basis is a bug" discipline).

## Priority order for the next rollout sprint

1. **`case_commander.py`** — highest value: eliminates a genuine drift risk (2 independently-computed
   readiness/gaps values for the same case), not just missing content. Sigma 005's own GPT Boundary Policy
   is already the right shape for Factory Step 4 — no new boundary mechanism needed, just re-sourcing the
   existing one.
2. **`digital_twin.py`** — clean context-injection case, AND a 3rd confirmed candidate for the
   deterministic-percentage-cap boundary mechanism (`nova_verovatnoca_uspeha`). Doing this one would make
   4 modules total using the same cap shape (Court Predictor's 2 flagship endpoints, `hearing_cc.py`, and
   this one) — worth checking at that point whether the cap logic itself (not its data source) has become
   common enough to warrant a single, tiny, well-tested shared function
   (`shared/readiness_cap.py::apply_readiness_cap(value, readiness_status, cap_map)` or similar) — the ONE
   case in this whole program's history where a shared helper might finally be justified, since by then it
   would be the 4th independent, byte-identical reimplementation of the exact same 3-line clamp logic. Not
   authorized this sprint — a future sprint's own explicit decision once the 4th instance exists for real,
   not a preemptive abstraction now.
3. **`zadaci.py::ai_analiziraj_predmet`** — lower urgency (already self-grounded via a direct call, not an
   active gap), but same mechanical value as `case_commander.py`. Good 3rd target once the
   duplicate-computation pattern is proven twice.
4. From the wider census (`docs/tau/GPT_MODULE_CENSUS.md`)'s own remaining candidates:
   `api.py::predmet_workspace` ("Cockpit AI" — richest bespoke builder found besides `hearing_cc.py`,
   not on the original `TAU-012` list), `api.py::predmet_ai_preporuka`, `copilot.py::_handle_analiza_predmeta`,
   `evidence_graph.py::generisi_graf`, `outcome_intel.py`, `precedenti.py`, `precedents_radar.py`,
   `profitabilnost.py`, `strategy_simulator.py`, `zakon_monitoring.py`, `zastarelost.py`.

## Rokovi/rocista split — now corroborated 4 independent times, worth its own small sprint

`TAU-013` already named this. Phase 7 this sprint independently found it a 3rd and 4th time
(`case_commander.py`, `digital_twin.py`, on top of the pre-existing `decision_replay.py`/`zadaci.py`
instances Phase 1's census also confirmed). 4 independent files maintaining their own `rokovi` fetch
alongside canonical `deadlines`' own `rocista` source is a real, recurring pattern now — worth a small,
focused future sprint deciding whether `rokovi` should become part of the canonical contract, or whether
`rokovi` itself should be deprecated in favor of `rocista` platform-wide (a bigger, riskier product decision,
not this handover's call to make).

## What NOT to do

- Don't build a shared context-fetch/formatter helper module — reconfirmed a 3rd time this sprint (Case
  Commander's shape differs from `hearing_cc.py`'s differs from `digital_twin.py`'s). Template the pattern.
- Don't attempt `case_commander.py`'s or `zadaci.py`'s own duplicate-computation elimination without first
  writing a test proving the 2 independently-computed values actually agree on realistic data — don't
  assume they do just because both call the same underlying functions (different input row sets could still
  diverge).
- Don't build the shared cap-clamp helper mentioned above until a 4th real instance exists — 3 is not yet
  enough per this whole program's own repeated "don't abstract until you have 3-4 PROVEN identical cases"
  discipline (and even then, it should be a deliberate, separately-authorized decision, not a byproduct of
  an unrelated migration sprint).
- Don't expand `shared/case_context.py`'s own contract in the same sprint as a rollout push — sequencing
  guidance from Master Sprint 004/005's own handovers still applies unchanged.

## What's already solid, don't re-litigate

The Factory pattern itself (`CANONICAL_CONTEXT_FACTORY.md`), proven across 4 modules of 2 genuinely
different shapes. The deterministic-cap boundary mechanism, proven 3 times now (Court Predictor,
`hearing_cc.py`, and structurally confirmed applicable to `digital_twin.py`). The Document Visibility
Engine, reused a 3rd time this sprint without modification. `MIGRATION_TEMPLATE.md`'s own 8-step checklist —
used successfully for the `hearing_cc.py` pilot and validated against 3 further shapes without needing
further changes beyond the one Step 0 addition.
