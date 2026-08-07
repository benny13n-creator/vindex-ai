# SEMANTIC_MAP.md — Operation Singular Intelligence, Mission 001

Inventory of the 10 named concepts plus a fresh 11th ("recommendation"), re-verified against current
code (commit `4ec02d4`, post-Single-Brain-002) by 6 forensic teams. Prior docs
(`docs/singlebrain/TRUTH_REGISTRY.md`, `SINGLE_BRAIN_DECISION_MAP.md`, `CANONICAL_VALUE_MAP.md`)
were used as a starting inventory, not trusted blindly — every claim was re-checked, and several
prior claims were found to have gone stale mid-mission (fixes landed after the doc was written).

## 1. Risk

**Canonical**: `services/risk_engine.py::calculate_procesni_rizik` — zero GPT, called live by 10+
sites. Duplication risk now **Low** — genuinely converged.

**New finding this mission**: `routers/zadaci.py::ai_analiziraj_predmet`'s `predmet_dokazi` query is
missing the `.is_("deleted_at","null")` filter every other canonical-risk consumer has (`matter_intel.py`,
`ccc.py`, `case_context.py`, `case_pipeline.py`, `case_evolution.py`) — **live, reproduced**: identical
underlying case data produces `nivo: "Visok"` (Matter Intel/CCC) vs `nivo: "Srednji"` (Zadaci AI
Analiziraj) for the SAME case, because a soft-deleted evidence row is silently counted on this one path.
Fixed this mission (§ Fix 1).

Dead/manual-only, unchanged: `predmeti.rizik`, `predmet_istorija`'s `"[Rizik]"` cache, `GET
/api/portfolio`, `matter_intel.py::get_uncertainty_dashboard`, `routers/dashboard.py:378`'s "Matter
Health Score" endpoint (zero frontend callers, itself a 3rd historical risk formula fixed 2026-08-03 and
never wired up).

## 2. Readiness

**Canonical**: `shared/case_readiness.py::compute_case_readiness` — unchanged, still zero GPT, still no
UI badge for its own 5-state enum. Mission 002's checklist-cap fix (`case_pipeline.py::
calculate_case_ready_score`) re-confirmed live at all 3 callers. `matter_intel.py::preflight_check` and
`case_commander.py` confirmed still zero frontend callers.

## 3. Strength

**Canonical**: `case_dna.snaga_predmeta_procent` via `genome_validator.py::compute_snaga_score`.
`heatmap`/`dokazi_rang[].snaga_score` clamp fix (Mission 002) re-confirmed live.

## 4. Probability

**Canonical pattern**: 4 GPT probability generators, all clamped + `CAP_BY_READINESS`-capped
(`shared/case_readiness.py:77`). `strategija.py`'s AI Sudija clamp re-confirmed live.
`SINGLEBRAIN-DEBT-010`/`SINGLEBRAIN2-DEBT-005` (readiness cap fails open on `build_case_context()`
error) confirmed still open, unchanged.

**New finding**: `routers/strategy_simulator.py`'s `rizik_score` (1-10 documented) and `verovatnoca` enum
have **zero clamp/guard** — reproduced with an actual poisoned response (`rizik_score: 999999999`,
`verovatnoca: "EKSTREMNO_SIGURNO_100_PROCENAT"`) passing straight through. `/api/simulator/*` is
confirmed to have zero frontend callers today — a live landmine, same risk class as `matter_intel.py::
preflight_check`. Named as debt, not fixed (dead code, lower priority than live findings).

## 5. Confidence — 16 sources now, one structural escalation

All 15 previously-catalogued sources re-verified; the 3 already-fixed items (CIO, Genome, Opponent
Intel) confirmed genuinely live. **Materially worse than previously stated**: `recommendation_log` has
**zero writers, ever** — `services/learning_engine.py::log_recommendation` inserts columns `tip`/`tekst`
against a table whose real columns (migration 037) are `tip_preporuke`/`tekst_preporuke` — every insert
has always failed, masked by a bare `except Exception`. `log_recommendation` also has zero callers
anywhere in the codebase. The entire downstream chain (`confidence_auditor.py`, `decision_replay.py`,
Court Predictor's "Statistika kancelarije" panel) has been permanently starved since inception. One live
UI consequence: `court_predictor.py`'s stats panel unconditionally renders "Prihvaćeno: 0 · Odbijeno: 0"
forever, with no "no data yet" guard (unlike its own sibling Confidence Audit panel, which has one).
Fixed this mission: the missing UI guard (§ Fix 7). NOT fixed: the underlying dead pipeline — reactivating
a zero-caller function is a feature-completion project, not a truth-fragmentation fix, and is named as
debt.

**New 16th source**: `routers/firm_memory.py::_apply_trust` — a 0.0-1.0 trust float, currently
backend-only (no frontend caller).

## 6. Health

Unchanged: single generator `health_index.py::_compute_health`, Portfolio Risk fix confirmed live.
`health_score` naming collision across 3 unrelated domains confirmed unchanged (naming trap, not a data
bug).

**New finding**: the firm-wide Health Index widget (`GET /api/firm/health-index`, the flagship widget
loaded unconditionally on the main dashboard) caches its full verdict for 1 hour with **no staleness
disclosure to the frontend** — reproduced: a stale "88/A/Sve je u redu" verdict can win over a live
"34/C/HITNO" recomputation for up to an hour. The codebase's own `cio.py` demonstrates the correct
pattern (threads `iz_kesa`/`generisano_u` through to the UI) but `health_index.py` doesn't apply it.
Fixed this mission (§ Fix 2).

## 7. Importance

Confirmed fully reconciled (Mission 002's `VAZNOST_TO_CANONICAL` fix holds).

## 8. Status

`conflict_check.py`'s targeted fix confirmed closed. Broader 5-way classifier fragmentation
(`SINGLEBRAIN2-DEBT-007`) unchanged, not re-attempted this mission.

## 9. Priority / Urgency

**New finding**: `routers/zastarelost.py` has **two different urgency-threshold ladders inside the same
file** — `/guardian/analyze` (≤3/≤7/≤14 days) vs. `/guardian/scan` (≤2/≤5/≤14 days, different bottom
label). A 3-day-out deadline is "kritično" on one endpoint, only "hitno" on the other — a sharper, worse
finding than the prior docs' "cutoffs coincide" verdict (which only ever compared the `analyze` variant
against `case_evolution.py`). Both endpoints confirmed zero frontend callers today — a landmine, not a
live contradiction. Named as debt.

## 10. Score (generic)

Confirmed an overloaded suffix, not an 11th concept — every `_score` field maps onto risk/health/
strength/confidence/readiness.

## 11. Recommendation — new category, not previously catalogued

The mission's headline finding. See `TRUTH_CONTRACT.md` §Recommendation and `DECISION_ARCHITECTURE.md`
for the full analysis. Summary: on the Command Center home screen alone, 3 independently-computed
"what should I do today" answers are stacked in view order — `routers/workspace.py` (deterministic,
canonical), `health_index.py::_compute_chief_partner` ("Chief Partner — Direktiva za danas", GPT, never
reads `case_actions`), and `routers/cio.py`'s "Preporuka za danas" (GPT, never reads `case_actions`,
and the module's own code comment admits this was a deliberate, disclosed scope decision — "van
bezbednog obima"). Neither GPT surface is cross-checked against the other or against Workspace.
Additionally: `services/case_pipeline.py::_step_copilot_preporuka`, `routers/copilot.py::
_handle_predlozi`, and `routers/zastarelost.py`'s own thresholds are 3 more independent
recommendation-adjacent generators (`SINGLEBRAIN2-DEBT-001`, still open). `routers/zadaci.py::
ai_analiziraj_predmet` is the best-disciplined GPT surface in this category — it injects
`identify_case_problems()`'s deterministic findings into the prompt and instructs GPT not to contradict
them.

## Cross-cutting: Web3/MiCA compliance suite — new AI-boundary flagship finding

Outside the case-risk/readiness/confidence vocabulary above but squarely inside this mission's mandate:
`web3_compliance.py`'s 4 client-facing PRO due-diligence scores (`mica-score`, `license-check`,
`aml-audit`, `health-score`) return raw GPT JSON with **zero server-side clamp or enum validation**, and
the frontend's fallback logic silently renders any unrecognized risk-level string as **green/low-risk** —
a materially worse failure direction than any previously-found gap, in a regulatory-compliance product.
Fixed this mission (§ Fix 3).
