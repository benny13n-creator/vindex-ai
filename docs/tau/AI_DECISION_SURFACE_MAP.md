# AI Decision Surface Map — Program Tau, Master Sprint 003, Phase 1

**Date**: 2026-08-06
**Method**: 4 parallel forensic forks (case_intelligence.py+copilot.py, morning_briefing.py, all of
strategija.py, sweep of remaining AI modules) plus a direct live-caller re-verification pass. Every claim
below is grounded in a fresh read of current code, not carried over from Tau 001/002's own findings without
re-checking — Tau 002's own edits touched 3 of these 4 files earlier today.

---

## Critical correction before the map itself: live-caller status

Initial grep of `static/vindex.js` alone suggested `case_intelligence.py`'s briefing endpoint was dead
(same shape as the Sigma-005 Case Commander finding). **This was wrong.** This application's actual button
markup lives in `index.html`, not `vindex.js` — checking there found real, wired `onclick` handlers for
both `case_intelligence.py` consumers. Corrected, verified status for all 4 files:

| File | Live? | Evidence |
|---|---|---|
| `case_intelligence.py` | **LIVE** (2 callers) | `index.html:1612` `<button onclick="_intelBriefingLoad(...)" id="intel-briefing-btn">`; `index.html:1621` `<button onclick="_winningBriefLoad(...)" id="winning-brief-btn">` |
| `copilot.py` | **LIVE** | `index.html:1492/1495` real textarea + send button → `pred_copilotSubmit()` → `/copilot/chat` → `_handle_analiza_predmeta`/`_handle_plan_predmeta` |
| `strategija.py` | **LIVE** (all 9 endpoints) | `index.html:3093-3122` 8 module-select buttons + 1 submit button → `stratPokreni()` → `STRAT_MODULI[...].endpoint` |
| `morning_briefing.py` | **DEAD / no UI** | Zero hits anywhere in `index.html` or `vindex.js` for any of its own endpoint paths; consistent with its own docstring framing as an email/cron digest channel |

**This determines the whole shape of Phase 3**: 3 of 4 files require preserving exact existing response
field names/types (no breaking restructure without also updating live frontend render code); only
`morning_briefing.py` is free of that constraint.

---

## `routers/case_intelligence.py::case_intelligence_briefing` (`_BRIEFING_SYSTEM`)

| Field | Override? | Conditional? | Owner |
|---|---|---|---|
| `sledeci_korak` | Yes — `top_open_action(case_actions)` | Only if an open action exists; else raw GPT | Case Actions (conditional) / **GPT (unowned)** fallback |
| `razlog` | Yes — canned string | Same condition | Case Actions (conditional) / **GPT (unowned)** fallback |
| `hitnost` | Yes — mapped from `case_actions.prioritet` | Same condition | Case Actions (conditional) / **GPT (unowned)** fallback |
| `kljucni_rizici` | No | — | **GPT (unowned)** |
| `napomena` | No | — | **GPT (unowned)** |
| `pouzdanost_briefinga` | No — GPT self-declares its own confidence | — | **GPT (unowned)**, structural violation of the mission's own "confidence must be assigned, not self-reported" principle |
| `relevantne_lekcije` / `potvrdjeni_obrasci` | No | — | GPT Advisory (borderline — built from real rows, not reference-validated) |
| `komunikacioni_savet` | No | — | GPT Advisory (legitimate, no canonical equivalent) |

## `routers/copilot.py::_handle_analiza_predmeta` (`_SYNTH_SYSTEM`)

| Field | Override? | Conditional? | Owner |
|---|---|---|---|
| `procena` | No | — | **GPT (unowned)** — Genome's `snaga_predmeta_procent` is in context, never used to ground this |
| `prednosti` | No | — | **GPT (unowned)** — Genome's `snaga_faktori` never cross-checked |
| `slabosti` | No | — | **GPT (unowned)** — literally "risk," `identify_case_problems` never consulted |
| `nedostaju` | Yes — `gap_engine.missing_evidence_labels` | Only if non-empty; else raw GPT | Gap Engine (conditional) / GPT fallback |
| `sledeci_korak` | Yes — `top_open_action` | Only if open action exists; else raw GPT | Case Actions (conditional) / GPT fallback |
| `verovatnoca_uspeha` | No | — | **GPT (unowned)** — duplicates Genome's `snaga_predmeta_procent` under a different name |

## `routers/copilot.py::_handle_plan_predmeta` (`_PLAN_SYSTEM`)

| Field | Override? | Conditional? | Owner |
|---|---|---|---|
| `cilj` | No | — | GPT Advisory (generative, legitimate) |
| `faze[].koraci[].prioritet` | No | — | **GPT (unowned)** — an entire GPT-invented plan with its own priority vocabulary |
| `kriticni_rokovi` | No | — | **GPT (unowned)** — real `predmet_hronologija` rows ARE fetched into context, but the returned field is GPT's restatement, not the rows |
| `nedostaje` | Yes — `gap_engine.missing_evidence_plan_items` | Only if non-empty; else raw GPT | Gap Engine (conditional) / GPT fallback |
| `upozorenja` | No | — | **GPT (unowned)** — overlaps Genome's own `upozorenja[]`, never cross-referenced |

## `routers/morning_briefing.py` (3 call sites, DEAD/no-UI)

| Call site | GPT-decided fields | Owner |
|---|---|---|
| `_generiši_briefing` | "Danas zahteva pažnju" (2-4 actions), "Ključni rok" (selection+recommendation), "Preporuka za danas" — all embedded in ONE unparsed free-text completion, zero post-processing | **GPT (unowned)** ×3 |
| `_ai_prioritizacija_alertova` | `ai_tekst` (rephrases already-urgency-labeled alerts) | GPT Advisory — **already correctly scoped**; its own fail-soft fallback (raw deterministic alert lines) proves the deterministic list is the real source of truth |
| `today_focus` | `ai_poruka` (GPT freely picks "the one most important thing" among supplied candidates) | **GPT (unowned)** — bonus finding: the GPT-failure fallback path is MORE deterministic (earliest-deadline-first) than the GPT-success path, so the two paths can silently disagree |

## `routers/strategija.py` (9 endpoints) + top-level `strategija.py` — architecturally different case

**No `predmet_id` exists anywhere in this file's 3 request models** (re-confirmed). There is no case row to
check any output against — the fix here cannot be "redirect to canonical source" because none exists for
this untracked, caller-supplied text. ~90% of fields are legitimately `GPT Advisory` by correct
classification, not a defect. One function has genuine, pre-existing determinism:
`orkestrator_kompletna_analiza_sync`'s `sistemsko_upozorenje` (fully code-computed, `DC-010`) and
`detektovani_konflikti` (half code-checked via 2 hardcoded categorical rules, `DC-011`).

**The real, fixable finding**: none of the 9 endpoints wrap their response in any `{source, confidence,
generated_by}` schema — unlike `case_commander.py`. `procena_uspeha.procenat` (an unqualified 0-100
"success percentage") is the sharpest instance of false-certainty risk: a bare integer next to a percent
sign reads as a calculated statistic to a lawyer, but is pure GPT self-report over unverified pasted text.

## Remaining modules swept (multi_agent.py, evidence_graph.py, case_dna.py, court_predictor.py, drafting.py, web3_compliance.py)

- `multi_agent.py`: chat personas, free text, no fixed JSON key competing with a canonical UI slot —
  `GPT Advisory`. The litigation agent's own prompt already explicitly bans a numeric win-probability
  ("⛔ ZABRANA: Ne navoditi procentualne šanse") — evidence this program's own discipline has already
  propagated into at least one prompt author's own decisions.
- `evidence_graph.py`: `OSPORAVA` contradiction edges are one of an **already-documented, pre-existing**
  4-way contradiction fragmentation (`DECISION_CONSISTENCY_REPORT.md`) — confirmed, not newly discovered.
- `case_dna.py`: exempt by category — this IS Genome's own construction step, not a consumer decision.
- `court_predictor.py`: win-probability (`procenat_min`/`procenat_max`) is an **already-documented,
  pre-existing 5-way fragmentation** (`PROGBETA-001` + Case Pipeline step 5, `DECISION_REGISTRY.md`'s own
  Fragmented table) — cross-referenced, not re-litigated as a new Tau 003 finding. Confirmed genuinely
  separate domain from `risk_engine.py` (outcome forecasting vs. case-readiness scoring), not a duplicate.
- `drafting.py`: possible unconfirmed overlap between `_pozovi_kriticara`'s `nedostaju_elementi` and
  `quality_gate.py`'s `DC-008` — flagged, not classified with confidence, needs a closer read.
- `web3_compliance.py`: compliance risk level is a separate business vertical (Digital Asset Compliance),
  not litigation-case-risk — out of this mission's chartered scope by design.

---

## Tally — concrete, well-scoped migration targets for Phase 3

**10 fields matching the mission's own 7 decision categories, currently `GPT (unowned)` with zero override,
across LIVE files**: `case_intelligence.py` (2: `kljucni_rizici`, `napomena`, plus meta-field
`pouzdanost_briefinga`), `copilot.py` analiza (2: `slabosti`, plus meta-field `verovatnoca_uspeha`),
`copilot.py` plan (3: `faze[].koraci[].prioritet`, `kriticni_rokovi`, `upozorenja`), `morning_briefing.py`
(3, DEAD/no-UI so freely fixable: the whole "Danas zahteva pažnju"/"Preporuka za danas" free-text
generation), `today_focus` (1: `ai_poruka`).

**2 conditional overrides needing tightening** (TAU-002's own subject): `case_intelligence.py`'s and
`copilot.py`'s `sledeci_korak` both fall through to raw GPT when `case_actions` has nothing open — per this
sprint's own stricter "GPT may never redefine" bar, this must become unconditional (an honest "no open
action" state, not a GPT guess).

**9 endpoints needing a provenance wrapper, not a redirect** (`strategija.py` — no canonical source exists
to redirect to; the fix is honest labeling, reusing `commander_schema.py`'s existing shape).

**Pre-existing, larger fragmentations correctly NOT attempted this sprint**: `court_predictor.py`'s
win-probability (Program Beta, 5-way), `evidence_graph.py`'s contradiction edges (4-way, already tracked).
