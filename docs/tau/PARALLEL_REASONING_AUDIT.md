# Parallel Reasoning Audit — Program Tau, Master Sprint 007, Phase 2

Per the mission's own rule: "Ako dva modula daju isti rezultat različitim putem: to je nalaz." Builds on
`docs/tau/REASONING_REGISTRY.md`'s own census to name every concrete instance found, with the actual risk
each one represents.

## Finding 1 — the risk/gap/readiness 6-module family (drift risk, not yet observed divergence)

`case_commander.py`, `zadaci.py::ai_analiziraj_predmet`, `api.py::predmet_workspace`, `matter_intel.py`,
`ccc.py`, `dashboard.py` each independently fetch case data and call `calculate_procesni_rizik`/
`identify_case_problems` (some also `compute_case_readiness`/`collect_case_gaps`) a 2nd, 3rd, 4th, 5th, and
6th time, rather than reading `build_case_context()`'s own already-computed `readiness`/`missing_evidence`/
`contradictions` fields. All 6 call the SAME deterministic functions with (as far as verified) the same
inputs — so today's outputs likely agree. **The real risk is not current disagreement, it's that nothing
prevents future disagreement**: if any ONE of these 6 independent fetch queries changes (a `.select()`
column added/removed, a filter tightened) without the other 5 changing identically, the SAME case would
silently report different readiness/risk/gaps under the same field name depending on which of the 6
endpoints the user happens to call. This is precisely the shape Core Consolidation (2026-07-22) was written
to prevent, and precisely what `build_case_context()` (Tau 002) exists to be the one place this can't
happen.

## Finding 2 — `case_commander.py`'s own internal duplication (a within-file variant, not cross-module)

Reading `_kanonski_nalazi` and `shared/gap_engine.py::collect_case_gaps` together reveals `case_commander.py`'s
own response has 2 fields that substantially OVERLAP with each other, not just with the rest of the
platform:

- `rizici` is built directly from `identify_case_problems`'s raw output.
- `nedostaje` is built from `collect_case_gaps(problemi, case_dna)`, which internally calls
  `gaps_from_case_problems(problemi)` — a 1:1 reshaping of the SAME `problemi` list `rizici` was built from
  — then filters to 3 of gap_engine's own 5 tip constants (`NEMA_DOKAZA`, `NEDOSTAJE_DOKUMENT`,
  `GENOME_NEDOSTAJE`).

Net effect: every `NEMA_DOKAZA`/`NEDOSTAJE_DOKUMENT`-classified item from `identify_case_problems` appears
in BOTH `rizici` (raw) AND `nedostaje` (reshaped) in the SAME API response — the same finding, described
twice, under 2 different field names, with 2 different confidence-mapping rules (see Finding 3). Items
classified `KRITICAN_ROK`/`PREDSTOJECI_ROKOVI` appear ONLY in `rizici` (not `nedostaje`'s own narrower
filter); Genome's own `GENOME_NEDOSTAJE` items appear ONLY in `nedostaje` (never in `rizici`, since `rizici`
is built from `identify_case_problems`'s output alone, before Genome is folded in). This is not a bug in the
sense of wrong output — each field is internally consistent — but it is a real instance of "two fields, one
underlying computation, described as if independent."

## Finding 3 — a confidence-mapping discrepancy, found while tracing Finding 2

`case_commander.py`'s own `rizici` confidence rule: `"visoka" if pr["ozbiljnost"] == "kritican" else "srednja"`
(binary — only `"kritican"` gets `"visoka"`). `shared/gap_engine.py::gaps_from_case_problems`'s own canonical
rule: `{"kritican": "visoka", "vazan": "visoka", "info": "srednja"}` (`"vazan"` ALSO gets `"visoka"`). For
any `identify_case_problems` finding with `ozbiljnost="vazan"`, `case_commander.py`'s own `rizici` field
reports confidence `"srednja"` while its own `nedostaje` field (sourced from the canonical gap_engine
mapping, for the same underlying finding) reports `"visoka"` — a real, small, previously-unnoticed
disagreement WITHIN a single API response, not just across modules. Migrating `rizici` to derive from the
canonical gap record (Phase 3) fixes this as a byproduct, not a separately-scoped bug fix.

## Finding 4 — `case_commander.py`'s own portfolio-wide digest computes readiness WITHOUT gaps at all

`_kanonski_prioritet_i_rizici` (used by `commander_jutarnji`) calls `compute_case_readiness(actions, [])` —
an empty list for the `gaps` parameter. This means the portfolio-wide "which case needs attention today"
ranking is computed WITHOUT any Genome-contradiction or missing-evidence awareness — only `case_actions`
status feeds it. `morning_briefing.py` (Tau 002) already solved this exact problem correctly, for the exact
same portfolio-wide use case, by looping lightweight `build_case_context()` calls (which DOES include real
gaps) over each displayed case. `case_commander.py`'s own digest predates that fix and was never updated —
not a hypothetical risk, a real completeness gap in what's actually today the LEAST-informed readiness
computation of the whole 6-module family.

## Finding 5 — `cio.py`'s GPT-decided priority (name, don't fix this sprint)

`routers/cio.py` asks GPT to independently invent `kriticnost`/`najveci_rizik`/`kriticni_rok`/
`cio_preporuka` from raw portfolio signals — a genuine GPT Boundary violation per this sprint's own Phase 5
framing. Already self-documented by Program Omega Sprint 004 as a deliberate, live-billed, "out of safe
scope" deferral, not a fresh discovery. Not fixed this sprint — see
`docs/tau/CANONICAL_REASONING_CERTIFICATION.md` Phase 5 for the explicit reasoning on why this stays
deferred rather than rushed into this sprint's own scope.

## What's confirmed clean, not re-litigated

`shared/attention_priority.py` (pure translation, computes nothing new). `routers/court_predictor.py`,
`case_intelligence.py`, `morning_briefing.py` (all read `build_case_context()`'s own output directly — Tau
002/005). No GPT-decided risk/readiness/contradiction/priority found anywhere outside `cio.py`/`strategija.py`
(the latter structurally exempt — no case linkage exists to duplicate against). No new parallel algorithm
(reimplemented formula) found anywhere in this census — every "recompute" finding calls the SAME canonical
deterministic function a 2nd time on a 2nd fetch, never a hand-rolled alternative.

## Scope decision for this sprint

Per the mission's own explicit Phase 3 instruction ("Migriraj: case_commander.py"), only `case_commander.py`
(Findings 1's own case_commander.py instance, plus Findings 2/3/4, all specific to this one file) is migrated
this sprint. The other 5 members of Finding 1's family (`zadaci.py`, `api.py::predmet_workspace`,
`matter_intel.py`, `ccc.py`, `dashboard.py`) are named, not migrated — consistent with this whole program's
own "one proven migration at a time" discipline (Tau 005/006 both scoped to a single file for the same
reason). Queued in `docs/tau/TAU_008_HANDOVER.md`.
