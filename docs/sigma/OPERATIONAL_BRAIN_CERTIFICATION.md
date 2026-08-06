# Operational Brain Certification — Program Sigma, Master Sprint 005 (2026-08-06)

Phase 6 deliverable: assume Case Commander still has its own decisions. Try to prove: 2 different "most
important actions," a recommendation without a source, GPT changing a priority, a refresh changing an
action with no underlying data change, a restart producing a different result.

### Attempt 1: do 2 different "most important actions" exist?

**Before this sprint**: yes, provably — `commander_analiza`'s own `PREPORUCENI POTEZ`, `commander_quick_check`'s
own top warning, and `_cross_case_analiza`'s own `prioritet` were 3 independent GPT calls, each capable of
naming a DIFFERENT case/action as most urgent for the identical underlying data.

**After this sprint**: all 3 now call `shared/case_readiness.py::top_open_action`/`_kanonski_prioritet_i_rizici`
— the SAME function, reading the SAME `case_actions` rows. Proven by
`test_kanonski_nalazi_preporuceni_potez_reads_case_actions_top_priority` and
`test_cross_case_analiza_prioritet_ignores_gpt_and_uses_case_actions` (2 dedicated tests, both passing) —
for the same input, all 3 surfaces are now structurally guaranteed to agree, since they share one function
call, not 3 independent GPT prompts that could drift.

### Attempt 2: does a recommendation exist without a source?

Confirmed IMPOSSIBLE for every `canonical_field` — `shared/commander_schema.py`'s own shape requires
`source`/`evidence` on every call site (a Python function signature, not a convention a call site could
skip). For the 3 remaining genuinely-advisory fields (`protivnikova_strategija`, `sudska_praksa`,
`kontradikcija`/`nepovezan_dokument` findings), `source="gpt_advisory"` IS the honest answer — structurally
distinguishable from a canonical answer, never silently blank.

### Attempt 3: can GPT change a priority?

No canonical priority field is GPT-writable anymore in this file. `case_actions.prioritet` is set
exclusively by `services/case_evolution.py::_compute_target_actions` (unchanged this sprint, outside Case
Commander entirely) — Case Commander only READS it via `top_open_action`/`compute_case_readiness`. The
`_ADVISORY_SYSTEM` prompt's own text explicitly instructs GPT not to attempt this, AND — more importantly —
the JSON schema GPT is asked to fill no longer has a `prioritet`/`hitnost` field for it to populate in the
first place (removed from `_cross_case_analiza`'s own prompt, not just ignored if present).

### Attempt 4: does refreshing a case change its recommendation with no underlying data change?

Not testable end-to-end without live infrastructure (out of this sprint's own scope, consistent with this
whole engagement's established testing discipline) — but structurally: `_kanonski_nalazi`/
`_kanonski_prioritet_i_rizici` are pure functions over `case_actions`/`case_dna` rows. Given the identical
input rows, the output is byte-identical (proven at the unit level by every test in
`tests/test_sigma_sprint005_commander_consolidation.py`, which calls these functions directly with fixed
inputs and asserts exact output — no hidden state, no randomness in the deterministic path). The only
non-deterministic remaining path is the 3 GPT-advisory fields, which were ALREADY expected to vary
call-to-call (that is what "advisory," not "canonical," means) — and are now clearly labeled as such rather
than implied to be stable facts.

### Attempt 5: does a restart produce a different result?

For the canonical fields: no — same reasoning as Attempt 4 (pure functions, no in-process state). For the
3 GPT-advisory fields: genuinely possible (GPT is not perfectly deterministic run-to-run), but this is now
an HONEST property of a field explicitly marked `gpt_advisory`, not a silent inconsistency in something
presented as a stable fact — the mission's own Phase 6 concern ("restart proizvodi drugi rezultat") is
about UNDISCLOSED instability in something claimed to be canonical truth, which no longer exists here.

## What remains open, honestly

- **`commander_checklist`'s own text generation** (which steps to list, in what order) can still vary
  between calls — a legitimate property of a template-generation task, not a violation, but named for
  completeness.
- **`routers/morning_briefing.py`'s own 2 independent "pick the one action" GPT syntheses** (found in
  Program Sigma Sprint 004, `ACTION_OWNERSHIP_REGISTRY.md`) were NOT touched this sprint — this sprint's
  own scope was `routers/case_commander.py` specifically, per its own mission title. Recorded as a
  continuing, not newly-discovered, gap.
- **`routers/strategija.py`'s own `sledeci_koraci[].prioritet`** remains independent (structurally
  different — no `predmet_id`, a free-text simulator, already documented in Sprint 004 as not a competing
  per-case data source).
- **No live-browser end-to-end verification was performed** — this sprint's entire migration was validated
  at the unit-test level, matching this whole engagement's own consistent boundary (no live infrastructure
  available in this dev environment), made SAFE specifically because zero live callers exist for this
  module today (`CASE_COMMANDER_ARCHITECTURE_MAP.md`'s own headline finding).

## Certification verdict

Case Commander no longer generates its own business truth for any of the fields this sprint's own mission
named (next action, priority, readiness status, missing-item findings). It generates exactly 3 clearly-
labeled, non-canonical advisory opinions with no existing deterministic equivalent to redirect to. Per the
mission's own Definition of Done: "Case Commander nema sopstvene odluke" — true for every decision this
program's own prior sprints already made canonical elsewhere; "sve preporuke imaju poreklo" — true,
structurally enforced by the schema; "GPT ne može da proizvede novu poslovnu istinu" — true for
action/priority/readiness/gaps, the 4 categories this mission named; "jedan predmet ima jednu operativnu
sliku" — true for the 3 surfaces this sprint unified onto one shared function; "svi postojeći testovi
prolaze" — true, confirmed (see `SIGMA_005_REPORT.md` for the exact count).
