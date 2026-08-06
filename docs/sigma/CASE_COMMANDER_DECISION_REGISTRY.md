# Case Commander Decision Registry — Program Sigma, Master Sprint 005 (2026-08-06)

Phase 2 deliverable: for every duplicated decision found in `CASE_COMMANDER_ARCHITECTURE_MAP.md`, the
canonical source it was redirected to, and the exact before/after.

## "Nedostaje dokaz X" — worked example from the mission's own brief

**Before**: `commander_analiza`'s own `_COMMANDER_SYSTEM` prompt asked GPT to independently list
"NEDOSTAJE" — GPT re-derived a missing-evidence list from raw `predmet_dokumenti`/`predmet_komentari` text,
with no reference to `case_actions`, Genome, or `identify_case_problems`.

**After**: `_kanonski_nalazi(ctx)` builds `nedostaje` directly from `shared/gap_engine.py::collect_case_gaps`
(itself normalizing `identify_case_problems` + Genome's own `nedostaje[]`) — the SAME function
`routers/copilot.py` was migrated to use in Program Sigma Sprint 003. If `case_actions` already has a
`PRIBAVITI_DOKAZ` action for this fact, that IS the answer; Case Commander does not re-decide it.

## `PREPORUCENI POTEZ` / `quick_check`'s own top warning / `_cross_case_analiza`'s own `prioritet`

**Before**: 3 independent GPT-invented "what's the one most important thing" answers, each with its own
prompt, own vocabulary, own reasoning — none reading `case_actions`.

**After**: all 3 now call `shared/case_readiness.py::top_open_action` (per-case) or the new
`_kanonski_prioritet_i_rizici` (portfolio-wide, ranks cases by `compute_case_readiness`'s own status —
`CRITICAL_GAP > BLOCKED > PARTIALLY_READY > READY`, tiebreak by nearest deadline). Same functions Program
Sigma Sprint 004 built for `routers/case_intelligence.py`/`routers/copilot.py` — reused, not reinvented.

## `RIZICI` (per-case) / `_cross_case_analiza`'s own `nalazi[tip=="rizik"]` (portfolio-wide)

**Before**: GPT free-text risk enumeration from raw case text, per-case AND independently again at the
portfolio level (2 separate GPT-invented risk lists for the same underlying facts).

**After**: per-case, `identify_case_problems(rizik, tip)` directly (the platform's own established
deterministic algorithm, Core Consolidation 2026-07-22). Portfolio-wide, the top 5 open `case_actions`
across all of a lawyer's cases, sorted by `shared/attention_priority.py`'s own canonical order — reading
the SAME already-computed rows, not recomputing risk from scratch per case in a portfolio loop (which would
have been expensive AND yet another independent computation).

## What was NOT redirected, and why — the 3 genuinely GPT-advisory surfaces

| Field | Why no canonical source exists |
|---|---|
| `PROTIVNIKOVA STRATEGIJA` ("what will opposing counsel likely do") | No deterministic system in the platform reasons about opposing-party behavior — this is a genuinely different question than "what's wrong with MY case," which is all `identify_case_problems`/Genome answer |
| `SUDSKA PRAKSA` (pattern in similar cases) | Distinct from the deterministic risk/gap findings — a narrative synthesis question, not a fact-check |
| `KONTRADIKCIJE`/`NEPOVEZANI DOKUMENTI` at the PORTFOLIO level (cross-case, or beleška-vs-document) | Genome's own `kontradikcije[]` is per-case only; nothing in the platform compares notes against documents, or documents across DIFFERENT cases, for contradictions |

All 3 are kept, but reclassified via `shared/commander_schema.py::gpt_advisory_field` — `source:
"gpt_advisory"`, `evidence: None` always, `confidence` capped low — structurally distinguishing "GPT's own
opinion" from "the platform's own established fact," matching Program Sigma Sprint 003's own
"hipoteza, ne činjenica" discipline, applied here to Case Commander specifically.

## `commander_checklist`'s own `completed` field

**Before**: GPT's own `[x]`/`[ ]` markdown checkbox marker, taken as if it reflected real case state — a
generic procedural template (e.g. "Priprema → Tužba → Postupak → Zaključenje") has no per-case data to
check against at all, so any `[x]` GPT produced was pure invention.

**After**: `completed` is always `False`. GPT may still propose WHICH steps a case of this type typically
requires (a legitimate templating task, `A` classification) — it may never claim one is already done.
