# INTELLIGENCE_SURFACE_MAP.md — Operation One Truth, Phase 1

*Synthesized from 7 independent forensic teams (Agents 1-7), 2026-08-07. Every claim below traces to a
specific team's file:line evidence — see `docs/onetruth/AGENT_REPORTS_RAW.md` for full per-agent reports.
Principle 0 applied throughout: no documentation, prior certification, code comment, or function name was
trusted without independent code verification by at least one team.*

This document maps every AI/deterministic case-assessment surface in the platform: who generates it, from
what data, whether it uses a canonical source, whether it calls GPT, and where it renders.

## Category 1 — Case Strength / Snaga predmeta

| Generator | Source | Canonical? | GPT? | Renders |
|---|---|---|---|---|
| `routers/case_dna.py::_extract_genome` → `case_dna.snaga_predmeta_procent` | Genome extraction, backend-recomputed via `shared/genome_validator.py::compute_snaga_score()` from `snaga_faktori` (NOT GPT's raw self-report) | **Canonical for this field** — single generation site | Yes (extraction), but score is deterministically recomputed | Genome panel, feeds `build_case_context()` |
| `routers/health_index.py::_compute_health` | Own loop over active cases' `case_dna.snaga_predmeta_procent` | Independent aggregation logic | No | Dashboard Health Index widget |
| `routers/cio.py::_generiši_cio_izvestaj` | Own, separately-coded loop, `prosecna_snaga` | Independent aggregation logic, different case-inclusion criteria than Health Index | No | CIO panel |

**Verdict**: base value is well-consolidated (1 generation site). Two independent, differently-filtered
*portfolio aggregations* of that same value can diverge and both render simultaneously on the dashboard.

## Category 2 — Risk / Rizik / Procena rizika

| Generator | Source | Canonical? | GPT? | Renders |
|---|---|---|---|---|
| `services/risk_engine.py::calculate_procesni_rizik` | Deterministic, from `predmet_dokazi`/`rocista`/documents | **The formula IS canonical** — verified single implementation across 11 call sites (Red Team) | No | Cockpit badge (live), Matter Intel bar, CCC (mostly) |
| `predmeti.rizik` (DB column) | Manually-set free-text dropdown, no CHECK constraint | **Not canonical** — no recompute trigger, PATCH-only | No | Status panel badge (**wins** over the live Cockpit value when set — `static/vindex.js:11897-11901`); fed as ground truth into Digital Twin (`digital_twin.py:241`, default fallback `"srednji"`) and Hearing CC (`hearing_cc.py:311`) AI prompts |
| `predmet_istorija` `"[Rizik] {date}"` cached tag | Snapshot of the live engine's output, written once at case creation + lazily on Workspace-open only | **Formula is canonical, cache staleness is not managed** — no event in `CONSEQUENCE_REGISTRY` re-writes this tag | No | Dashboard case-list risk badge, `GET /api/portfolio` |
| `routers/ccc.py`'s own local deadline-count loop | Naive-datetime bug (`TypeError` silently swallowed), same bug class already fixed once in `risk_engine.py` | **Not canonical — a live regression**: the canonical values are computed 2 dozen lines above in the same function and then discarded | No | CCC "next critical hearing" panel (effectively always empty) |
| `routers/matter_intel.py::get_uncertainty_dashboard` | Reimplements the identical naive-datetime bug in a sibling endpoint of the SAME file that correctly uses the canonical engine elsewhere | Not canonical, dead-adjacent (no frontend caller found, but live if called) | Partially (feeds GPT prompt) | Not currently rendered (orphaned) |

**Verdict**: the single most consequential finding of this mission. The *scoring formula* is genuinely
unified — but a manual DB column, a stale cache, and a broken duplicate calculation all sit alongside it and
can each independently disagree with the live canonical value, on 5+ distinct surfaces. 5 of 7 forensic
teams independently converged on some manifestation of this.

## Category 3 — Case Readiness / Spremnost / Case Ready Score

| Generator | Source | Canonical? | GPT? | Renders |
|---|---|---|---|---|
| `shared/case_readiness.py::compute_case_readiness` | Deterministic 5-state model from `case_actions.prioritet` + gap_engine | **Canonical** — used to cap AI outputs in digital_twin/court_predictor/hearing_cc/case_commander/cio | No | Not directly rendered as its own widget; consumed via `build_case_context()` |
| `services/case_pipeline.py::calculate_case_ready_score` | Independent weighted checklist (docs/klijenti/rokovi/strategija-tag/rizik-tag/rociste) | **Not canonical** — different criteria, never reconciled with the above | No | `pred_renderCaseReadyScore()`, case detail gauge, labeled "spreman/delimično spreman/zahteva dopunu" — same vocabulary as the canonical model, different mechanism |
| `routers/matter_intel.py::preflight_check` | GPT-4o generates `status`/`score` directly | Not canonical, GPT-native | Yes | **Dead — zero frontend callers found** |

**Verdict**: 2 live sources using the same Serbian vocabulary for what a lawyer would read as one concept,
confirmed to co-render on the case detail page.

## Category 4 — Success Probability / Verovatnoća uspeha

| Generator | Source | Canonical? | GPT? | Renders |
|---|---|---|---|---|
| `routers/digital_twin.py::kreiraj_simulaciju`/`sta_ako_analiza` | GPT-4o, capped only at readiness extremes (CRITICAL_GAP/BLOCKED) | Not canonical, partially bounded | Yes | Digital Twin panel (×2 sub-features) |
| `routers/court_predictor.py::prediktuj_ishod` | GPT-4o + RAG, same readiness cap mechanism | Not canonical, partially bounded | Yes | Court Predictor panel |
| `routers/court_predictor.py::argument_reputation` | GPT-4o, **no deterministic clamp at all** | Not canonical, unbounded | Yes | Argument Reputation panel |
| `routers/hearing_cc.py::hearing_command_center` `hearing_score` | GPT-4o, same readiness cap | Not canonical, partially bounded | Yes | Hearing CC panel |
| `routers/copilot.py::_handle_analiza_predmeta` `verovatnoca_uspeha` | **= `genome.snaga_predmeta_procent` directly** — already fixed by a prior sprint | **Canonical (deduplicated)** | No (aliased) | Copilot chat |

**Verdict**: 4 independently-prompted GPT percentages for "will this case succeed," none cross-checked
against each other or against Genome's own strength score — only Copilot has actually been fixed to alias
the canonical value. This is the "5-7 unreconciled scores" finding Iron Lawyer's UX audit already surfaced
at the presentation layer; this mission confirms it is equally unreconciled at the computation layer.

## Category 5 — Confidence / Pouzdanost (most fragmented category — 7 algorithms)

7 distinct, independently-coded confidence/reliability scales found (court_predictor's own 2 internal
scales, a fully dead `confidence_calibrator.py`, case_intelligence's own briefing-confidence formula,
judge_profile's odluke-count formula, opponent_intel's mostly-GPT-self-declared scale, Genome's own
`genome_kompletnost`, and `genome_validator.py::verify_genome`'s 3-state decision) — see Agent 1's full
report for the complete table. None share a scale; several overlap in what they claim to measure.

## Category 6 — Missing Evidence / Gaps — GOOD, single source

`shared/gap_engine.py::collect_case_gaps()` correctly aggregates 3 pre-existing sources
(`identify_case_problems`, Genome's `nedostaje[]`, Genome's `kontradikcije[]`) with an explicit
`hipoteza: True/False` tag distinguishing deterministic findings from GPT hypotheses. Verified consumed
correctly by `build_case_context()`, `case_commander.py`, `copilot.py`. **No fix needed.**

## Category 7 — Priority / Prioritet / Hitnost — mostly GOOD, 1 live gap

`shared/attention_priority.py` is a genuine, well-documented 5-source translation layer. **Gap**:
`routers/copilot.py::_handle_predlozi` computes its own ad hoc priority purely from deadline proximity,
bypassing both `case_actions` and the translation layer — a 6th, uncoordinated vocabulary live in Copilot's
"PREDLOZI" intent.

## Category 8 — Next Action / Sledeća akcija — mostly GOOD, 1 live gap

Canonical: `identify_case_problems` + `shared/case_readiness.py::top_open_action`, correctly reused by
`case_intelligence.py`, `case_commander.py`, `copilot.py`'s main analysis handler, Matter Intel, Cockpit.
**Gap**: the same `_handle_predlozi` handler above independently generates its own action suggestions from
raw deadline/document/note-staleness queries — a live, un-migrated 4th "next action" generator.

## Category 9 — Contradiction Severity — GOOD, well-scoped

Single generation site (`case_dna.kontradikcije[].tezina`), identity-tracked, severity-normalized.
`case_commander.py`'s cross-case GPT contradiction detection is a deliberately different, explicitly-tagged
domain (`gpt_advisory`), not a duplicate. **No fix needed.**

## AI Boundary — where GPT can author or override a near-canonical fact (Agent 3)

1. **`genome_validator.py::verify_genome()` is advisory-only** — a `require_review` decision (hallucinated
   document reference, internally-inconsistent score) never blocks the write, and is invisible to every
   downstream consumer (`build_case_context()` never reads `_verifikacija`). A flagged-bad Genome propagates
   through Court Predictor, Hearing CC, CIO, Copilot, and Digital Twin with the same trust level as a clean
   one.
2. **`najslabija_tacka.kriticnost`** (Case Genome, 0-100) is fully GPT-authored with zero clamping —
   reaches the DB, `build_case_context()`'s `key_facts`, and drives proactive-alert urgency math, unlike its
   sibling field `snaga_predmeta_procent` which IS correctly backend-recomputed.
3. **Court Predictor's Judge Profile** invents specific-sounding statistics (`stopa_potvrdjivanja_zalbi` —
   "appeal confirmation rate") with **no real per-judge data source anywhere in the codebase** — presented
   to the lawyer as if measured.

Where the boundary genuinely holds (verified, not assumed): `risk_engine.py` itself (zero GPT calls),
`case_readiness.py` (zero GPT calls), Genome's `snaga_predmeta_procent` (backend-recomputed, not GPT's raw
number), Matter Intel's `preflight_check` score/status (clamped + enum-validated post-BLACKSWAN-AI-001),
Hearing CC's `hearing_score` (clamped + readiness-capped), CIO's `kriticnost` (clamped) plus
reference-validated against real portfolio IDs, Court Predictor's own Confidence Check (purely deterministic
formula, GPT explicitly forbidden from stating a number).

## Database layer (Agent 6)

- `predmeti.case_dna`, `kanban_faza`, `oblast` — read/written by dozens of call sites, **zero migration
  provenance** (added directly to live Supabase outside the tracked migration system — same disease
  `migrations/105` already fixed once for `predmet_dokumenti`). Disaster-recovery/fresh-environment risk.
- `predmeti.oblast_prava` — read by 6 AI-context features (CIO, Case Intelligence, Decision Replay,
  Precedents Radar, Court Portal heuristics), **never written anywhere on `predmeti`** — silently always
  empty.
- `predictor_analize`, `commander_analize`, `hearing_briefovi` — written on every AI call (6+ call sites),
  never read back by anything — wasted spend + false "history is tracked" signal.
- `predmet_health_log.rizik_label` — written daily, excluded from the one read query that exists.

## Net summary

- **4 concept categories are genuinely well-consolidated** (case risk formula, missing evidence/gaps,
  contradiction severity, priority vocabulary structure).
- **8 concept categories have 2+ independent, unreconciled sources**, 3 of which are confirmed
  simultaneously live on the same case-detail screen.
- **1 root cause (`predmeti.rizik` + the risk-snapshot cache) was independently found by 5 of 7 teams** —
  the highest-confidence, highest-priority fix in this mission.
- **3 AI-boundary gaps** where GPT output reaches a near-canonical field without validation.
- **4 database-layer integrity issues**, one of which (missing migration provenance) is a proven-pattern
  disaster-recovery risk, already fixed once for a sibling table earlier the same day.
