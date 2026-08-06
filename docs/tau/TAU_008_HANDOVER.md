# Tau 008 Handover — Rolling Out Canonical Reasoning Consolidation

Program Tau, Master Sprint 007 migrated `case_commander.py` off its own independent risk/gap/readiness
computation and closed the drift risk it represented. This is the priority-ordered handover for whichever
sprint continues the reasoning-consolidation work `docs/tau/PARALLEL_REASONING_AUDIT.md` mapped but did not
migrate.

## The remaining 5-module family (`docs/tau/REASONING_REGISTRY.md` Finding 1)

`zadaci.py::ai_analiziraj_predmet`, `api.py::predmet_workspace`, `matter_intel.py`, `ccc.py`, `dashboard.py`
each still independently call `calculate_procesni_rizik`/`identify_case_problems` (some also
`compute_case_readiness`) on their own fetches. Priority order for the next sprint:

1. **`api.py::predmet_workspace`** ("Cockpit AI") — the richest of the 5, already flagged in Tau 006's own
   census as the richest bespoke context builder besides `hearing_cc.py`. Migrating this closes both a
   context-injection gap (Tau 006's own concern) and a duplicate-computation gap (this sprint's own concern)
   in one pass — good next target precisely because it's 2 debt items in 1 file.
2. **`matter_intel.py`** — its own docstring already frames itself as "the reference endpoint" for this
   computation, which makes it a lower-risk migration (the team already treats its own output as
   authoritative) but also means its response shape is likely the most-relied-upon of the 5 — verify live
   callers carefully (Step 0 of `docs/tau/MIGRATION_TEMPLATE.md`) before assuming Tau 006/007's own
   "confirmed dead" pattern repeats here.
3. **`ccc.py`, `dashboard.py`** — both already delegate to the canonical FUNCTION (fixed in a prior sprint)
   but still run their own independent fetch. Lower-risk, mechanical migrations — good matched pair to do
   together since they're structurally identical in shape.
4. **`zadaci.py::ai_analiziraj_predmet`** — lowest urgency (already self-grounded via a direct call, not an
   active correctness gap, per Tau 006's own prior assessment) but same mechanical value.

**Apply `case_commander.py`'s own 2-shape lesson to each**: check Step 0 (does this module ALSO independently
recompute what `build_case_context()` already computes, not just re-fetch the same tables?) before assuming
a pure context-injection migration suffices. `case_commander.py` needed field-level care (`nedostaje`/`rizici`
weren't a clean 1:1 swap — see `docs/tau/CASE_COMMANDER_CONSOLIDATION.md`); expect the same for at least
some of these 5.

## `cio.py`'s GPT-decided priority — the one real, still-open GPT Boundary violation (`TAU-017`)

`docs/tau/CANONICAL_REASONING_CERTIFICATION.md` names this precisely (formalized as `TAU-017` in the debt
register): GPT independently invents
`kriticnost`/`najveci_rizik`/`kriticni_rok`/`cio_preporuka` from raw portfolio signals, with no deterministic
grounding. Live, billed, previously deliberately deferred (Program Omega Sprint 004) — needs its own
dedicated sprint, not a bolt-on to a reasoning-consolidation or Factory-pattern sprint, because changing a
live GPT prompt's own behavior/shape carries real user-facing risk a "just migrate the context" sprint
shouldn't absorb. Recommend a sprint scoped specifically to this ONE file, following the same "forensic
re-verify live traffic first" discipline Tau 005/006/007 have each applied to their own single-file targets.

## The rokovi/rocista split — now corroborated 5 times total

Tau 006 counted 4 independent files (`case_commander.py`, `decision_replay.py`, `zadaci.py`,
`digital_twin.py`); this sprint's own Phase 1 census found `case_commander.py` itself independently
confirms it a 5th way (both the single-case AND portfolio-wide code paths in that ONE file each kept their
own `rokovi` fetch). Genuinely due for its own small, focused sprint — a contract-expansion or `rokovi`
deprecation decision — rather than continuing to accumulate as a side-finding of unrelated migrations. This
recommendation has now repeated across 2 consecutive Tau sprints' own handovers; do not let it become a
3rd repetition without action.

## What's already solid, don't re-litigate

`shared/case_context.py::build_case_context()` as the single reasoning-and-context source (proven across 6
consumer modules now: `case_intelligence.py`, `court_predictor.py`, `morning_briefing.py`, `hearing_cc.py`,
`case_commander.py`, and structurally simulated for `digital_twin.py`). The deterministic-cap GPT-boundary
mechanism (proven 3 times: Court Predictor, `hearing_cc.py`, structurally validated for `digital_twin.py`).
The Canonical Context Migration Factory template (`docs/tau/MIGRATION_TEMPLATE.md`), now proven against 2
genuinely different migration shapes (context-injection and duplicate-computation-elimination) and should
be the starting checklist for any of the 5 modules named above — don't redesign the process, instantiate it.

## What NOT to do

- Don't migrate more than 1-2 of the 5 remaining modules in a single sprint — this program's own repeated
  discipline (Tau 005/006/007 each scoped to exactly 1 file) exists because each migration surfaces its own
  field-level nuances (Finding 2/3/4 in this sprint's own audit were not predictable in advance).
- Don't fix `cio.py` as a side-effect of a reasoning-consolidation sprint — it needs its own dedicated risk
  budget, per the reasoning above.
- Don't build a shared "risk/readiness fetch" helper across the 5 remaining modules — reconfirmed a 4th time
  this program that request shapes differ enough (`case_commander.py`'s own 2-function, 2-shape migration is
  the clearest proof yet) that a forced shared abstraction would misfit at least one of them.
