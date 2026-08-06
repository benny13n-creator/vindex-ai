# GPT Module Census — Program Tau, Master Sprint 006, Phase 1

Fresh, from-source census of every GPT-calling module in the repo. Does NOT reuse `TAU-012`'s own prior
"16+ files" estimate, or any prior sprint's `GPT_CONTEXT_MAP.md`, without re-verifying against current
source. Performed by 2 parallel forensic forks (alphabetical split, files starting A-M / N-Z), cross-checked
by a direct repo-wide grep for `build_case_context` from the main thread.

## Correction to this program's own immediately-prior claim

`docs/tau/TAU_006_HANDOVER.md` (Master Sprint 005) described `case_commander.py` as an already-completed
canonical-context migration ("Sigma 005's Case Commander migration") — the naming template for hearing_cc.py's
own future migration. **This is wrong.** Direct verification (`grep -n "build_case_context" routers/case_commander.py`
→ zero hits) confirms `case_commander.py` still runs its own bespoke `_dohvati_predmet_kontekst` fetcher.

What Sigma Master Sprint 005 actually did was consolidate Case Commander onto **canonical DECISION sources**
(`case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py`) under its own separate GPT Boundary Policy
(`docs/sigma/GPT_BOUNDARY_POLICY.md`) — restricting what GPT may decide vs. must read as pre-computed truth.
This is a real, different axis from what Tau 002 onward has been migrating modules onto: the canonical
**CONTEXT** source, `shared/case_context.py::build_case_context()`. Both are legitimately "canonical," but
for different concerns (decision-authority vs. context-completeness), and conflating them was a genuine
mistake in the prior handover — corrected here, not silently dropped. `case_commander.py` remains a real,
unmigrated Factory candidate.

## Canonical context callers — confirmed by direct repo-wide grep

Exactly 3 production call sites of `shared/case_context.py::build_case_context()` exist anywhere in the repo:

| File | Mode |
|---|---|
| `routers/case_intelligence.py` | Full (documents included) |
| `routers/court_predictor.py` | Full for 2 endpoints, lightweight for 5 (Tau 005) |
| `routers/morning_briefing.py` | Lightweight (`include_documents=False`, portfolio-wide loop) |

## Naming collision, flagged so it isn't mistaken for a 4th caller

`shared/ai_provenance.py::case_context(...)` is an unrelated provenance/audit context manager (sets
`predmet_id`/`operation_name` for audit trail purposes). `copilot.py`, `evidence.py`, `evidence_graph.py` call
this — none of them call `shared/case_context.py::build_case_context()`. Two functions, same short name,
different modules, different purpose. Do not conflate.

## Real bespoke single-case migration candidates (Factory-eligible)

Modules with a genuine per-case, `predmet_id`-driven, multi-table context fetch that duplicates part of
what `build_case_context()` already does — the direct target population for this program's "Canonical
Context Migration Factory":

| Module | Fetch shape | Notes |
|---|---|---|
| `routers/hearing_cc.py::_load_all_context` | 8 tables | **This sprint's Phase 4 pilot.** Richest bespoke duplicate found. |
| `api.py::predmet_workspace` ("Cockpit AI") | 7+ signals + deterministic risk | Not on TAU-012's original list. Richest bespoke builder found in this census besides hearing_cc.py. |
| `routers/case_commander.py::_dohvati_predmet_kontekst` | multi-table | See correction above — genuinely unmigrated, despite the naming confusion in this program's own prior handover. |
| `routers/copilot.py::_handle_analiza_predmeta` | 5 tables | `predmet_id` genuinely used (not a TAU-011 shape) |
| `routers/zadaci.py::ai_analiziraj_predmet` | 7 tables | Comparable scope to hearing_cc.py |
| `api.py::predmet_ai_preporuka` | 4 tables | Not on TAU-012's original list |
| `routers/digital_twin.py::_dohvati_kontekst_predmeta` | 4 tables | Clean candidate |
| `routers/evidence_graph.py::generisi_graf` | 4 tables | Clean candidate |
| `routers/decision_replay.py::_gather_timeline_events` | 7 tables, incl. both `rokovi` AND `rocista` | Independently corroborates `TAU-013`'s rokovi/rocista split finding. Historical-replay purpose differs from `build_case_context()`'s current-state snapshot — may be a legitimately different shape, not a pure swap (see Phase 7). |
| `routers/outcome_intel.py` | bespoke-narrow + portfolio aggregation | Mixed |
| `routers/precedenti.py` | bespoke-narrow + portfolio comparison | Mixed |
| `services/agent_tasks/precedents_radar.py` | Genome-field-only | Narrow |
| `routers/profitabilnost.py` | single-case, billing-focused | Narrow |
| `routers/strategy_simulator.py::_dohvati_predmet` | narrow (naziv/tip/opis/status/stranke) | Narrow |
| `routers/zakon_monitoring.py` | narrow-moderate | Case row + law-impact fetch |
| `routers/zastarelost.py` | narrow, deadlines-focused | `rokovi` table only |
| `routers/case_pipeline.py` | narrow, per-step | By design minimal (fires immediately post-creation) |
| `routers/cross_doc.py::cross_doc_predmet` | narrow, documents-only | Purpose-specific |

**17 real candidates**, at endpoint/module granularity — broadly reconciles with `TAU-012`'s original
file-level "16+" estimate, though the exact count differs because this census works at finer granularity
(e.g. `api.py` contributes 2 separate bespoke endpoints, not counted as a "file" in the original estimate).

## TAU-011-shape findings (predmet_id present but not used for context, or structurally absent)

| Module | Shape |
|---|---|
| `drafting/router.py::generate_draft()` | **No `predmet_id` parameter in the function signature at all** — not just unused, structurally absent. The most extreme instance of this shape found in this program to date. |
| `routers/doc_templates.py::generisi_dokument` | `predmet_id` accepted (Optional) but completely unused in generation — TAU-011 shape in a file not previously examined for it. |
| `routers/drafting.py` | `predmet_id` only used post-generation at the staging/write path; the actual generation prompt's own "context" is RAG-retrieved legal precedent, not the case's real state — same shape pre-migration Court Predictor had. |
| `routers/style_checker.py` | `predmet_id` only filters a history list (`GET /analize`); never feeds the GPT call itself. |
| `services/ambient_analyzer.py::analyze_paragraph` | `predmet_id` param accepted, never referenced again in the function body. |

## Architecturally exempt (not single-case-context candidates)

Producers of canonical truth (migrating them would be circular): `routers/case_dna.py` (Genome — canonical
context *reads from* this), `routers/evidence.py` (evidence classification — same exemption class).

Portfolio-wide / different scope entirely (not single-case by design): `routers/cio.py`, `routers/health_index.py`,
`routers/client_twin.py` (keyed by `klijent_id`, not `predmet_id`), `routers/voice.py` (cross-case hearing lookup).

No case concept applies (pre-case-creation, firm-wide, or genuinely case-independent): `routers/intake.py`,
`shared/intake_classify.py`, `shared/intake_extract.py`, `routers/integracije.py`, `routers/dokument.py`,
`routers/auto_discovery.py`, `routers/batch_ingest.py`, `routers/oblasti.py`, `routers/praksa.py`,
`routers/region.py`, `routers/web3.py`, `web3_compliance.py`, `routers/strategija.py` + root `strategija.py`
(self-documented: no endpoint has a `predmet_id` at all), `routers/copilot.py::_handle_pravno_pitanje`,
`routers/corrections.py`, `routers/status_page.py`, `routers/proof.py`, `services/voice_orchestrator.py`,
`shared/voice_tools.py`, `drafting/playbook.py`.

## Census scale

52 GPT-calling files inventoried across both forks (27 in the A-M half, 25 in the N-Z half), zero overlap
confirmed (one ambiguous alphabetical boundary — `drafting/router.py` vs. root-level `strategija.py`/
`web3_compliance.py` — checked and confirmed not double-counted by either fork). This is a materially finer
sweep than any prior Tau sprint's own module count, since it inventories every GPT call site, not just the
file-level list `TAU-012` originally produced.
