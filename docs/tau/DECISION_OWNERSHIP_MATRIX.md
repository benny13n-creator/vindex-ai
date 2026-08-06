# Decision Ownership Matrix — Program Tau, Master Sprint 003, Phase 2

Every GPT-decided field found in `AI_DECISION_SURFACE_MAP.md`, classified into exactly one of the 8
permitted owners: **Case Actions, Case Readiness, Gap Engine, Risk Engine, Genome, Evidence, Human, GPT
Advisory**. `GPT` alone, without one of these 8, is never an accepted answer — every row below either names
one or is listed in the "still GPT (unowned)" table as a named Phase 3 migration target.

## Correctly owned already (no Phase 3 action needed)

| Field | File | Owner |
|---|---|---|
| `nedostaje`/`nedostaju` (both copilot handlers) | `copilot.py` | Gap Engine (conditional on non-empty; documented gap below) |
| `sistemsko_upozorenje` | `strategija.py::orkestrator_kompletna_analiza_sync` | Human-authored deterministic code (this function itself) |
| `detektovani_konflikti` (categorical half) | `strategija.py::orkestrator_kompletna_analiza_sync` | Human-authored deterministic code (2 hardcoded rules) |
| `_ai_prioritizacija_alertova`'s `ai_tekst` | `morning_briefing.py` | GPT Advisory over Risk-Engine-adjacent deterministic input (rephrasing only, proven by fallback identity) |

## Migrated this sprint (Phase 3 — see `AI_ENTRY_POINT_MIGRATION_REPORT.md`-equivalent section of `SPRINT_003_REPORT.md`)

| Field | File | Old owner | New owner |
|---|---|---|---|
| `sledeci_korak`/`razlog`/`hitnost` | `case_intelligence.py` | Case Actions (conditional) / GPT fallback | **Case Actions** (unconditional — honest "no open action" state replaces the GPT fallback) |
| `sledeci_korak` | `copilot.py::_handle_analiza_predmeta` | Case Actions (conditional) / GPT fallback | **Case Actions** (unconditional) |
| `kljucni_rizici` | `case_intelligence.py` | GPT (unowned) | **Risk Engine / Gap Engine** (derived from `case_context`'s `missing_evidence`+`contradictions`) |
| `napomena` | `case_intelligence.py` | GPT (unowned) | **Genome / Gap Engine** (deterministic completeness statement) |
| `pouzdanost_briefinga` | `case_intelligence.py` | GPT self-report (unowned) | **Human-authored deterministic heuristic** (data-completeness based, not self-reported) |
| `slabosti` | `copilot.py::_handle_analiza_predmeta` | GPT (unowned) | **Genome** (derived from `case_dna.kontradikcije`+`nedostaje` via `shared/gap_engine.py`) |
| `verovatnoca_uspeha` | `copilot.py::_handle_analiza_predmeta` | GPT (unowned, duplicate) | **Genome** (`snaga_predmeta_procent`, when computed) |
| `kriticni_rokovi` | `copilot.py::_handle_plan_predmeta` | GPT (unowned) | **Evidence/Deadlines** (`predmet_hronologija` rows already fetched, now returned directly) |
| `upozorenja` | `copilot.py::_handle_plan_predmeta` | GPT (unowned) | **Genome** (same derivation as `slabosti`) |
| "Danas zahteva pažnju" | `morning_briefing.py::_generiši_briefing` | GPT (unowned) | **Case Actions/Case Readiness** (pre-computed canonical priority list, GPT told to phrase not decide) |

## Legitimately GPT Advisory (no canonical owner exists or is appropriate — labeled, not removed)

| Field(s) | File | Why no canonical owner |
|---|---|---|
| `procena`, `prednosti`, `relevantne_lekcije`, `komunikacioni_savet`, `potvrdjeni_obrasci` | `case_intelligence.py`/`copilot.py` | Genuine narrative synthesis over real fetched data, no competing canonical decision |
| `cilj`, `faze[].koraci` (plan structure itself) | `copilot.py::_handle_plan_predmeta` | Generative planning narrative — legitimate "drafting assistance" per `LEGAL_AI_BOUNDARY_POLICY.md`'s own MAY column |
| Every field in `strategija.py`'s 6 single-module endpoints + `sudija-v2` + most of `v2/analiza`/`kompletna-analiza`'s synthesis | `strategija.py` | No `predmet_id` exists anywhere — no case record to own these facts against. Correct classification, not a defect. |
| `multi_agent.py`'s chat persona responses | `multi_agent.py` | Free text in an open chat, no fixed JSON key competing with a canonical UI slot |

## Still `GPT (unowned)` after this sprint — named, not fixed (see `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`)

| Field | File | Why not fixed this sprint |
|---|---|---|
| `faze[].koraci[].prioritet` | `copilot.py::_handle_plan_predmeta` | Per-step priority inside a GPT-synthesized multi-phase plan has no case_actions equivalent (case_actions is a flat list, not a phased plan) — genuinely no canonical structure to redirect to without a new planning engine (out of scope, would be over-engineering) |
| `procenat_min`/`procenat_max` | `court_predictor.py` | Pre-existing, already-tracked 5-way fragmentation (Program Beta, `PROGBETA-001`) — a separate, larger consolidation project, not this sprint's to re-litigate |
| `OSPORAVA` contradiction edges | `evidence_graph.py` | Pre-existing, already-tracked 4-way fragmentation — same reasoning |
| `nedostaju_elementi` | `drafting.py::_pozovi_kriticara` | Possible overlap with `quality_gate.py` (`DC-008`) not yet confirmed — needs a dedicated read before any fix, not assumed |
