# DECISION_DEPENDENCY_GRAPH.md — Operation Single Brain, Team 2

Every edge below is cited to an exact file:line, independently re-verified — not taken from
`docs/onetruth/INTELLIGENCE_SURFACE_MAP.md` or `docs/architecture/VINDEX_LEGAL_INTELLIGENCE_MODEL.md`
(both used only as a starting checklist).

## The deterministic backbone (confirmed: a strict DAG, zero cycles)

```
predmet_dokazi / predmet_dokumenti / rocista          (raw tables, leaf inputs)
  → risk_engine.py::calculate_procesni_rizik            services/risk_engine.py:21
  → risk_engine.py::identify_case_problems               services/risk_engine.py:177
  → case_evolution.py::_compute_target_actions
      → case_actions table (SOLE writer)                 services/case_evolution.py:820-914
  → case_readiness.py::compute_case_readiness             shared/case_readiness.py:73
      [also reads gap_engine.py::collect_case_gaps, itself reading Genome as a sibling leaf]
  → build_case_context()["readiness"]                      shared/case_context.py:413,519-522
  → _CAP_BY_READINESS clamp on a GPT success-%             court_predictor.py:350 /
                                                            digital_twin.py:333 / hearing_cc.py:427
  → frontend panel render                                  static/vindex.js
```

**7 hops** — one deeper than either prior mission doc's own worked example, because `case_actions`
(written by `case_evolution.py`, itself a consumer of `risk_engine.py`) is a genuine intermediate node
between raw risk data and `case_readiness.py`, not a pass-through. Confirmed independently across four
parallel research passes with no disagreement on the backbone's shape.

**Cycle check**: `case_actions` was specifically checked for any read-back into `risk_engine.py`'s or
`case_readiness.py`'s own inputs — none found. `case_readiness.py` imports only `attention_priority.py`,
which imports nothing project-internal. GPT modules (Court Predictor, Digital Twin, Hearing CC) are
confirmed leaf consumers writing only to insert-only, never-read-back tables (`predictor_analize`,
`hearing_briefovi`) — no feedback path closes anywhere. The `predmeti.rizik` manual column is a **display-
precedence inversion** (a frontend `||` fallback choosing the wrong source), not a cycle: the live engine
never reads it back.

## Risk Level — full graph

- **Computes**: `services/risk_engine.py::calculate_procesni_rizik` — pure function, 11 confirmed call
  sites (`shared/case_context.py:407`, `routers/ccc.py:144`, `routers/dashboard.py:386`,
  `routers/matter_intel.py:79`, `routers/zadaci.py:633`, `services/case_evolution.py:576,690`,
  `services/case_pipeline.py:577,640`, `api.py:3488,5312`).
- **Displays**: Cockpit badge (canonical, correct) at `static/vindex.js:10377`; Status panel
  (`pred-s-rizik`, `:11903-11907`) where the manual `predmeti.rizik` column wins by JS `||` precedence;
  `routers/dashboard.py::command_center` (the app's actual home-tab endpoint) still reads the **stale**
  `[Rizik]` cache — confirmed live and unfixed, distinct from the sibling `/api/predmeti/dashboard` endpoint
  Operation One Truth already fixed; `GET /api/portfolio`, same stale pattern, confirmed dead/orphaned.
- **Uses (multi-hop)**: `identify_case_problems` → `gap_engine.py::gaps_from_case_problems` →
  `collect_case_gaps()` → `case_readiness.py::compute_case_readiness` → the 3 AI success-probability caps →
  frontend. Separately, `case_evolution.py` re-invokes the same two risk functions to build `case_actions`
  rows — a second legitimate branch off the same root, not a duplicate formula.
- **Changes**: (1) `predmeti.rizik` — manually PATCHed, whitelisted at `api.py:3651`, no recompute trigger.
  (2) `predmet_istorija` `"[Rizik] {date}"` — **two independent writers** (`api.py:5426-5459`,
  `services/case_pipeline.py:535-598`), neither aware of the other. (3) `predmet_health_log.rizik_label` —
  written daily, confirmed never read.
- **What depends on it**: Gaps → Readiness → the 3 AI probability caps → `case_actions` → Priority/Next
  Action → Case Commander ranking, CIO's CRITICAL_GAP/BLOCKED portfolio count.

## Case Readiness — two independent, live, unreconciled systems

**2A — Canonical**: `shared/case_readiness.py::compute_case_readiness` — deterministic 5-state enum,
first-match-wins, zero GPT calls, zero DB I/O. Never its own widget (zero matches for
`readiness_status`/`CRITICAL_GAP` in `static/vindex.js`) — reaches the lawyer only as an invisible cap on
other GPT numbers, or narrated in Case Commander text (which has zero frontend entry point).

Readiness-cap consumers, verified hop-by-hop: `court_predictor.py::prediktuj_ishod` (`:337-356`),
`digital_twin.py::kreiraj_simulaciju`/`sta_ako_analiza` (`:202,331-343,427-435` — own copy of the cap dict),
`hearing_cc.py` (`:126,409-431` — own copy, plus an *additional* unconditional clamp its siblings lack),
`case_commander.py` (ranks/narrates, doesn't cap a number), `cio.py` (counts CRITICAL_GAP/BLOCKED cases).
`court_predictor.py::argument_reputation` is confirmed **NOT** capped by readiness — only range-clamped.

**Confirmed structural duplication**: `_CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}` is a literal
dict copy-pasted 3 times (court_predictor.py, digital_twin.py, hearing_cc.py) instead of imported once —
currently in sync only by discipline, a latent desync risk.

**2B — Non-canonical duplicate**: `services/case_pipeline.py::calculate_case_ready_score` — independent
0-100 weighted checklist, genuinely never calls `case_readiness.py` or `case_actions`. Rendered live at
**two** sites (`static/vindex.js:10543`, `:11954`) confirming genuine simultaneous co-render with the
readiness-capped AI panels on the same screen.

**2C — Dead**: `routers/matter_intel.py::preflight_check`/`get_uncertainty_dashboard` — both confirmed zero
frontend callers.

## Success Probability

| Source | Readiness-capped? | Range-clamped? |
|---|---|---|
| `court_predictor.py::prediktuj_ishod` | Yes | Implicit via cap |
| `court_predictor.py::argument_reputation` | **No** | Yes (added same-day) |
| `digital_twin.py` (×2 endpoints) | Yes | Implicit via cap |
| `hearing_cc.py::hearing_score` | Yes | Yes, separately |
| `copilot.py::_handle_analiza_predmeta` | N/A — direct alias of Genome, not GPT-computed | — |

Notable rendering gap: Court Predictor's own capped `procenat_min`/`procenat_max` are **never actually
rendered** in the single-module UI flow (only free-text narrative is shown) — a computed-and-capped number
that structurally never reaches the lawyer through that path. A *different* percentage from a separate "AI
Sudija" module only renders through the combined "Kompletna Analiza" orchestrator view.

## Confidence, Priority, Gaps, Contradiction Severity, Obligations, Evidence, Strategy

See `docs/singlebrain/TRUTH_REGISTRY.md` for the full per-category breakdown; summarized graph relationships:

- **Gaps**: `gap_engine.py::collect_case_gaps` aggregates exactly 3 sources with a `hipoteza` flag
  distinguishing deterministic from GPT-advisory. `routers/copilot.py` calls only 2 of the 3 sub-functions
  directly (a legitimate partial slice, not a re-derivation) — missing the deterministic
  `identify_case_problems`-derived findings Case Commander's full aggregation includes.
- **Priority**: `shared/attention_priority.py` is a real, working 5-6-vocabulary consolidation.
  `routers/copilot.py::_handle_predlozi` is a confirmed-live bypass (§ own vocabulary, own render site).
- **Next Action**: `case_actions` has exactly one writer, independently re-confirmed by exhaustive grep —
  `services/case_evolution.py::_consequence_refresh_case_actions`. Migration 099's own comment ("no other
  module may write directly to this table") holds true today, verified not assumed.
- **Contradiction Severity**: clean — `case_dna.kontradikcije[].tezina`, identity-tracked, Case Commander's
  cross-case detection explicitly self-tagged `"gpt_advisory"`, not a silent duplicate.
- **Obligations**: the `rocista`/`predmet_hronologija` split is confirmed architecturally intentional.
- **Evidence Strength**: clean base value; `evidence.py::_snaga_iz_lokacije` is a per-claim scorer whose
  output feeds `risk_engine.py`'s canonical formula as an input (see `TRUTH_REGISTRY.md` §5).
- **Strategy** (`routers/strategija.py`): 9 GPT modules confirmed structurally outside `build_case_context()`
  (no `predmet_id` on any request model, by the module's own comment). Every response carries a
  `_advisory_provenance()` disclosure object — confirmed, by direct grep of `static/vindex.js`, **never
  rendered anywhere**. Computed and shipped in every API response, cannot reach the lawyer's screen.

## Duplicate-computation red flags handed to elimination work

1. Case Readiness — 2 live sources, co-rendered
2. Risk display precedence — manual column beats live engine on the same page
3. Risk cache freshness split — one dashboard endpoint fixed, a sibling (Command Center) still stale, a
   third (Portfolio) stale-and-dead
4. Success Probability — 4 independent GPT sites, only 1 of 5 surfaces deduplicated
5. Portfolio Case-Strength Aggregation — 2 independently-coded averages, different inclusion filters
6. Confidence — 15 distinct mechanisms, no shared scale, 1 live near-name-collision
   (`confidence_calibrator.py` dead vs. `confidence_auditor.py` live)
7. Priority/Next-Action — Copilot's `_handle_predlozi` bypass
8. `_CAP_BY_READINESS` triplication
9. `[Rizik]` cache tag — two independent writers
