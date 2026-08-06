# Unified Workspace Architecture — Program Omega, Sprint 004 (2026-08-06)

Phase 2 (Canonical Responsibility Matrix) + Phase 3 (Unified Workspace Model)'s own required deliverable.
Reads on top of `docs/omega/WORKSPACE_SURFACE_REGISTRY.md` (Phase 1) — 12 surfaces found, 6 of them
independently live on the SAME home page. This document makes ONE firm decision per surface — no
surface is left "maybe both."

## The decision framework

Per the mission's own instruction ("Nema kompromisa. Jedna funkcija = jedan vlasnik.") — but "jedna
funkcija" first requires correctly SCOPING what function each surface actually performs. Not every
surface answering a version of "what needs attention" performs the SAME function:

- **Deterministic operational action** ("this specific case_actions row must be resolved, sourced,
  lifecycle-managed") — exactly ONE legitimate owner: Program Omega Sprint 003's `case_actions` /
  `_consequence_refresh_case_actions`.
- **Human-assigned task** ("a partner told an associate to do X") — a genuinely different function,
  real human input, no AI substitute exists or should exist for it.
- **Narrative/strategic interpretation** ("here's GPT's read on what's going on") — a genuinely
  different function from an operational worklist: synthesis and framing, not a verifiable queue.
- **Passive FYI notification** ("something changed, you may want to know") — lower-stakes than an
  operational action, doesn't need a lifecycle, just needs to be seen once.

The Responsibility Matrix below assigns each of the 12 surfaces to exactly one of 3 verdicts —
**OSTAJE** (stays, unchanged ownership), **POSTAJE PODMODUL** (stays, but is explicitly demoted from
"the" canonical view to a named, secondary/optional layer), **GASI** (retired as a canonical
candidate — code may remain if deletion carries needless risk for zero benefit, but it is no longer
positioned as anyone's answer to "what does the lawyer see").

## Responsibility Matrix

| # | Površina | Funkcija | Odluka | Obrazloženje |
|---|---|---|---|---|
| 1 | Command Center (`dashboard.py`) | Portfolio case-list overview (hearings today, top cases, unpaid invoices) | **POSTAJE PODMODUL** | Genuinely useful overview widget; its own `ai_preporuke` rule-based recap duplicates Workspace's job and is demoted — Workspace is now canonical for "what must I do," Command Center remains canonical for "here's my case list." |
| 2 | Morning Briefing (`morning_briefing.py`) | Email digest, narrative | **POSTAJE PODMODUL** | Different delivery channel (email) is real, retained value — no longer positioned as an in-app operational view. |
| 3 | Case Commander `/jutarnji` (`case_commander.py`) | GPT cross-case narrative | **POSTAJE PODMODUL** | Self-description ("srce platforme") corrected this sprint (docstring fix, zero behavior change) — retained as an optional AI-perspective layer, explicitly no longer canonical. |
| 4 | CIO Daily (`cio.py`) | GPT portfolio strategy ("biggest opportunity/risk") | **POSTAJE PODMODUL** | Closest GPT analog to the Action Engine's own goal, but strategic/portfolio framing is a genuinely different question than "what specific thing is due" — retained, demoted, documented (module docstring updated this sprint). |
| 5 | Notifications (`notifications.py`) | Event-log FYI stream (bell icon) | **OSTAJE** | Different function — passive, ambient, global (every page), not an operational worklist. Its own independent deadline/inactivity computation (a 6th one found) is named as a future integration candidate (`OMEGA-010`), not eliminated this sprint. |
| 6 | Health Index (`health_index.py`) | Firm-level (not per-case) health metric | **OSTAJE** | Different scope entirely — portfolio health, not "what should I do." |
| 7 | `proactive_alerts` (`shared/proactive_alerts.py`) | Cross-module alert table, real consumers (4 modules) | **OSTAJE** | Real, consumed, different function (a triggered alert, not a persistent worklist item) — candidate FYI-tier input for a future Workspace extension, not integrated this sprint. |
| 8 | Zadaci `/predmet`, `/tim` (`zadaci.py`) | Human-assigned team task management | **OSTAJE** | The one genuinely irreplaceable human-input function on this list. |
| 8b | Zadaci `/moji` (`zadaci.py`) | Personal cross-case task view | **GASI** (kao kanonski kandidat) | Zero frontend references (confirmed, Phase 1). Superseded conceptually by Workspace's own "na_cekanju" bucket (reads the SAME `zadaci` rows, status='ceka'). Endpoint code retained (deprecation docstring added this sprint) — no known external consumer, deleting a working route for zero benefit is unnecessary risk. |
| 9 | `zadaci.py::ai_analiziraj_predmet` | On-demand GPT task suggestion, already grounded in `risk_engine.py` | **OSTAJE** | Distinct trigger model (manual button, rate-limited) and 2 unique GPT-only checks `case_actions` doesn't cover (inactivity, unpaid billing) — real, non-duplicated value. Still named (Sprint 003's own `ACTION_PRODUCER_REGISTRY.md`) as the cheapest future consolidation target for its 3 already-`case_actions`-covered categories. |
| 10 | Case Intelligence briefing (`case_intelligence.py`) | Per-case, on-demand deep-dive synthesis | **OSTAJE** | Lower overlap priority — on-demand, not a landing surface (confirmed, Phase 1). |
| 11 | `case_actions` Worklist / new `/api/workspace` | Deterministic, sourced, lifecycle-managed operational action list | **OSTAJE, BECOMES CANONICAL** | The mission's own central deliverable — see Canonical Workspace Spec. |
| 12 | `case_intelligence_summaries` (migration 098) | Sourced case-level batch summary | **OSTAJE** | Data exists, no read API yet (`OMEGA-004`, still open, unchanged this sprint). |

## Why "postaje podmodul," not "gasi," for the 4 GPT narrative surfaces

Deleting or disabling 4 live, revenue-bearing, already-shipped GPT features (Command Center's own
recap, Morning Briefing, Case Commander, CIO Daily) in one autonomous session, with no live-browser
verification available and no dedicated test coverage for the FRONTEND rendering of any of them, would
be exactly the kind of blind, high-blast-radius production change this whole engagement's own standing
discipline avoids (matching precedent: Smart Intake's own frontend was named as a gap for 3 sessions
before being explicitly authorized and built in "Operation Beta Closure," not attempted blind). The
Responsibility Matrix decision is made firmly (all 4 are explicitly non-canonical as of this sprint,
documented in each module's own code); the RISKIER action (removing or rewriting live GPT prompt
behavior) is deliberately not taken without a dedicated pass and/or explicit authorization, matching
established precedent — named as `OMEGA-012` (see Debt Register).

## What "canonical" concretely means as of this sprint

`GET /api/workspace` (`routers/workspace.py`) is the ONE endpoint whose job is "what does the lawyer
need to do, right now, across every case." It has zero competing writers (it writes nothing at all —
pure read aggregation) and reads from exactly 3 already-single-owner sources:
`case_actions` (Sprint 003, deterministic), `zadaci` status='ceka' (human-assigned, waiting),
`intake_jobs` status='awaiting_review' (Smart Intake's own pending-human-decision queue). No other
endpoint in the platform computes this same aggregation.

## The honest gap: frontend wiring

`case_actions`'s own Worklist (Sprint 003) already had zero frontend references before this sprint;
the new `/api/workspace` endpoint inherits that same gap on day one — it is architecturally canonical
but invisible to an actual lawyer until the home page (`dash_load()`, `static/vindex.js:1206`) is
rewired to read it. This is the single most consequential unresolved item from this sprint — named
explicitly as `OMEGA-012` (Debt Register), not silently claimed as done. Matches this whole
engagement's own "backend-first, frontend needs its own dedicated, escalated pass" pattern for every
Program Omega sprint so far (Sprint 001-003 never touched frontend either).
