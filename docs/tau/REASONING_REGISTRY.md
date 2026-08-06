# Reasoning Registry — Program Tau, Master Sprint 007, Phase 1

Complete map of every place the platform assesses risk, determines priority, assesses case readiness,
determines the next step, identifies missing evidence, assesses contradictions, determines case status, or
generates recommendations. Built by 2 parallel forensic forks (split by reasoning concern, not by file), no
assumptions — everything below is verified from source.

## The canonical mechanisms (ground truth, not re-litigated this sprint)

| Concern | Canonical mechanism |
|---|---|
| Risk / case problems | `services/risk_engine.py::calculate_procesni_rizik` + `identify_case_problems` |
| Missing evidence / contradictions (aggregated) | `shared/gap_engine.py::collect_case_gaps` (normalizes `identify_case_problems` + Genome's own `nedostaje[]`/`kontradikcije[]` — computes nothing new itself) |
| Case readiness | `shared/case_readiness.py::compute_case_readiness` |
| Next action / priority | `case_actions` table (written by `services/case_evolution.py`) + `shared/case_readiness.py::top_open_action` |
| Priority vocabulary translation | `shared/attention_priority.py` (a pure lookup/translation layer over `case_actions.prioritet` — computes nothing new, confirmed clean) |
| Single-case context aggregation | `shared/case_context.py::build_case_context()` (calls ALL of the above internally, exposes their output as `readiness`/`missing_evidence`/`contradictions`/`active_actions`) |

## Risk / Readiness / Gaps / Contradictions — census (Fork 1)

| Module | Function(s) called | Classification |
|---|---|---|
| `routers/case_commander.py` | `calculate_procesni_rizik`, `identify_case_problems`, `collect_case_gaps`, `compute_case_readiness`, `top_open_action` | **recompute/duplicate** — 2 independent call sites in the same file (`_kanonski_nalazi` for single-case endpoints, `_kanonski_prioritet_i_rizici` for the portfolio-wide digest) |
| `routers/zadaci.py::ai_analiziraj_predmet` | `calculate_procesni_rizik`, `identify_case_problems` | **recompute/duplicate** (known from Tau 006) |
| `api.py::predmet_workspace` ("Cockpit AI") | `calculate_procesni_rizik`, `identify_case_problems` | **recompute/duplicate** — Tau 006 flagged this as bespoke-context; now confirmed it also duplicates computation, not just the fetch |
| `routers/matter_intel.py` | `calculate_procesni_rizik`, `identify_case_problems` | **recompute/duplicate** — the file's own docstring frames itself as the "reference" endpoint for this computation, but still bypasses `build_case_context()` |
| `routers/ccc.py` | `calculate_procesni_rizik` | **recompute/duplicate** — already delegates to the canonical FUNCTION (fixed 2026-08-03, Project Nexus, stopped reimplementing its own formula) but still runs its own independent fetch |
| `routers/dashboard.py` | `calculate_procesni_rizik`, `identify_case_problems` | **recompute/duplicate** — same "canonical function, own fetch" shape as `ccc.py` |
| `routers/copilot.py::_handle_analiza_predmeta` | `top_open_action` | **milder finding** — calls the correct canonical function, but on its own freshly-fetched `case_actions` rows rather than `build_case_context()`'s own `active_actions` field; logic isn't duplicated, only the fetch |
| `routers/court_predictor.py`, `routers/case_intelligence.py`, `routers/morning_briefing.py` | — | **canonical** — confirmed reading `build_case_context()`'s own output directly (Tau 005/002) |

**No GPT-decided risk/readiness/contradiction/priority found anywhere in this scope** — Tau 003/005's own
boundary work holds for this reasoning class.

## Priority / Next-step / Status / Recommendation — census (Fork 2)

| Module | Description | Classification |
|---|---|---|
| `shared/attention_priority.py` | Canonical priority translation layer; `zadaci.py`/`notifications.py`/`inbox.py`/`predmet_hronologija.vaznost` all translate INTO it, not recompute | **canonical**, confirmed clean |
| `routers/cio.py` | GPT independently invents `kriticnost` (0-100), `najveci_rizik`, `kriticni_rok`, `neprimecena_kontradikcija.tezina`, `cio_preporuka` from raw portfolio signals — not from `case_actions`/`identify_case_problems`/`compute_case_readiness` | **GPT-decided** — but ALREADY self-documented (the file's own header) as a known, deliberate gap from Program Omega Sprint 004: "the canonical answer is `GET /api/workspace`; this module remains a supplementary strategic perspective... out of safe scope [previously]." A live, billed module — not touched this sprint, see Phase 5. |
| `routers/strategija.py` | GPT invents `sledeci_koraci[].prioritet` in an on-demand strategy simulation | **GPT-decided but not case-linked** — no `predmet_id` on any endpoint in this file (self-documented, pre-existing), so there is no canonical per-case state to duplicate against |
| `routers/case_dna.py` (Genome) | `nedostaje[].hitnost` is GPT-advisory | **GPT-decided**, but documented advisory-only, not consumed downstream as an autonomous decision |
| `routers/multi_agent.py`, `routers/drafting.py`, `routers/decision_replay.py`, `routers/strategy_simulator.py` | No priority/readiness/status/next-step vocabulary found | not applicable |

## Verdict

The 6-module risk/gap/readiness duplicate-computation family (fork 1) is this sprint's own primary target
class — `case_commander.py` is Phase 3's named migration target; the other 5 are named in
`docs/tau/TAU_008_HANDOVER.md` as the next rollout queue, not migrated this sprint. `cio.py`'s own
GPT-decided priority is the one real, still-open GPT-boundary finding — addressed explicitly in Phase 5
(`docs/tau/CANONICAL_REASONING_CERTIFICATION.md`), not silently fixed mid-sprint given its own live-billed,
previously-deliberately-deferred status.
