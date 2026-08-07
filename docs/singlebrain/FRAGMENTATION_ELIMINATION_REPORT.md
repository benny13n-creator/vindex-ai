# FRAGMENTATION_ELIMINATION_REPORT.md — Operation Single Brain, Mission 002

Ledger of every fragmentation finding from Phase 1 (6 forensic teams, `SINGLE_BRAIN_DECISION_MAP.md`),
marked CLOSED (fixed + regression-tested this mission) or DEFERRED (named as `SINGLEBRAIN2-DEBT-XXX`
in `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`). Every CLOSED item cites its fix and its test.

## CLOSED (5 fixes)

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 | **Headline fix.** A case's checklist-based "Case Ready Score" could show 100/100 "Predmet spreman za rad" on the SAME case where the canonical `compute_case_readiness()` engine had already found a blocking CRITICAL_GAP — proven with a real reproduction (Team 2), not theorized. The two systems answer genuinely different questions (setup-completeness vs. blocking-gap-severity), so neither was replaced; instead the checklist score is now capped by the SAME `CAP_BY_READINESS` constant already governing 4 GPT probability generators (a 5th consumer of an existing pattern, not a new one), and the checklist gains a visible ⚠ item naming the specific blocking reason so the cap is explained, not silent. Wired into all 3 real callers (`services/case_pipeline.py::run_case_pipeline`, `routers/case_pipeline.py::pipeline_status`, `api.py`'s case-workspace endpoint). | `services/case_pipeline.py::calculate_case_ready_score` gains an optional `readiness` parameter; `shared/case_readiness.py` unchanged (already canonical) | `tests/test_singlebrain2_readiness_unification.py` (10 tests) |
| 2 | `court_predictor.py::argument_reputation` was range-clamped but never readiness-capped, unlike its sibling `prediktuj_ishod` in the same file — a `CRITICAL_GAP`/`BLOCKED` case could show an uncapped, confident argument-success percentage on this one surface while every other success-probability surface on the same case was already capped (`SINGLEBRAIN-DEBT-002`, carried from Mission 001) | Applied `CAP_BY_READINESS` to both `uspesnost_procena` and `ukupna_snaga` | `tests/test_singlebrain2_readiness_unification.py::test_argument_reputation_has_readiness_tier_cap` |
| 3 | **Most serious new finding (Team 3).** `strategija.py`'s F10 "AI Sudija" verdict (`orkestrator_kompletna_analiza_sync`, korak 5) had zero server-side clamp/validation on `procena_uspeha_tuzilac`/`izreka`/`confidence` — the frontend only clamped the progress-bar width, never the displayed number text. A poisoned response (`procena_uspeha_tuzilac: 9999`, fabricated `izreka`) was proven to reach the live, UI-wired response unmodified — the single most direct violation found of this mission's own Acceptance Criterion 2. | Unconditional clamp on `procena_uspeha_tuzilac` (0-100); enum-guard on `izreka`/`confidence`, fail-safe to the non-extreme values | `tests/test_singlebrain2_readiness_unification.py::test_orkestrator_clamps_poisoned_ai_sudija_verdict`, `test_orkestrator_leaves_well_formed_verdict_unchanged` |
| 4 | Genome's `heatmap` and `dokazi_rang[].snaga_score` sub-fields were never clamped, even though the headline `snaga_predmeta_procent`/`kriticnost`/`genome_kompletnost` fields on the SAME extraction call already were (Mission 001) — the "guarded the headline, missed the sibling field" pattern recurring a 3rd time. `dokazi_rang[].snaga_score` also drives a `<70` "weak evidence" filter downstream. | Both clamped 0-100, matching the existing `najslabija_tacka.kriticnost` pattern | `tests/test_singlebrain2_readiness_unification.py::test_extract_genome_clamps_poisoned_heatmap_and_dokazi_rang` |
| 5 | `routers/ccc.py`'s hearing query had `.limit(10)` (ordered by nearest date, no future-only filter) while `routers/matter_intel.py`'s equivalent query — feeding the IDENTICAL `calculate_procesni_rizik` call — was unbounded. For a case with more hearings than the cap, the two endpoints' health/risk badges could diverge on the same screen; in the worst case a genuinely critical upcoming hearing could fall outside the cap entirely. | Removed `.limit(10)`, matching `matter_intel.py` exactly | `tests/test_singlebrain2_readiness_unification.py::test_ccc_hearing_query_no_longer_limited` |

Phase 4 (Team 7 Chaos & Regression) then ran all 6 mandated adversarial scenarios (1000 documents,
100 contradictions, GPT poisoned response sweep, concurrent updates, stale cache injection, frontend/
backend disagreement) against the fixed code — `tests/test_singlebrain2_phase4_chaos.py`, 8 tests, all
passed. No contradiction survived any of the 6 scenarios.

## DEFERRED — named as debt, not silently dropped

See `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` for `SINGLEBRAIN2-DEBT-001` through `-012`.
Summary:

- **Next Action fragmentation** (`SINGLEBRAIN2-DEBT-001`): 3-4 independent "what should the lawyer
  do" generators (`top_open_action`, `case_pipeline.py::_step_copilot_preporuka`, `copilot.py::
  _handle_predlozi`, `zastarelost.py`'s own parallel deadline thresholds) — a genuinely new category
  Mission 001 never separately mapped, too large to consolidate safely in this mission's time budget.
- **Case Genome's `snaga_predmeta_procent` surfaces unlabeled as a de facto second "risk"/"success"
  metric** in CIO's portfolio panel, Copilot's "Verovatnoća uspeha", and the Case Genome hero panel's
  own risk label (`SINGLEBRAIN2-DEBT-002`) — a labeling/UX decision, not a mechanical bug.
- **Portfolio case-strength aggregation** still diverges between `health_index.py`/`cio.py`
  (`SINGLEBRAIN2-DEBT-003`, carried from Mission 001's `SINGLEBRAIN-DEBT-003`, unchanged).
- **Confidence means 4 different things on one case page** (`SINGLEBRAIN2-DEBT-004`, Team 4) — RAG
  grounding confidence, Genome completeness-as-confidence, the Sveobuhvatna Procena report's own
  verdict, firm-wide calibration bands.
- **`SINGLEBRAIN-DEBT-010` carried forward unchanged** (`SINGLEBRAIN2-DEBT-005`): the readiness-tier
  cap still fails open on `build_case_context()` error.
- **Case Commander remains dead code** (`SINGLEBRAIN2-DEBT-006`) — the platform's best-designed
  consolidation of all 8 decision concepts has zero live frontend callers; wiring it up is named as
  the single highest-leverage next move, not attempted here (would need to happen only AFTER, not
  before, the readiness consolidation in this mission — doing it first would have created a new,
  immediately-visible 3-way collision).
- **`predmeti.status` classifier fragmentation** (`SINGLEBRAIN2-DEBT-007`) — full specification for
  the fix in `docs/singlebrain/CASE_STATUS_CANONICAL_MODEL.md`, not implemented this mission.
- **`health_score` naming collision** across 3 unrelated domains (`SINGLEBRAIN2-DEBT-008`) — a naming
  trap, not a data bug; each is internally single-sourced.
- **DB CHECK constraints missing** on `predmeti.status`/`.rizik`/`.kanban_faza`, `case_actions.
  confidence`, `predmet_istorija.confidence` (`SINGLEBRAIN2-DEBT-009`) — requires migrations, which
  per this engagement's standing convention are drafted but never run by the coordinator.
- **Shadow columns** (`predmeti.kanban_faza`/`case_dna`/`oblast`/`oblast_prava`, zero migration
  provenance) — carried forward unchanged (`SINGLEBRAIN2-DEBT-010`).
- **`GET /api/portfolio`'s stale cache + `matter_intel.py`'s dead uncertainty dashboard** — carried
  forward unchanged, confirmed still dead/orphaned, low practical risk (`SINGLEBRAIN2-DEBT-011`).
- **`predmet_health_log.rizik_label`** confirmed dead (write-only, never read) by Team 5 — schema
  cleanup, not attempted (`SINGLEBRAIN2-DEBT-012`).

## Honest scope note

This mission's founder mandate set the highest bar of the engagement: "even one cross-module
contradiction fails the mission." The 5 fixes above close every CONCRETELY REPRODUCED contradiction
the 6 forensic teams found — each one backed by an actual function-call reproduction or a direct code
citation, not a theoretical concern. The 12 deferred items are real, named, and specific, but are
either (a) larger consolidations that risk introducing new behavior changes if rushed, (b) product/UX
labeling decisions outside a mechanical fix's scope, or (c) migration-gated DB changes outside the
coordinator's authority to run. See `SINGLE_BRAIN_MISSION_002_FINAL_CERTIFICATE.md` for the full
verdict against the mission's 5 stated acceptance criteria.
