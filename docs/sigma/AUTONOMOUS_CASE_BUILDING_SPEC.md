# Autonomous Case Building Spec — Program Sigma, Master Sprint 001 (2026-08-06)

Phase 4 (Autonomous Enrichment) and Phase 7 (Operational Readiness) deliverable.

## Phase 4 — Autonomous Enrichment

Requirement: every new document must automatically refresh Genome, Strategy, Timeline, Worklist, Dashboard,
Alerts, Notifications — without duplication, without a race condition, without a second algorithm.

This is the domain Program Omega's own Sprints 002-007 (this same engagement) already built and
certified — re-verified current, not re-built, this sprint:

| Target | Auto-refreshed by | Mechanism | Duplication guard |
|---|---|---|---|
| Genome | `_consequence_genome_refresh` | `DOCUMENT_ACCEPTED`/`DOCUMENT_BATCH_COMPLETED` → `handle_case_changed` | One recompute per batch (Sprint 002's own `OMEGA-001` fix), not per document |
| Timeline | `_consequence_timeline_entry` | Same events | Per-`(event_id, consequence_name)` idempotency ledger (`case_evolution_consequences`) |
| Worklist / Tasks (`case_actions`) | `_consequence_refresh_case_actions` | Same events | `dedupe_key` + partial UNIQUE index (migration 099) |
| Notifications | `_consequence_project_case_actions_to_notifications` (Program Omega, Final Sprint 007) | Same events, trailing consequence | `dedupe_key` reused from `case_actions` + partial UNIQUE index (migration 101) |
| Dashboard | Read-only projection over `predmet_hronologija`/`case_actions` | N/A — no independent write | N/A, nothing to duplicate |
| Alerts (`proactive_alerts`) | `on_rok_kritican`/`on_health_score_promenjen` | Separate Event Bus handlers, application-level check-before-emit | **Known gap, not DB-enforced** — `OMEGA-023` (Sprint 007), unchanged this sprint |
| Strategy | **Two independent triggers** — see below | — | — |

**Strategy is the one target with 2 legitimately different trigger paths, not a duplication**:
`routers/strategija.py` (on-demand, full multi-agent simulation, a lawyer explicitly requests it) and
`case_pipeline.py::_step_strategija` (automatic, lite, one-shot initial assessment, fired once when a case
is created — now including Smart-Intake-created cases, this sprint's own fix). These write to the SAME
`predmet_istorija` table but under different markers (`[Strategija Pipeline]` vs. whatever the on-demand
endpoint uses) and serve different purposes (initial orientation vs. deep on-demand analysis) — not the
"second algorithm for the same decision" the mission's own Phase 4 forbids, since they're not both trying
to be the SAME thing (one is a always-fresh-computed on-demand deep dive, the other a one-time initial
placeholder that never re-runs once written).

All 5 of the Case Evolution-owned consequences run through the SAME sequential per-event dispatcher
(`handle_case_changed`), proven crash/retry/replay-safe by this whole engagement's own prior test suites
(re-run clean this sprint, see `SYSTEM_GAP_REPORT.md`) — no new orchestrator was introduced by this
sprint's own fix; the new `PREDMET_KREIRAN` wiring reuses the SAME durable-outbox/Event-Bus pattern already
proven for `DOCUMENT_ACCEPTED`.

## Phase 7 — Operational Readiness

Requirement: on opening a case, a lawyer must immediately see what arrived, what's missing, what's
contradictory, what deadlines exist, what risks exist, what to do first, what can wait, what document/
evidence is missing — verifiable facts only, no GPT marketing text.

**`GET /api/matter-intel/{predmet_id}`** (`routers/matter_intel.py:45-`) is this payload, already built and
live, re-verified this sprint:

| Requirement | Field | Source | Deterministic? |
|---|---|---|---|
| Šta je stiglo | `predmet_dokumenti` count (implicit in Genome/Case Ready Score) | Direct query | Yes |
| Šta nedostaje | `nedostajuci_dokazi` | `services/risk_engine.py::calculate_procesni_rizik` | Yes — deterministic (Core Consolidation Sec 1.1, 2026-07-22) |
| Šta je kontradiktorno | Genome's own `kontradikcije` | `case_dna` | GPT-extracted, grounded with document/page citations — see `LEGAL_KNOWLEDGE_FLOW.md`'s own precision caveat |
| Koji rokovi postoje | `predstojeći_rokovi`, `kriticni_rokovi` | Same endpoint | Yes |
| Koji rizici postoje | `procesni_rizik` | `calculate_procesni_rizik` | Yes — the ONE deterministic risk algorithm platform-wide (Core Consolidation) |
| Šta prvo treba uraditi | `otkriveni_problemi` | `identify_case_problems(rizik, tip)` | **Yes — deterministic, NOT a GPT sentence.** `services/case_pipeline.py::_step_copilot_preporuka`'s own docstring documents this was explicitly changed FROM a 3rd independent GPT "next action" generator TO this same deterministic function, closing a real duplicate-algorithm finding from an earlier sprint's own forensic audit (2026-07-22) |
| Šta može da čeka | Implicit — `otkriveni_problemi` is priority-ordered via `shared/attention_priority.py`'s own canonical model | Same | Yes |

**"Bez GPT marketing teksta. Isključivo proverljive informacije" is already satisfied for the load-bearing
fields** — `nedostajuci_dokazi`/`procesni_rizik`/`otkriveni_problemi` are all deterministic, code-computed,
zero GPT calls. The one GPT-sourced field in this payload (`kontradikcije`, sourced from Genome) is
grounded with page/document citations, not free marketing prose — consistent with the platform's own
established AR-01 (no ungrounded AI opinion presented as fact) discipline.

## The one silent-failure risk this sprint found for Phase 7

`finalize_intake_job`'s own whole-job decrypt/extract failure (`routers/smart_intake.py:1150-1167`) fails
soft, producing a per-document `povezan: false, razlog: "prazan_tekst"` entry in the finalize HTTP
response — but this response is only ever seen by whatever called the finalize endpoint (the frontend's own
upload flow), not surfaced anywhere in `GET /api/matter-intel`'s own "what's missing" payload once the
lawyer later opens the case. A lawyer who didn't watch the upload response closely has no way to discover,
from the case-detail view itself, that a specific document failed to process. Not fixed this sprint —
surfacing this in Matter Intel requires a new persisted "processing failures" field/query, a real (if
small) feature addition, not a wiring fix; recorded as `SIGMA-003` in the Debt Register.
