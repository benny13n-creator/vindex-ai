# CROSS_MODULE_CONSISTENCY_REPORT.md — Operation Single Brain, Teams 5 & 6

## Ground truth confirmed

`services/risk_engine.py::calculate_procesni_rizik` is genuinely canonical and deterministic. It is called
live and directly by `api.py`'s `/api/predmeti/dashboard`, `routers/ccc.py`, `routers/matter_intel.py`,
`routers/zadaci.py`, `services/case_pipeline.py`, `services/case_evolution.py`, and propagated via
`shared/case_context.py::build_case_context()` into case_commander, case_intelligence, cio,
court_predictor, digital_twin, hearing_cc, and morning_briefing. `case_actions` has exactly one writer,
event-driven off 4 registered trigger events — eventual consistency by design, not compute-on-read.

## Surface × concept matrix

| Surface | Concept shown | Source | Freshness |
|---|---|---|---|
| Workspace | action priority | `case_actions.prioritet`, live read | Live read of event-driven table |
| Dashboard — `api.py /api/predmeti/dashboard` | `rizik_nivo`, `po_prioritetu` | `calculate_procesni_rizik` live + `case_actions` live | **Live** (fixed by Operation One Truth) |
| Dashboard — `routers/dashboard.py /api/dashboard/command-center` (**the app's actual home tab**) | `predmeti_visok_rizik`, `pad_procene` | `predmet_istorija` `"[Rizik]"` cache, written at most once/day | **Stale, up to ≥24h — CONFIRMED STILL LIVE, unfixed** |
| `routers/dashboard.py /api/predmeti/{id}/health` | health score | canonical risk_engine (fixed) | Live, but dead — no frontend caller |
| Case Commander | risk/readiness | `build_case_context()` only | Live, but dead — zero frontend entry point |
| Court Predictor `/analiza` | win-probability % | GPT JSON + live readiness cap | Hybrid |
| Court Predictor `/confidence-check` | confidence | deterministic score/9 | Deterministic |
| Digital Twin | scenario probability | GPT JSON + same readiness cap | Hybrid |
| Health Index | "Portfolio Rizik" component | `predmeti.rizik_nivo` — **column not selected, doesn't exist** | **Permanently broken, always max score** |
| Health Index | "Snaga predmeta" component | cached Genome | Cached, separate pipeline from risk_engine |
| CIO | `kriticnih_rizika` count | canonical `readiness.status` per case | Live |
| CIO | `najveci_rizik.kriticnost` headline pick | GPT free choice, range-clamped + capped-if-READY | **Unreconciled against canonical ranking** |
| Copilot `ANALIZA_PREDMETA` | `sledeci_korak` | `case_actions`/`top_open_action` | Live |
| Copilot `ANALIZA_PREDMETA` | `verovatnoca_uspeha` | `genome.snaga_predmeta_procent` | Cached Genome |
| Copilot `PREDLOZI` | `predlozi[].prioritet` | own ad hoc engine, bypasses `case_actions`/`attention_priority` | Live query, wrong source |
| Morning Briefing | "danas zahteva pažnju" | `build_case_context`+`top_open_action`, well-consolidated | Live, but **email-only, no in-app UI caller** |
| Case Intelligence `POST /briefing` | `sledeci_korak`, `kljucni_rizici` | canonical | Live |
| Case Intelligence `GET /briefing/poslednji` | same fields | frozen `decision_log` snapshot | Cached, **no staleness indicator** |
| Case DNA/Genome | strength/kriticnost | `genome_validator.py::compute_snaga_score` | Cached until next event-driven refresh |
| Notifications | alert priority | **two live, independent generators** | Self-acknowledged unresolved overlap in code |
| PDF export | — | fetches fresh at export time, embeds no risk/priority/health field | N/A |

## Confirmed cross-module inconsistencies, ranked by how likely a lawyer hits them in one day

1. **Command Center home tab shows a risk badge up to a day (or more) stale, while every other live
   surface is current.** This is the endpoint actually wired to the app's home tab. Scenario: a hearing
   gets scheduled inside the critical window at 2pm — Workspace, Cockpit, `/api/predmeti/dashboard`, CCC,
   and Matter Intel all instantly show "Visok"/critical; the home-tab Command Center keeps its morning's
   "no risk" badge and omits the case from `predmeti_visok_rizik` until tomorrow's pipeline run.
2. **Copilot answers "what should I do?" two different ways in the same conversation.** `PREDLOZI` and
   `ANALIZA_PREDMETA` are two unrelated next-action engines in the same router.
3. **Genome/Copilot "case strength" vs. live risk-engine "case strength."** Same jaka/srednja/slaba
   vocabulary, two independent pipelines with different freshness — marking one piece of evidence "jaka"
   updates live surfaces instantly but leaves Genome/Copilot/Health Index's cached number unchanged until a
   full Genome re-extraction.
4. **Health Index's "Portfolio Rizik" component is permanently dead** — always scores maximum ("no risk")
   no matter how many cases are actually flagged critical right now, independently confirmed by 3 of the
   10 teams this mission.
5. **CIO's headline "biggest risk" case is an unreconciled GPT pick** — never checked against which case is
   actually CRITICAL_GAP in `case_actions`/Workspace.
6. **Two live, independently-vocabularied notification generators** — the code's own comment documents this
   as unresolved, self-acknowledged overlap, not a hypothetical.
7. **Structural risk, not yet a caught steady-state failure**: every `case_actions` consumer is only as
   fresh as the last qualifying event dispatch, while `api.py`'s dashboard/CCC/matter_intel/zadaci compute
   `calculate_procesni_rizik` truly live per request — a genuine eventual-consistency seam.
8. **`GET /briefing/poslednji`** serves a frozen snapshot with no staleness marker, silently disagreeing
   with a same-moment live Workspace/Dashboard view.

**Explicitly flagged as dead/unreachable** (not counted as "consistent" just because nobody sees them): Case
Commander, `GET /api/predmeti/{id}/health`, Morning Briefing's in-app surface (email-only), PDF export
(uninformative, not contradictory — carries no comparable field).

## Team 6 — API Consistency: execution-tested endpoint pairs (not just code-read)

Method: built a fake Supabase client that honors `.select(cols)` column projection and `.is_()` filtering
(the repo's existing `MagicMock`-chain test fixtures don't, and the bug lives exactly in which columns each
router selects). 4 endpoint functions tested against identical mocked case data.

| Pair | Result | Root cause |
|---|---|---|
| `routers/ccc.py::get_ccc` vs `routers/matter_intel.py::get_matter_intel` | **DISAGREE** — health_score 70 vs 55 | `matter_intel.py` selects `predmet_dokumenti` WITHOUT `tip_dokaza`; `calculate_procesni_rizik`'s missing-evidence detection always reports **all** expected document types missing regardless of what's actually uploaded |
| `api.py::predmet_workspace` (Cockpit) vs `matter_intel.py` | **"AGREE"** — both "srednji" | **Agreement is coincidental**: Cockpit has the identical missing-`tip_dokaza` bug — it literally told a lawyer "Nedostaje relevantni ugovor u spisu" even though the contract WAS uploaded |
| `shared/case_context.py::build_case_context` vs `ccc.py` | AGREE — genuinely correct | Both correctly select `tip_dokaza` |
| `build_case_context` vs `matter_intel.py` | **DISAGREE** — same root cause, inherited transitively | — |

**Second, independent root cause, isolated in a controlled scenario**: `ccc.py`'s `predmet_dokazi` query has
**no** `deleted_at` filter (unlike `matter_intel.py`/`api.py`/`case_context.py`, which all correctly exclude
soft-deleted evidence). In one test run, this bug and the `tip_dokaza` bug happened to cancel out to an
apparently-matching `health_score` — a more dangerous failure mode than an outright mismatch, since it hides
two real, unrelated defects behind consistent-looking output. `nedostajuci_dokazi` diverged completely in
the same run even though `health_score` didn't, so the inconsistency IS visible on that field.

**Verdict**: 2 of 4 tested endpoint pairs disagreed via actual execution against identical data, both traced
to one confirmed root cause (missing `tip_dokaza` in the `predmet_dokumenti` column selection at 2 call
sites: `matter_intel.py` and `api.py::predmet_workspace`/Cockpit itself). A second, independent root cause
(`ccc.py`'s missing `deleted_at` filter) was separately confirmed.
