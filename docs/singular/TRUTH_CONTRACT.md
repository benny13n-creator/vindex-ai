# TRUTH_CONTRACT.md — Operation Singular Intelligence, Mission 001

For every canonical concept: Owner, Input, Output, Forbidden. This is the enforceable contract
`shared/semantic_registry.py` encodes in code — this document is the human-readable source of truth
it's generated from.

---

## Risk

**Owner**: `services/risk_engine.py::calculate_procesni_rizik`
**Input**: `predmet_dokazi` (evidence, soft-delete-filtered), `predmet_dokumenti`, `rocista`
(hearings/deadlines), case type, expected-document schedule
**Output**: `{"nivo": "Nizak"|"Srednji"|"Visok", "health_score": 0-100, "nedostajuci_dokazi": [...],
"predstojeći_rokovi": int, "kriticni_rocista": [...]}`
**Forbidden**: any other module independently computing a "how risky is this case" verdict. GPT may
never author this value. A module that needs risk MUST call this function with a correctly-filtered
evidence set (soft-deleted rows excluded) — `routers/zadaci.py`'s omission of that filter was a Truth
Contract violation, fixed this mission.
**Explicitly NOT this concept**: `predmeti.rizik` (a lawyer's own manual note — different concept,
different label, must never be displayed as if it were this one).

## Readiness

**Owner**: `shared/case_readiness.py::compute_case_readiness`
**Input**: `case_actions` (open rows only), Gap Engine hypothesis-only findings
**Output**: `{"status": "READY"|"PARTIALLY_READY"|"BLOCKED"|"CRITICAL_GAP"|"UNKNOWN", "razlog": str,
"izvor": [...]}`
**Forbidden**: GPT may never author this value (verified: no parameter in the function signature
through which one could be injected). No other module may independently classify "is this case ready."
**Explicitly NOT this concept, and not forbidden to coexist**: `services/case_pipeline.py::
calculate_case_ready_score` answers "has the case's setup been completed" — a genuinely different
question. Per `docs/singlebrain/READINESS_AUTHORITY_SPEC.md`, it MUST be capped by this concept's
`CAP_BY_READINESS` constant whenever this concept reports `CRITICAL_GAP`/`BLOCKED`, so it can never
claim more readiness than the canonical engine allows — this is the enforcement mechanism between two
legitimate, distinct concepts, not a merge.

## Strength

**Owner**: `shared/genome_validator.py::compute_snaga_score`, writing `case_dna.snaga_predmeta_procent`
**Input**: `case_dna.snaga_faktori` (Genome-extracted, backend-recomputed from — not GPT's raw
self-report)
**Output**: `{"snaga_predmeta_procent": 0-100, "snaga_predmeta": "jaka"|"srednja"|"slaba",
"snaga_faktori": [...]}`
**Forbidden**: GPT's own raw `snaga_predmeta_procent` self-report may never be trusted directly — this
function recomputes it. No other module may independently score case strength.
**Explicitly a DIFFERENT concept from Risk, despite sharing display space**: strength measures argument/
merits quality; risk measures process/evidence/deadline exposure. A UI surface that labels a strength
score using risk vocabulary ("Visok rizik" for a low strength score) violates this contract even though
no number is wrong — this was found live in the Case Genome hero panel and is addressed in
`DEPRECATION_PLAN.md`.

## Probability (success/outcome)

**Owner**: no single function — 4 legitimately independent GPT generators answering different questions
(`court_predictor.py::prediktuj_ishod`, `court_predictor.py::argument_reputation`, `digital_twin.py` ×2,
`hearing_cc.py::hearing_score`), unified only by a shared GUARD contract, not a shared formula.
**Mandatory guard contract for ANY new or existing probability generator**: (1) unconditional numeric
range clamp applied regardless of any other condition, (2) `shared/case_readiness.py::CAP_BY_READINESS`
tier cap applied on top when readiness is `CRITICAL_GAP`/`BLOCKED`. A generator without BOTH is a Truth
Contract violation. `routers/strategy_simulator.py` currently violates this (named as debt — dead code,
not fixed this mission).
**Forbidden**: a probability number reaching a lawyer-facing UI with neither guard present.

## Confidence

**Owner**: no single function — legitimately ~16 distinct mechanisms answering different questions
(source-grounding confidence, completeness-as-confidence, self-declared analysis confidence,
calibration-band accuracy, etc.). **Mandatory guard contract**: any GPT self-declared confidence value
reaching lawyer UI MUST be enum-validated against its documented value set, fail-safe toward the least
confident bucket for unrecognized input (the pattern established by `normalize_tezina()` and reused for
`genome_kompletnost`/CIO's `pouzdanost`/Opponent Intel's `pouzdanost`).
**Explicitly acknowledged limitation of this contract**: the actual outcome-calibration mechanism
(`recommendation_log` → `confidence_auditor.py`) is non-functional (dead insert path since inception) —
this Truth Contract cannot currently be VERIFIED empirically for any of the 16 sources, only enforced
structurally at the point each value is produced. Named as debt.

## Health

**Owner (firm-wide)**: `routers/health_index.py::_compute_health`
**Owner (per-case)**: `services/risk_engine.py::calculate_procesni_rizik`'s own `health_score` field
**Input/Output**: firm-wide is a deterministic weighted sum over portfolio risk/strength/billing/
activity; per-case is the inverse-of-risk number from the canonical risk formula.
**Forbidden**: a 3rd independently-computed "health" meaning. `web3_compliance.py`'s "Documentation
Health Score" is a 3rd, UNRELATED concept (AML documentation completeness) sharing only the field
NAME — this is a naming collision, not a Truth Contract violation, but MUST NOT be renamed to something
that could be confused with either canonical owner above.
**Mandatory disclosure**: any cached firm-wide Health Index value MUST thread its cache status
(`iz_kesa`/`generisano_u`, the pattern `cio.py` already establishes) to the frontend. Serving a
>15-minute-stale verdict with no staleness indicator is a Truth Contract violation — found live this
mission, fixed.

## Priority / Urgency

**Owner**: `case_actions.prioritet` (DB-enforced enum, migration 099), translated for display via
`shared/attention_priority.py`
**Forbidden**: any module computing its own priority/urgency classification for the same underlying
case-action concept instead of reading `case_actions.prioritet` through the canonical translator.
`routers/copilot.py::_handle_predlozi` and `routers/zastarelost.py`'s dual internal threshold ladders
both violate this — named as debt (`SINGLEBRAIN2-DEBT-001` and this mission's own zastarelost.py
finding), not fixed this mission (consolidation-scale work).

## Recommendation ("what should the lawyer do") — NEW in this contract

**Owner**: `shared/case_readiness.py::top_open_action()`, reading `case_actions` (the sole-writer table,
`services/case_evolution.py`)
**Input**: `case_actions`' own already-canonical priority-ordered open rows
**Output**: a single highest-priority action `{tip, prioritet, razlog, rok, dedupe_key}`
**Forbidden**: a GPT narrative presenting itself as "what to do today" without EITHER (a) being
unconditionally overwritten from this function's output before reaching the UI (the pattern
`case_intelligence.py`'s AI Briefing already correctly implements), or (b) carrying an explicit,
visible disclosure that it is an independent AI suggestion, not the canonical action.
**Currently in violation, not fixed this mission (named as debt, mitigated with disclosure — see
DEPRECATION_PLAN.md)**: `health_index.py::_compute_chief_partner`'s "Direktiva za danas" and
`routers/cio.py`'s "Preporuka za danas" both generate free-form GPT recommendations without reading
`case_actions` at all, both rendered on the same Command Center home screen as the canonical Workspace
board, neither disclosed as independent from it. `cio.py`'s own code comment discloses the team already
knew this and deliberately deferred it as "van bezbednog obima" (out of safe scope, live paid feature).
This mission adds the visible disclosure (mitigation) but does not perform the deeper consolidation
(architecture for that is in `DECISION_ARCHITECTURE.md`, scoped as future work).
