# Case Genome V3 — Gap Analysis (2026-07-18)

Snapshot of the repository on 2026-07-18. This is a point-in-time document, not a
durable architectural decision — re-run before acting on it if much time has passed.
Triggered by a "Case Genome V3" master-prompt architecture bible (event bus,
multi-agent pipeline, fact graph, risk/strategy/red-team engines, git-style
versioning, learning loop) evaluated against the live implementation.

Governing rules (see `MEMORY.md` → `project_strategic_direction`,
`project_case_genome`):

- **Rule A (product features):** any new user-facing functionality must trace to
  one of four evidence sources — LEC, Hall of Shame, Office Accuracy Dashboard, or
  real user/pilot feedback. No evidence, no build.
- **Rule B (platform architecture):** infrastructure changes may proceed without
  direct user evidence if they satisfy all four: don't change the API, don't
  change the UX, improve maintainability/scalability, and don't add complexity
  without clear benefit.

## Findings by module

| Module | Status | Notes |
|---|---|---|
| Theory of the Case | Partial | `case_dna.py:37-44` (pravni_identitet/sustina_spora/osnov_odgovornosti/uzrocna_veza), `:71-72` (argumenti_za/protiv). No alternative-theories array. |
| Timeline Engine | Partial | `intelligence_timeline.py` + genome `datumi_kljucni`/`rokovi_kriticni`. No missing-event detector beyond `nedostaje`. |
| Evidence Engine | Partial | `case_dna.py:86-89` dokazi_rang (score/stars/reason) + `evidence.py` + `migrations/016_evidence_vault.sql`. No audit trail, no human-override field, no per-item confidence. |
| Fact Graph | Partial | `evidence_graph.py` builds an entity graph via one GPT call. Not a typed Fact→Evidence→Claim→Argument→Rule→Risk→Outcome chain. |
| Risk Engine | Partial (decent coverage) | `matter_intel.py:106-125` rule-based rizik_score, `:277` 5-dim uncertainty semaphore, genome `najslabija_tacka`, `strategija.py:313` kljucni_rizici. No separate probability/impact/confidence fields per risk. |
| Strategy Engine | **Implemented** | genome `strategija` block + `strategija.py` (7 specialized endpoints: litigation, sudija, due-diligence, revizor, witness, sudija-v2, kompletna-analiza orchestrator). No explicit aggressive/defensive/minimal-risk labels, but functionally covered. |
| Red Team | **Implemented** | `strategija.py:62-64` `POST /api/strategija/red-team`. Standalone endpoint, not gated into Genome refresh. |
| Next Action Engine | Partial | `matter_intel.py:231 _compute_next_action()` + genome `nedostaje`. No task-object model (assignee/due-date/task table). |
| Firm DNA | **Implemented, standalone** | `learning.py:914-1172` (`/firm-dna`, `/refresh`, `/history`) + `migrations/045_firm_intelligence.sql`, `046_firm_memory.sql`. Not wired through Genome — separate state, violates spec's single-source-of-truth intent. |
| Multi-Agent Pipeline | Partial, generic | `multi_agent.py` `run_parallel`/`run_pipeline` chain agent outputs. Genome extraction (`case_dna.py:_extract_genome`) is one monolithic GPT-4o call, not decomposed into specialist sub-agents. |
| Critic Layer / Genome Validator | Missing | No confidence gate blocking a save anywhere in the codebase. |
| Explainability | Partial (data layer only) | `case_dna.py:74-77` snaga_faktori, dokazi_rang razlog. Click-to-source (page/paragraph) is a frontend question, not verified here. |
| Impact Propagation | Missing — current design does the opposite | Every refresh fully regenerates the whole Genome JSON (`_extract_genome`); no partial/incremental update. |
| Versioning | Partial, more than expected | Auto-increment `verzija`, `predmet_genome_history` table, real delta diffing (`_compute_delta`). `compare_docs` (`case_dna.py:547`) compares two *documents*, not two Genome versions — separate feature. Missing: rollback/restore endpoint (history is read-only today). |
| Learning Loop | Partial, substantial | `learning.py` has outcome tracking, counterfactual analysis, lessons w/ decay-check, performance/impact reports. Gap: no direct-edit UI on Genome, so "human override of a Genome field" specifically isn't captured. |
| Event-Driven Architecture | **Partial — corrected 2026-07-18** | `services/event_bus.py` (362 lines) is a real outbox-pattern bus: `EventType` enum, `Event`, `EventBus`, `emit()`, `dispatch_pending_events()`, `DispatchLoop` started/stopped in `api.py:785,798`. Used and crash-tested by the intake pipeline (`tests/test_intake_e2e_restart.py`, `test_intake_phase0.py`). **Not wired to Genome** — `case_dna.py` never imports it; every Genome mutation is still a direct synchronous DB write, not an emitted event. Original pass of this analysis searched only `shared/` and `routers/` and missed `services/`, incorrectly reported "Missing." |

## Evidence-source check (Rule A gate)

- `evaluation/lec/annotations.json` → `dokumenti: []` — 0 annotated documents.
- `evaluation/hall_of_shame/incidents.json` → `incidenti: []` — 0 incidents.
- No Office Dashboard finding found citing Genome specifically.
- Pilot (3-5 firms, per `project_strategic_direction`) has not launched — no real-user feedback stream yet.

**Missing but evidence-backed (Rule A): none.** Every "Missing" item above (Critic
Layer, Impact Propagation, cross-module Genome wiring for Firm DNA/Red Team/Next
Action) is currently **missing and speculative** under Rule A — not because the
ideas are bad, but because no LEC/Hall-of-Shame/Dashboard/user finding has flagged
them yet as user-facing functionality.

## Candidates under Rule B (infrastructure, evidence not required)

Items the founder explicitly greenlit as infra-track, subject to the four Rule B
conditions (no API change, no UX change, improves maintainability/scalability, no
unjustified complexity):

- **Event Bus → Genome wiring.** Lowest-risk of the group — the bus already
  exists and is production-tested elsewhere; this is "connect an existing pipe,"
  not "build a new one." Would also be the mechanism that eventually enables real
  Impact Propagation (only recompute what an event says changed) instead of full
  regeneration on every refresh.
- **Internal Agent Registry.** No current inventory of agents beyond `multi_agent.py`'s
  hardcoded list (`lista_agenata`) — formalizing this doesn't change any public API.
- **Genome State Machine.** Would need to confirm it doesn't change the `case_dna`
  response shape before treating it as pure infra.
- **Version restore.** Additive endpoint on top of the existing (already
  implemented) history table — the data is already there, this just exposes a
  write path back onto it.
- **Typed models.** Pydantic models for the Genome JSON shape instead of raw
  dicts — internal only, no API/UX surface change.

None of these are scheduled or started as of this document. This is a reference
snapshot for when work on any of them begins — re-verify file/line citations
before acting, since the codebase moves.
