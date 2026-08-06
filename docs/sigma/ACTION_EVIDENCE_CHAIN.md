# Action Evidence Chain — Program Sigma, Master Sprint 004 (2026-08-06)

Phase 3 deliverable: every action must know why it exists, which evidence caused it, which fact/document/
gap/event is connected. If it has no origin, it is not valid.

## Confirmed this sprint: already clean, by construction

All 5 rules in `services/case_evolution.py::_compute_target_actions` populate `dokaz` (the schema's own
NOT NULL DEFAULT `'{}'::jsonb` column, migration 099) with real, non-empty, traceable content:

| Rule | `dokaz` content |
|---|---|
| Rule 1 (deadlines, from `rocista`) | `{"rociste_id", "sud", "datum", "dani_preostalo"}` |
| Rule 2 (missing-evidence/predstojeci-rokovi/weak-evidence, from `identify_case_problems`) | `{"izvor": "identify_case_problems", "problem": <exact text>}` |
| Rule 3 (contradictions, from Genome's `kontradikcije[]`) | `{"opis", "lokacija_1", "lokacija_2", "tezina"}` |

**Repo-wide grep for every `case_actions` write confirmed exactly ONE call site**
(`services/case_evolution.py:765`, inside `_consequence_refresh_case_actions`, the reconcile loop that
consumes `_compute_target_actions`' own output). No other code path anywhere can insert a `case_actions` row
— meaning no path exists that could create an evidence-less action. This is the mission's own "ako nema
poreklo, akcija nije validna" requirement, satisfied structurally, not by a runtime check.

## Traceability beyond `dokaz` itself

Every `case_actions` row also carries `dedupe_key` (a stable identity — `_stable_key(...)`-derived for
Rules 1/2, and, since Program Sigma Sprint 002/003, `shared/contradiction_identity.py`-derived for Rule 3,
immune to GPT phrasing drift) and `izvor_dokumenti` (the specific document citations for Rule 3). Combined,
a lawyer — or an auditor — can trace any action back to: which rule created it, what raw data it read, and
(for contradictions) which 2 specific document/page citations are in conflict.

## This sprint's own 2 fixes extend the same discipline to next-action surfaces outside `case_actions`

The 2 fixes in `ACTION_OWNERSHIP_REGISTRY.md` (`case_intelligence.py`'s AI Briefing,
`copilot.py::_handle_analiza_predmeta`) now surface `case_actions`' own `dedupe_key` directly in their own
response's `razlog` field (e.g. `"Najviši prioritet u Case Actions (case_actions.dedupe_key=%s)"`) — the
lawyer-facing text itself now names the traceable source, not just an internal data structure a lawyer
never sees.

## What remains, honestly

`routers/case_commander.py`'s own 8 independent recommendation surfaces (named in full in
`ACTION_OWNERSHIP_REGISTRY.md`) have NO evidence-chain discipline at all — they read raw `predmeti`/
`rokovi`/`predmet_dokumenti`/`predmet_komentari` rows directly and hand them to GPT, with no structured
`dokaz`-equivalent field, no `dedupe_key`, no stable identity. Any recommendation Case Commander produces
today fails this sprint's own "ako nema poreklo, akcija nije validna" test — named as `SIGMA-018` in the
Debt Register (folded into the same major finding as `ACTION_OWNERSHIP_REGISTRY.md`'s own Case Commander
entry), not fixed this sprint for the reasons given there.
