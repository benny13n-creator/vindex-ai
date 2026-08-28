# Decision Registry — Program Gamma (Masterprompt 003)

**Purpose:** the single catalog of every canonical business/legal decision
function in the platform. Before writing any new business-decision logic,
check this file first — per the founder's own binding rule (closing note of
Masterprompt 003): *"Da li uvodi novu poslovnu odluku? Ako uvodi, da li ta
odluka već postoji u Decision Registry-ju? Ako ne postoji, da li zaista
treba da bude nova odluka ili je samo drugačiji prikaz postojeće?"*

This is not a new mechanism — it is the first formal write-up of a pattern
that has existed in this codebase since 2026-07-18 (`compute_snaga_score`)
and been proven independently 4 times since (Court Predictor, Program Beta's
2 fixes, Program Gamma's 3 fixes below). Registering it does not add
complexity; it makes an already-real convention checkable.

## How to read this table

- **Status `CANONICAL`**: exactly one author, proven single-sourced, safe to
  build new consumers against.
- **Status `FRAGMENTED`**: 2+ independent authors exist for this decision
  today — building a new consumer means picking one (document which, and
  why) or, better, escalating to close the fragmentation first. See
  `DECISION_CONSISTENCY_REPORT.md`.
- **Status `ORPHANED`**: a real, correct implementation exists but has zero
  live consumers.

## Canonical decisions (exactly one author, verified)

| Decision | Canonical function | File | Consumers | Contract |
|---|---|---|---|---|
| Procesni rizik (case risk) / health score | `calculate_procesni_rizik` | `services/risk_engine.py` | `ccc.py`, `dashboard.py`, `matter_intel.py` (main endpoint), `zadaci.py`, `case_pipeline.py` steps 7/8 | `DC-001` |
| Sledeći koraci (deterministic "what's missing", NOT the AI recommendation layer) | `identify_case_problems` | `services/risk_engine.py` | `dashboard.py`, `zadaci.py::ai_analiziraj_predmet`, `case_pipeline.py` step 8 | `DC-002` |
| Case-strength percentage (Genome) | `compute_snaga_score` | `shared/genome_validator.py` | `case_dna.py::_extract_genome` (both call sites) | `DC-003` |
| Court Predictor confidence level + percentage | `_calc_confidence_nivo` / `_procenat_iz_score` | `routers/court_predictor.py` | `confidence_check` endpoint | `DC-004` |
| Evidence Vault claim strength (`snaga`) | `odredi_snagu` (wraps `snaga_iz_lokacije`) | `shared/evidence_write.py` | **only** `upisi_dokaze` — which is the single write path for `predmet_dokazi`, used by both `routers/evidence.py::klasifikuj_i_sacuvaj` (automatic) and `routers/evidence.py::add_dokaz` (manual) | `DC-005` |
| Genome delta significance / alert urgency | `_delta_significant` / `_delta_hitnost` | `routers/case_dna.py` | auto-refresh + manual-refresh paths (both, since Program Gamma's dedup) | `DC-006` |
| Genome internal consistency / escalation need | `verify_genome` (incl. `_validate_dok_reference` family) | `shared/genome_validator.py` | `case_dna.py::_extract_genome`, `_maybe_alert_require_review` | `DC-007` |
| Draft readiness (deterministic half only — citations) | `evaluate_draft_quality` (citation component) | `services/quality_gate.py` | `routers/drafting.py` auto-promotion gate | `DC-008` |
| Cross-reference existence check (DOK-XX / graph node / predmet prefix) | `validate_dok_reference` / `validate_graph_edge_references` / `validate_predmet_reference` | `shared/genome_validator.py` | `case_dna.py::compare_docs`, `evidence_graph.py::generisi_graf`, `case_commander.py::_cross_case_analiza` | `DC-009` |
| Strategy Engine Synthesis low-confidence aggregation | inline in `orkestrator_kompletna_analiza_sync` (deterministic block) | `strategija.py` | Synthesis step (korak 6) | `DC-010` |
| Strategy Engine Synthesis categorical conflict detection (structurally-checkable subset) | inline in `orkestrator_kompletna_analiza_sync` (deterministic block) | `strategija.py` | Synthesis step (korak 6) | `DC-011` |
| Court Predictor argument-color / profile-confidence derivation | inline in `argument_reputation` / `judge_profile` | `routers/court_predictor.py` | those 2 endpoints | `DC-012` |
| Alert creation (single write path) | `create_proactive_alert` | `shared/proactive_alerts.py` | all alert-producing modules (Program Alpha canonicalization) | `DC-013` |
| Case Commander per-case canonical findings (status/nedostaje/rizici/preporučeni potez/vremenski pritisak) | `_kanonski_nalazi` | `routers/case_commander.py` | `commander_analiza`, `commander_quick_check` | `DC-014` |
| Case Commander portfolio-wide priority + risk ranking | `_kanonski_prioritet_i_rizici` | `routers/case_commander.py` | `_cross_case_analiza` (→ `commander_jutarnji`) | `DC-015` |

## Fragmented decisions (2+ independent authors — do NOT add a 3rd without reading `DECISION_CONSISTENCY_REPORT.md` first)

| Decision | Known authors (not exhaustive — see report) | Severity |
|---|---|---|
| "Sledeći preporučeni korak" / strategic recommendation | ≥9 across Genome, Strategy Engine (2), Court Predictor (4), Copilot (3, override-with-GPT-fallback only — GPT still invents a next step when `case_actions` is empty), Case Intelligence (same fallback shape), Case Pipeline step 5. Case Commander's 3 were fully consolidated into `DC-014`/`DC-015` by Sigma Sprint 005 (2026-08-06) — no longer a fragmentation author, verified against current code by Program Tau (2026-08-06), not assumed from this row's prior text. | Critical — largest fragmentation in the platform |
| Litigation win-probability percentage | `PROGBETA-001`'s 4 generators + Case Pipeline step 5 = 5 | Critical |
| "Is this document/case ready" | `quality_gate.confidence_score` vs. Strategy Engine's Pravni Revizor `ocena` (2, incompatible representations) | High |
| Case strength/readiness/risk (broader than procesni rizik) | `risk_engine`, Genome, Matter Intel Uncertainty Dashboard, Matter Intel Pre-Flight = 4 | High |
| "What's missing" (documents/evidence) | `identify_case_problems` (canonical) vs. Genome `nedostaje` vs. Strategy Engine V2 `nedostajuci_dokazi` vs. Copilot PLAN `nedostaje` (field-name collision, incompatible vocab) | High |
| Contradiction between evidence | Genome, Compare Docs, Evidence Graph, Case Commander = 4 (2 now evidence-checked by this mission, see `DECISION_CONSISTENCY_REPORT.md`) | Medium-High |
| Hearing readiness | `routers/hearing_cc.py` (paid, deliberate) vs. Case Pipeline step 6 (free, automatic shadow) | High |
| "How urgent is this" vocabulary | 6+ independently-defined 3-value taxonomies, no shared enum | Medium |
| Document classification (`tip_dokaza`) | `intake_classify.py` (English, sync, wrong vocabulary) vs. `evidence.py` (Serbian, correct vocabulary, unawaited fire-and-forget) — `ALPHA-003` | Critical |
| Firm memory judge-favorability | `firm_memory.py::kontekst_za_ai` (real data, dead) vs. Court Predictor (LLM guess, live) — `ALPHA-005` | Critical |

Full detail, file:line citations, and the reasoning behind each severity
rating: `DECISION_CONSISTENCY_REPORT.md` and the 5 domain-investigation
files in `.vindex_ai_team/decisions/2026-08-04_gamma_domain_*_INVENTORY.md`.

## Orphaned decisions (real, correct, zero live consumers)

| Decision | Implementation | Why orphaned |
|---|---|---|
| Judge win-rate / procedural preference / client settlement posture | `routers/firm_memory.py::kontekst_za_ai` | Live path (`api.py::_fetch_firm_memory_context`) never calls it — `ALPHA-005`, sharpened by Gamma to note Court Predictor answers a related question with no real data at all |
| Legal Reasoning Engine `Claim` nodes | `services/legal_reasoning_engine.py` | Explicitly Phase-0-scoped by the founder to not be wired yet — not a defect, a forward guardrail (see `DECISION_HARDENING_REPORT.md`) |

## Registration rule for any future decision (the enforcement mechanism)

1. Before writing a function that computes a business or legal conclusion
   (anything a lawyer reads and acts on), search this table for the closest
   matching decision name.
2. If found and `CANONICAL`: call it. Do not reimplement.
3. If found and `FRAGMENTED`: do not add a 5th/6th/7th generator. Escalate —
   either use the existing consolidation design in
   `CANONICAL_DECISION_ENGINE.md` §Deferred, or raise it as a founder
   decision the way `DUPLICATE_DECISION_REPORT.md`'s Pattern A prescribes.
4. If not found: add a row to this table (with its `DC-0XX` contract in
   `DECISION_CONTRACTS.md`) in the SAME pull request that introduces the
   function. `tests/test_decision_registry_completeness.py` mechanically
   verifies every registered function is still importable and callable —
   it does not (and cannot, without static analysis infrastructure this
   repo does not have) verify a NEW decision was registered; that half of
   the rule is a process convention, not a runtime check. See
   `DECISION_HARDENING_REPORT.md` for the honest limits of this guardrail.
