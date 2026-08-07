# ARCHITECTURE_CERTIFICATION — Program Lambda, Certification 008

Covers Team 1 (Architecture Integrity), Team 7 (Canonical Context), Team 8 (Canonical Decision Sources).
Verifies the platform's own governing law (`docs/architecture/VINDEX_CORE_CONSOLIDATION.md`): "1 koncept =
1 vlasnik = 1 algoritam = 1 istina."

## Verified sound (re-checked directly against current code, not assumed)

- All 6 of `VINDEX_CORE_CONSOLIDATION.md`'s concrete canonical-ownership claims hold up (risk, next-action,
  Genome, deadlines) — `case_pipeline.py`'s risk/action steps call `risk_engine.py` exclusively, no
  independent GPT reimplementation found.
- The Canonical Action Engine (`case_evolution.py`) and Canonical Attention translation layer
  (`shared/attention_priority.py`) are real, consistently reused, and not bypassed anywhere newly checked.
- `case_commander.py::_kanonski_nalazi`/`_kanonski_prioritet_i_rizici` verified to call
  `build_case_context()` exclusively — zero direct `calculate_procesni_rizik`/`identify_case_problems` calls.
- `routers/case_readiness.py`, `gap_engine.py`, `attention_priority.py` are genuine consolidation/translation
  layers, not new competing algorithms.

## Findings — all fixed this sprint

1. **`api.py::predmeti_dashboard`'s 4th independent priority formula** (MEDIUM-HIGH) — computed its own
   `_RISK_SCORE`-weighted score instead of using the canonical Attention Engine, live and user-facing (drove
   the case-list "sort by priority" control). Fixed: now delegates to `case_actions.prioritet` via
   `shared/attention_priority.canonical_sort_key`, same pattern Workspace already uses.
2. **`case_commander.py`'s document context fetch** (MEDIUM-HIGH) — a narrower, un-migrated leftover from
   before the module's main analysis path was consolidated onto `case_context.py` (Tau Sprint 007); this
   specific helper still ran an unordered `.limit(20)` query feeding GPT directly, reproducing the exact
   "static slice permanently hides most of a large case" bug `case_context.py` was built to prevent. Fixed
   via recency ordering.
3. **`zakon_monitoring.py::impact_analiza`** (MEDIUM) — same unordered-slice bug, wholly undocumented before
   this sprint. Fixed.
4. **`multi_agent.py`'s document sampler** (LOW) — ascending (oldest-first) instead of descending, so a
   growing case stayed permanently stuck on its original oldest 10 documents. Fixed.
5. **`health_index.py`'s dead-column bug** (HIGH, technically a decision-source integrity finding) —
   selected a `rizik_nivo` column that exists nowhere in the schema, silently swallowed by
   `return_exceptions=True`, zeroing 4 dashboard components. Fixed by removing the phantom column reference.

## Findings — deferred, debt-registered

- **`matter_intel.py::get_uncertainty_dashboard`** (`GAMMA-003`, re-confirmed still open) — independently
  recomputes a missing-document percentage in the same file that already imports the canonical
  `calculate_procesni_rizik`. Not fixed this sprint (consolidation needs a bigger scoped pass than this
  sprint's fix budget allowed).

## Already-tracked, correctly not re-reported

- `routers/health_index.py`'s independent GPT firm-level recommendation engine (`TAU-018`/`LAMBDA-005`).
- `court_predictor.py`/`digital_twin.py`/`hearing_cc.py`'s duplicated `_CAP_BY_READINESS` dict (minor DRY
  issue across 3 files, not a competing algorithm — not re-flagged as new).

**Verdict**: 5 genuine architecture-integrity violations found this sprint, all fixed; 1 pre-existing
duplicate-decision-source item re-confirmed open and correctly deferred, not silently ignored.
