# AI Canonical Architecture — Program Beta (Masterprompt 002)

**Deterministic AI & Evidence-First Architecture.** Executive summary and
entry point for the 7 companion documents this mission produced. Mirrors
`CANONICAL_ARCHITECTURE_REPORT.md`'s role for Program Alpha, applied to
AI-reasoning defects instead of structural duplication.

## Governing principle

> Model nije izvor istine. Model je samo izvršilac. Izvor istine je platforma.
> Ako sutra promenimo GPT, Claude, Gemini ili lokalni model, korisnik mora
> dobiti isti zaključak kada su činjenice iste. Ako to danas nije moguće, to
> je arhitektonski problem, ne problem modela.

## 5 principles, verified against real code, not aspiration

1. **Facts Before AI** — best living example: `services/risk_engine.py::
   identify_case_problems` → `ai_analiziraj_predmet` (facts computed first,
   injected with a don't-contradict instruction, failure path reproduces the
   same facts with zero LLM involvement).
2. **Facts ≠ Inference ≠ Recommendation** — implicit in most schemas
   (Genome, Compare), explicit nowhere as a machine-checked or UI-enforced
   category. Real, unresolved violation: Copilot's akcija handlers
   (`PROGBETA-005`).
3. **AI Cannot Invent Authority** — strongest implementation: `main.py::
   ask_agent`'s hard-refuse on an unverified article citation, model never
   sees the question. Weakest: Strategy Engine's 9 endpoints, zero backend
   citation verification (`PROGBETA-003`).
4. **Deterministic Core** — proven 3× independently in this repo, oldest to
   newest: `analiza/validator.py` Sloj 10 → `compute_snaga_score()`
   (2026-07-18) → Court Predictor's `_calc_confidence_nivo`/
   `_procenat_iz_score` (Program Alpha, 2026-08-04) → this mission's
   `_snaga_iz_lokacije()` and the Strategy Engine `sistemsko_upozorenje`
   determinism fix. A standing platform principle, not a one-off.
5. **Explainability By Design** — best implementation: Genome's
   `_verifikacija` UI block (non-collapsible by design — "hiding a trust
   signal behind a click would defeat the reason it was built"). This
   mission extended the same discipline to Compare (symmetric ⚠/✓) and
   Evidence Vault (grounding tooltip) after Olympus governance review
   found both were backend-correct but not user-visible.

## What this mission found (see `AI_DECISION_GRAPH.md`, `EVIDENCE_CHAIN_REGISTRY.md`)

5 domain investigations across the entire AI surface (Upload/OCR/Extraction,
Genome/Memory/Firm Brain, Legal Reasoning/Strategy/Court Predictor,
Copilot/Briefing/Drafting, Search/Tasks/Alerts/Dashboard) inventoried every
AI operation in the platform. Single most severe finding: Strategy Engine's
litigation-percentage — **4 independent, unreconciled raw-LLM percentage
generators** for one conceptual value, worse than Court Predictor's own
pre-fix state (`PROGBETA-001`, supersedes the older `KEYSTONE-004` entry
with a materially more precise diagnosis).

## What was implemented this mission (bounded, safe, fully tested)

1. **Evidence Vault `snaga`** (`routers/evidence.py`) — derived from
   `_lociraj_tvrdnju`'s already-computed grounding result instead of a
   hardcoded `"srednja"` constant. Hardened after Olympus governance review
   (2 independent reviewers, AI Grounding + AI Quality Auditor, found the
   same over-claim risk): bounded to claims of length [20,100] chars —
   too short risks a spurious match, too long means only the first 100
   chars (the `_lociraj_tvrdnju` probe window) were actually verified.
2. **Compare docs evidence check** (`routers/case_dna.py` +
   `shared/genome_validator.py::validate_dok_reference`) — previously the
   only AI call in the platform with zero of provenance/evidence-validation/
   UI-trust-signal. Now: `case_context()` wrapped, DOK-XX existence checked
   across all 3 citation-bearing fields (`koji_je_jaci_dokaz`,
   `kontradikcije`, `razlike_kljucne` — widened after AI Grounding's
   review), shape normalized to match `verify_genome()`'s contract, wrapped
   in its own fail-soft try/except (Backend Reliability's review), and
   surfaced symmetrically in the UI (⚠ on `require_review`, ✓ on `approve`
   — Architecture Review's finding).
3. **Strategy Engine `sistemsko_upozorenje`** (`strategija.py`) — the
   "≥2 of 5 steps NISKA" cross-step warning is now computed in code, not
   decided by the Synthesis LLM call, overriding the LLM's output in both
   directions. Hardened after Workflow Integrity's review: off-spec
   `confidence` values are no longer silently dropped (counted as an
   anomaly), and JSON-parse-failure steps are distinguished from genuine
   low-confidence legal signal, not conflated.

All 3 shipped with new/extended tests (`test_genome_validator.py`,
`test_akcija2_faza4_2026_07_24.py`, `test_strategija_sistemsko_upozorenje.py`,
`test_compare_docs_evidence_check.py`), full suite green after every change.

## Phase 10 — Olympus governance verdict

10 fresh, independent agents reviewed the implementation (9 founder-mandated
+ Reliability & Chaos, matching Program Alpha's own precedent of including
it). **Verdicts**: 1 clean APPROVED (Security Review), 8 APPROVED WITH
CONDITIONS, 1 DEGRADED (AI Quality Auditor — the Evidence Vault over-claim
risk, independently also found by AI Grounding). Every condition raised was
either fixed in this same pass or logged as an explicit, reasoned
`PROGBETA-00X` deferral in `ARCHITECTURAL_DEBT_REGISTER.md` — no systemic
problem was left unaddressed silently, per the mission's own Phase 10 rule.
One real self-correction surfaced by the review itself: this mission's own
deferred-item IDs (`BETA-001`..`005`) collided with unrelated missions'
existing Founder's Master Prompt IDs in `MISSION_BOARD.md` — renamed to
`PROGBETA-00X` platform-wide.

## What was deferred, and why (full detail: `ARCHITECTURAL_DEBT_REGISTER.md`)

`PROGBETA-001` (Strategy Engine shared scorer — needs 2 new signal-wiring
calls across 4 sites), `PROGBETA-002` (RAG provenance threading — 15+ call
sites, needs its own tested pass), `PROGBETA-003` (`quality_gate`
generalization — portability unconfirmed), `PROGBETA-004` (Genome heatmap
scoring — needs an extraction-schema redesign, not just a post-processor),
`PROGBETA-005` (Copilot fact/inference schema separation — touches a
system-of-record table). Plus 3 items found only during governance review:
`PROGBETA-006` (a newly-reachable `risk_engine.py` branch with no backfill
for pre-fix rows), `PROGBETA-007`/`PROGBETA-008` (pre-existing, adjacent,
lower-severity gaps). Every deferral follows the founder's own addendum:
systemic-first was evaluated and explicitly could not be safely bounded to
this session — not skipped for convenience.

## Success metrics (per the mission's own mandate — not commit/line counts)

| Metric | Count | Detail |
|---|---|---|
| AI error classes eliminated | 2 | "Discarded already-computed grounding signal" (Evidence Vault + Compare); "AI operation with zero evidence/provenance/UI trust signal" (Compare, the only such case in the platform) |
| Non-deterministic decisions removed | 2 | Evidence Vault `snaga`; Strategy Engine `sistemsko_upozorenje` |
| Canonical AI pipelines documented | 1 | `AI_REASONING_PIPELINE.md` — names and cross-references the existing, now-3×-proven deterministic-derivation pattern as a standing platform principle |
| AI decisions moved to a provable Evidence Chain | 2 | Evidence Vault `snaga`, Compare's citation-bearing fields (widened to 3 fields) |
| AI outputs made genuinely explainable (UI-visible, not just backend-correct) | 3 | Evidence Vault grounding tooltip, Compare's symmetric ⚠/✓ signal, Strategy Engine's breakdown message (NISKA count / anomaly count / technical-error count, distinguished) |
| AI outputs confirmed model-independent | 2 new functions | `_snaga_iz_lokacije`, `validate_dok_reference` — pure Python, zero model coupling by construction |
| AI heuristics removed (LLM executing a rule that should be code) | 1 | Strategy Engine's `sistemsko_upozorenje` aggregation |
| "Magic" confidence values eliminated | 1 | Evidence Vault's fixed `"srednja"` constant |

**Explicitly not claimed**: no new canonical pipeline was *invented* (the
one documented already existed 3× over); no AI capability was added; no
GPT-specific mechanism was introduced (all 2 new functions operate on
structured JSON fields any model could populate under the same contract).

## Reading order for the other 7 documents

`AI_DECISION_GRAPH.md` (Phase 2, full platform map) → `EVIDENCE_CHAIN_REGISTRY.md`
(Phase 3, every claim's traceability verdict) → `CONFIDENCE_MODEL_SPECIFICATION.md`
(Phase 4, every confidence value's status + the future-value rule) →
`HALLUCINATION_ELIMINATION_REPORT.md` (Phase 5, mechanism-level fix/defer
ledger) → `AI_REASONING_PIPELINE.md` (Phase 6, the canonical 10-step flow) →
`MODEL_INDEPENDENCE_REPORT.md` (Phase 8) → `AI_SYSTEM_HARDENING_REPORT.md`
(Phase 9, AI-reasoning-specific — distinct from Program Alpha's structural
`SYSTEM_HARDENING_REPORT.md`).
