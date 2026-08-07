# ONE_TRUTH_ARCHITECTURE_MAP.md — Operation One Truth, Phase 1

*Pre-migration architecture map. Produced before any Phase 3 code change. Synthesized from 7 independent
forensic teams — see `docs/onetruth/INTELLIGENCE_SURFACE_MAP.md` for the full per-concept breakdown and
`docs/onetruth/AGENT_REPORTS_RAW.md` for complete per-agent evidence.*

## Ownership table

| Informacija | Canonical Owner | Ostali korisnici (duplicate/competing) | Rizik |
|---|---|---|---|
| Case risk level (rizik) | `services/risk_engine.py::calculate_procesni_rizik` | `predmeti.rizik` (manual column, wins in Status panel); `predmet_istorija` `"[Rizik]"` cache (Dashboard/Portfolio, no invalidation trigger); `routers/ccc.py`'s own broken local loop; `routers/matter_intel.py::get_uncertainty_dashboard`'s sibling reimplementation of the same bug | **CRITICAL** — 5-team convergent finding, live on 5+ surfaces, includes a malpractice-adjacent blind spot (Dashboard can show "low risk" for a case a hearing has since made urgent) |
| Case strength (snaga predmeta) | `routers/case_dna.py::_extract_genome` → `case_dna.snaga_predmeta_procent` (backend-recomputed via `genome_validator.py`) | `health_index.py`'s own portfolio average; `cio.py`'s own, separately-coded portfolio average | HIGH — base value is fine, 2 independent aggregations can diverge |
| Success probability (verovatnoća uspeha) | *(no single owner exists today — Genome's `snaga_predmeta_procent` is the closest deterministic anchor)* | Digital Twin (×2), Court Predictor `prediktuj_ishod`, Court Predictor `argument_reputation` (unclamped), Hearing CC — all independent GPT calls; only Copilot's `ANALIZA_PREDMETA` is fixed (aliased to Genome) | HIGH — 4 live independent numbers, Iron Lawyer's UX audit already flagged this at the presentation layer |
| Case readiness (spremnost) | `shared/case_readiness.py::compute_case_readiness` | `services/case_pipeline.py::calculate_case_ready_score` (independent checklist, same UI vocabulary); `matter_intel.py::preflight_check` (GPT-native, confirmed dead/no frontend caller) | MEDIUM-HIGH — 2 live sources render on the same case page |
| Missing evidence / gaps | `shared/gap_engine.py::collect_case_gaps` | None found | LOW — genuinely single source |
| Contradiction severity | `case_dna.kontradikcije[].tezina` via `shared/contradiction_identity.py` | Case Commander's cross-case detection (deliberately different, tagged scope) | LOW — well-scoped |
| Priority / hitnost | `shared/attention_priority.py` (5-source translation layer) | `routers/copilot.py::_handle_predlozi`'s own ad hoc deadline-proximity priority | MEDIUM — 1 live gap, narrow blast radius (one Copilot intent) |
| Next action | `identify_case_problems` + `shared/case_readiness.py::top_open_action` | Same `_handle_predlozi` handler, independent generation | MEDIUM — same narrow blast radius |
| Confidence / pouzdanost | *(no single owner — 7 independently-coded scales)* | court_predictor's 2 internal scales, dead `confidence_calibrator.py`, case_intelligence's briefing formula, judge_profile's odluke-count formula, opponent_intel's GPT-self-declared scale, Genome's `genome_kompletnost`, `genome_validator.py::verify_genome` | MEDIUM — most fragmented category, but none currently co-render on one screen in direct contradiction (unlike risk/readiness/probability) |
| Genome trust/validity | `shared/genome_validator.py::verify_genome()` (correctly DETECTS bad output) | *(no enforcement — advisory only, invisible downstream)* | HIGH — the detector exists and works but nothing acts on it |
| Genome `najslabija_tacka.kriticnost` | *(none — fully GPT-authored)* | Unlike its sibling field `snaga_predmeta_procent`, never clamped or validated | MEDIUM-HIGH — reaches DB, canonical context, and alert-urgency math unchecked |
| Court Predictor judge statistics | *(none — invented)* | `stopa_potvrdjivanja_zalbi` has no backing data source anywhere in the codebase | MEDIUM — presented as measured fact, isn't one |

## Root-cause convergence

The single highest-confidence finding of this mission is **not** a new discovery each team made
independently by accident — it is the *same underlying defect class* (a non-canonical value sitting beside
a canonical one, with no sync/invalidation discipline) manifesting in five different concrete forms, found
by five of seven teams working from completely different angles:

1. Agent 1 (Intelligence Consistency) — mapped the case-detail page co-rendering the live badge and the
   Case Ready Score gauge from two unreconciled sources.
2. Agent 2 (Data Truth) — found `predmeti.rizik` winning over the canonical live value in the frontend's own
   fallback chain, plus the CCC/Matter Intel broken duplicate-computation regression.
3. Agent 4 (UX Trust) — traced the exact 6-months-untouched scenario the mission's own test question asks
   about, confirming the Genome/Cockpit staleness gap and the dashboard-safety-net blind spot.
4. Agent 6 (Database Integrity) — found `predmeti.rizik` feeding two AI prompts (Digital Twin, Hearing CC)
   with stale or hardcoded-default data, bypassing the deterministic engine entirely.
5. Agent 7 (Red Team) — built the single most concrete, most damaging reproduction: the Dashboard's cached
   `"[Rizik]"` snapshot vs. Workspace's live computation, with a full step-by-step scenario proving a
   realistic false-vs-true contradiction reaches the platform's primary triage screen.

**This is Phase 3's first and highest priority.**

## Red Team verdict (full detail: Agent 7's report)

**"Is the one-truth property currently violated in a real, demonstrable way? YES — confirmed, reproduced,
not manufactured.**" The scoring *formula* is genuinely unified (11 call sites checked, no rogue second
implementation of the algorithm itself). The violation is entirely in the **caching/refresh layer**: a
canonical function whose *output* is trusted as current by the Dashboard and Portfolio views without any
invalidation trigger tied to the events that actually change the answer. Blast radius: 3 UI surfaces
(Dashboard, Portfolio, Workspace) can show 3 different pictures of the same case in one session.

## UX Trust verdict (full detail: Agent 4's report)

Direct answer to "if I open this case after 6 months, do I trust the system?": **Partially.** The team has
visibly converged the platform onto one canonical risk *function* and even added a staleness-disclosure
pattern for Genome — but that discipline doesn't reach the two places a lawyer would notice after 6 months
of silence (Genome is event-frozen, Cockpit is always-live, no visible timestamp without an extra click),
and the aggregate safety net (Dashboard/CIO "biggest risk" ranking) is itself dependent on the neglected
case being reopened to refresh — the exact case most likely to have quietly gotten worse is the least likely
to be flagged.

## What does NOT need fixing (verified good, not just claimed good)

- `services/risk_engine.py`'s scoring formula itself — single implementation, reused correctly everywhere
  except the caching/manual-override layer around it.
- `shared/gap_engine.py::collect_case_gaps` — correctly-built aggregator.
- `shared/attention_priority.py` — correctly-built translation layer (1 narrow gap in Copilot only).
- `shared/case_context.py::build_case_context()` — genuinely computes nothing new, provenance-tagged.
- `routers/case_commander.py`'s 2026-08-06 rewrite — a real, working precedent for the "view, not owner"
  pattern (`shared/commander_schema.py`'s `{value, source, evidence, confidence, generated_by, timestamp}`
  shape).
- The Obligations split (`rocista` + `predmet_hronologija`) — intentionally two tables for two genuinely
  different extraction paths, not accidental duplication.
- Copilot's `ANALIZA_PREDMETA` `verovatnoca_uspeha` — already fixed to alias Genome directly, the model to
  replicate for the other 4 probability generators.

## Phase 2 reference

See `docs/architecture/VINDEX_LEGAL_INTELLIGENCE_MODEL.md` (Agent 5's deliverable) for the full canonical
mental model — 7 core entities (Facts, Evidence, Risks, Gaps, Obligations, Actions, Strategy), each with a
named owner, a governing "everything else is a view" principle, and a decision rule for future features.
