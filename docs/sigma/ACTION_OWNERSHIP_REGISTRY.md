# Action Ownership Registry — Program Sigma, Master Sprint 004 (2026-08-06)

Phase 1 (Forensic Action Map) and Phase 2 (Action Ownership) deliverable: every mechanism repo-wide that
generates a recommended action, next step, task, reminder, recommendation, warning, or suggested move,
classified CANONICAL/PROJECTION/LEGACY/DUPLICATE/DEAD, with file:line citations (2 forensic forks).

## CANONICAL

| Mechanism | File:line | Notes |
|---|---|---|
| `case_actions` | migration 099, populated by `services/case_evolution.py::_compute_target_actions` | The platform's own established, deterministic, stateful action-tracking table. Unchanged this sprint. |
| `api.py`'s `_COCKPIT_SYSTEM` prompt | `api.py:5058-5068` | Re-verified compliant — explicitly instructs GPT "ne predlazi sledecu akciju, to nije tvoj posao." Still a positive AR-01 example. |
| `routers/cio.py::cio_preporuka` | `routers/cio.py:6-12` | **Already self-documented as non-canonical** by its own docstring (Program Omega Sprint 004): *"cio_preporuka is GPT-generated portfolio-level narrative, NOT a canonical operational source. The canonical answer to 'what should the lawyer do today' is GET /api/workspace."* A prior sprint correctly disclaiming, not a new violation. |

## DUPLICATE — fixed this sprint

| Mechanism | File:line | Fix |
|---|---|---|
| `routers/case_intelligence.py`'s AI Briefing `sledeci_korak`/`hitnost` | `case_intelligence.py:66-76` (prompt), `:389` (response) | Independently GPT-generated "single most urgent action" + urgency tier, disconnected from `case_actions`. **Fixed**: overridden with `shared/case_readiness.py::top_open_action`'s own reading of `case_actions` whenever an open row exists; GPT's own value kept only as a fallback when no case_actions row exists yet. |
| `routers/copilot.py::_handle_analiza_predmeta`'s `sledeci_korak` | `copilot.py:341` (prompt), `:437` (response, pre-fix) | Own `{"opis","rok","prioritet":"hitan\|normalan"}` shape, independently GPT-generated. **Fixed**: same override pattern, `prioritet` translated from `case_actions`' own canonical value (critical/high → hitan; medium/low/informational → normalan). |

## DUPLICATE — confirmed, NOT fixed this sprint (named, with reasoning)

| Mechanism | File:line | Why not fixed |
|---|---|---|
| **`routers/case_commander.py`** — the sprint's own single largest finding | `_COMMANDER_SYSTEM` (lines 36-62), `_dohvati_predmet_kontekst` (78-136, reads `predmeti`/`rokovi`/`predmet_dokumenti`/`predmet_komentari` directly — **never reads `case_actions`, `case_dna`, or `identify_case_problems`**) | An entire module with 8 independent GPT-generated recommendation surfaces (`NEDOSTAJE`, `RIZICI`, `PREPORUCENI POTEZ`, `VREMENSKI PRITISAK` inside `_COMMANDER_SYSTEM`; `commander_quick_check` line 282; `commander_checklist` line 338; `_cross_case_analiza`'s own independent portfolio `"prioritet"` object, lines 488-620; `commander_jutarnji` line 630) — none reading any canonical source. Rewiring 8 GPT prompts across an entire module, each needing its own live-browser verification pass, is not a same-sprint, safely-completable fix — it is its own dedicated future sprint. See `READINESS_FORENSIC_REPORT.md` for the full severity assessment. |
| `routers/morning_briefing.py` — 2 independent GPT "pick the one action" syntheses in the same file | Lines 185-204 ("Preporuka za danas"), lines 1054-1094 (separate call, "izaberi JEDNU najvazniju akciju") | Same reasoning — 2 more independent GPT prompts, each needing individual live verification before a safe swap to a `case_actions` read; bundling into this sprint risks a rushed, under-verified change to a live daily-digest feature. |
| `routers/copilot.py::_handle_plan_predmeta`'s `faze[].koraci[].prioritet` | `copilot.py:472-478` | Architecturally different from the "single next action" fields fixed above — this is a genuinely GPT-synthesized MULTI-STEP PLAN (up to 3 phases, up to 4 steps each), not one action. `case_actions` has no "phased plan" concept to read from. Its own priority vocabulary (`hitan\|normalan\|odlozen`, a 3rd distinct vocabulary found this sprint) still competes with the canonical one, but consolidating a multi-step plan onto a flat action list is a genuine design question, not a mechanical swap. |
| `routers/strategija.py`'s `sledeci_koraci[]` | Line 363, `StrategijaV2Request` (374-377) | **Structurally different, not force-merged**: this request model has NO `predmet_id` field at all — a free-text what-if simulator, not tied to any specific case row, cannot structurally write to or read from `case_actions`. A duplicate of the *concept* "next steps," not a competing per-case data source. |

## A side-finding, outside this sprint's own directive, flagged for awareness

A `rokovi` table is read by 8+ files (`case_commander.py` ×2, `api.py`, `dashboard.py`, `decision_replay.py`,
`integrations.py`, `morning_briefing.py` ×2, `whatsapp_notif.py` ×2+) but **no `CREATE TABLE rokovi` exists
in any migration file** (grepped all of `migrations/*.sql`). Either created outside migration tracking, or
a widespread silent-failure risk. Not chased further this sprint — outside Phase 1's own scope
(action-generator mapping, not schema audit) — named here so it isn't lost.

## PROJECTION / DEAD

`routers/health_index.py` — no action/recommendation prompts found, confirmed still out of this domain
(unchanged from Sprint 001's own finding). `routers/multi_agent.py:531-532` — only reads an already-computed
`preporuka` field into context, not an independent generator.
