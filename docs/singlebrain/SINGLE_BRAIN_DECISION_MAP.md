# SINGLE_BRAIN_DECISION_MAP.md — Operation Single Brain, Mission 002

Decision Authority Map, synthesized from 6 independent forensic teams (2026-08-07), each instructed
to re-verify current code rather than trust Mission 001's own docs. Every claim below is either
independently confirmed by 2+ teams, or backed by an actual reproduction (a real function call with
synthetic/poisoned input, not a code-read argument alone).

## Readiness — HIGH risk, the mission's headline target

| | |
|---|---|
| Canonical owner (this mission designates) | `shared/case_readiness.py::compute_case_readiness()` — deterministic, 5-state enum, zero GPT calls, no injectable GPT parameter (Team 3 confirmed by full read) |
| Competing source #1 | `services/case_pipeline.py::calculate_case_ready_score()` — independent 0-100 weighted checklist (docs/clients/deadlines/strategy-ran/risk-ran/hearing-exists), zero overlap with `case_actions`/Gap Engine |
| Competing source #2 (dead) | `routers/matter_intel.py::preflight_check()` — GPT-native 3-state, zero frontend callers (Team 1 + Team 2 both confirmed via grep) |
| Consumers of the checklist score | 3 frontend render sites, all showing the SAME value (`static/vindex.js:10480-10526`, called at `:10543`/`:11961`, plus the intake-wizard result screen `:20610-20648`) — Team 2's correction to Mission 001's own debt entry: these are not 3 competing systems, they're 3 renders of 1 system |
| Consumers of the canonical status | `shared/case_context.py::build_case_context()` → `CAP_BY_READINESS` clamp on 4 GPT probability generators (`court_predictor.py::prediktuj_ishod`, `digital_twin.py` ×2, `hearing_cc.py`). **No direct UI badge for the 5-state enum exists anywhere** (Team 1 confirmed) |

**Proven disagreement (Team 2, real reproduction against the actual functions, not theorized)**: a case with a full checklist (docs+clients+deadlines+strategy-ran+risk-ran+hearing) scores **100/100 → "Predmet spreman za rad"** on the main case screen. The identical case with one open `case_actions` row (`prioritet="critical"`) simultaneously computes **CRITICAL_GAP** via the canonical engine — which silently caps that same case's Court Predictor/Hearing CC/Digital Twin probability numbers to ≤50% on other tabs, with the reason never surfaced. This precondition (checklist complete + a later-discovered critical gap) is not an edge case — it's a normal point in a real case's lifecycle.

**Verdict**: genuine, live, high-severity fragmentation. Fixed this mission — see `FRAGMENTATION_ELIMINATION_REPORT.md` §1.

## Next Action — MEDIUM-HIGH risk, newly mapped as its own category

Mission 001 never separately catalogued this. Team 1 found a genuine, currently-live duplicate:

- **Canonical**: `shared/case_readiness.py::top_open_action()` — single highest-priority open `case_actions` row.
- **Duplicate #1**: `services/case_pipeline.py::_step_copilot_preporuka` (STEP 8) independently re-derives "what to do" via `identify_case_problems()` and renders it as **"Copilot preporuka"** directly beside the Case Ready Score checklist (`static/vindex.js:10519-10525`) — same screen area as `top_open_action()`'s answer shown in the AI Briefing panel elsewhere. Both deterministic (no hallucination risk), but different inputs with different freshness — not guaranteed to agree.
- **Duplicate #2**: `routers/copilot.py::_handle_predlozi` — its own ad hoc priority/next-step generator, bypassing `case_actions` entirely (Team 1 + Team 6 both found this independently). Its per-item list isn't rendered (only a summary count), narrowing but not eliminating the exposure.
- **Duplicate #3, newly found**: `routers/zastarelost.py` runs its own independent deadline-urgency thresholds (`kritično/hitno/prati/planiraj`, ≤3/≤7/≤14 days) parallel to `case_evolution.py::_priority_by_days` (≤3/≤7) — currently harmless only because the cutoffs happen to coincide today.

**Verdict**: not fixed this mission (would require consolidating 3-4 independent generators, a larger scope than this mission's time budget) — named as debt.

## Success Probability — HIGH risk, mostly closed, one gap confirmed open

5 GPT-generated percentages. 4 of 5 are readiness-capped via the now-single shared `CAP_BY_READINESS` constant (Mission 001's own fix, re-confirmed genuinely consolidated by Team 1). The 5th — `court_predictor.py::argument_reputation`'s `uspesnost_procena`/`ukupna_snaga` — is range-clamped but **never checked against readiness** (`SINGLEBRAIN-DEBT-002`, independently re-confirmed by Team 1 and Team 3). Fixed this mission — see `FRAGMENTATION_ELIMINATION_REPORT.md` §2.

**New, more serious finding (Team 3, reproduced)**: `routers/strategija.py`'s F10 "AI Sudija" orchestrator step returns `procena_uspeha_tuzilac` with **zero server-side clamp or validation** — the frontend only clamps the progress-bar *width*, the displayed number text is raw GPT output. A poisoned response (`procena_uspeha_tuzilac: 9999`, unenumerated `izreka`/`confidence` strings) was proven to pass through unmodified into the live, UI-wired `POST /api/strategija/kompletna-analiza` response. This is the single most direct violation found of the mission's own Acceptance Criterion 2 ("no lawyer-facing UI displays an unsupported AI-generated decision"). Fixed this mission — see `FRAGMENTATION_ELIMINATION_REPORT.md` §3.

## Case Strength — MEDIUM risk

Per-case value (`case_dna.snaga_predmeta_procent`) is genuinely single-sourced (`genome_validator.py::compute_snaga_score`). Portfolio-level *aggregation* diverges between `health_index.py` and `cio.py` (different population filters, `SINGLEBRAIN-DEBT-003`, re-confirmed unchanged) — not fixed this mission, scope too large relative to value (the two currently produce the same practical population since the extra filter values are never written).

**New finding (Team 6, Team 1)**: `snaga_predmeta_procent` itself surfaces unlabeled in 2 lawyer-facing places that read like a *different* metric — CIO's portfolio panel and Copilot's "Verovatnoća uspeha" — with no shared vocabulary, no staleness indicator, and (per Team 4) a Case Genome hero panel that derives its own "Visok rizik"/"Srednji rizik" LABEL from this same strength score, using the word "rizik" for a completely different formula than the risk engine's "rizik". Not fixed this mission (a labeling/UX decision, not a mechanical bug) — named as debt.

**New finding (Team 3)**: Genome's own `heatmap` and `dokazi_rang[].snaga_score` sub-fields were never enum/range-guarded (only the headline `snaga_predmeta_procent`/`kriticnost`/`genome_kompletnost` were, in Mission 001) — same "guarded the headline, missed the sibling field" pattern. Fixed this mission — see `FRAGMENTATION_ELIMINATION_REPORT.md` §4.

## Health — LOW risk (genuinely improved)

Firm-level Health Index's Portfolio Risk sub-component (confirmed dead by Mission 001, now confirmed fixed by both this mission's Team 1 and Team 5). One naming trap, not a data bug: 3 unrelated concepts share the literal field name `health_score` (firm-wide Health Index; risk_engine's per-case inverse-of-risk number; Web3's AML documentation-completeness score) — each is internally single-sourced within its own domain. Not fixed this mission (rename would touch many call sites for a naming-only issue) — named as debt.

## Risk — HIGH risk, mostly closed by Mission 001, 2 items re-confirmed still open

Canonical: `services/risk_engine.py::calculate_procesni_rizik`. Team 5 independently re-verified Mission 001's own fixes to `health_index.py` and `dashboard.py::command_center` genuinely hold in current code (correcting stale claims still visible in the mid-mission `docs/singlebrain/*.md` drafts from Mission 001, which captured pre-fix state). Still open: `GET /api/portfolio` reads the stale `"[Rizik]"` cache directly — confirmed dead/orphaned (zero frontend callers, Team 5) — low practical risk, named as debt rather than fixed. `matter_intel.py::get_uncertainty_dashboard` still dead, still a landmine via direct API call — named as debt.

**New finding (Team 6, concrete same-screen divergence)**: `routers/ccc.py`'s hearing query has `.limit(10)` while `routers/matter_intel.py`'s equivalent query is unbounded — both feed `calculate_procesni_rizik`, so a heavy-docket case (>10 hearings) can show two different health/risk badges on the same case screen. Fixed this mission — see `FRAGMENTATION_ELIMINATION_REPORT.md` §5.

## Urgency / Priority — MEDIUM risk

`shared/attention_priority.py` remains a genuine, correctly-scoped consolidation. Confirmed still-open: `copilot.py::_handle_predlozi`'s bypass (see Next Action, above — same root cause, listed once). Not independently fixed further this mission.

## Confidence — MEDIUM risk, UI-only fragmentation newly mapped

Team 4 found "pouzdanost"/confidence means 4 different things on one case page (RAG source-grounding confidence, Genome completeness-as-confidence proxy, the Sveobuhvatna Procena report's own independent confidence verdict, and firm-wide historical calibration bands) — none share a scale. Not fixed this mission (a UI/labeling consolidation, not a mechanical guard) — named as debt.

## Cross-cutting structural note

`routers/case_commander.py` is, by design, the platform's most architecturally correct consumer of
all 8 decision concepts — zero independent GPT decisions, reads `build_case_context()` exclusively.
It has **zero live frontend callers** (Team 1, re-confirmed). The best-designed consolidation is
invisible to lawyers; the fragmented sources are what's actually rendered. Wiring it up is explicitly
named as the next mission's highest-leverage move, NOT attempted here — doing so without first
finishing the readiness consolidation above would have created a new, immediately-visible 3-way
collision instead of resolving one.

See `READINESS_AUTHORITY_SPEC.md` for the CANONICAL_OWNER contract this mission implements for
Readiness specifically, and `FRAGMENTATION_ELIMINATION_REPORT.md` for the full fix ledger.
