# Executive Intelligence Map — Program Tau, Master Sprint 008, Phase 1

Complete map of every executive AI surface — portfolio-wide or case-wide summary/narrative/briefing/
dashboard presented to a lawyer, as opposed to a single-purpose tool. Built from a direct read of `cio.py`
(this sprint's own named migration target) plus a parallel forensic fork covering every other surface. No
assumptions — every claim below is verified from source.

## Summary table

| Surface | Canonical Context | Case Actions | Readiness | Gap Engine | Risk Engine | Local computation | GPT boundary |
|---|---|---|---|---|---|---|---|
| `routers/morning_briefing.py` | **Yes** | **Yes** | Via context | Via context | Via context | None | Grounded (Tau 002/003) |
| `routers/workspace.py` (`GET /api/workspace`) | No (no GPT call at all) | **Yes**, primary source | N/A | No | No | Priority-vocabulary translation only | N/A — no GPT |
| `routers/dashboard.py::command_center` (live, wired in `dash_load()`) | No | No | No | No | No | **Yes — real finding**, see below | N/A — no GPT call in this endpoint |
| `routers/dashboard.py::matter_health_score` | No | No | No | No | **Yes**, direct call (Tau 007's own confirmed 6th family member, reconfirmed independently here) | — | N/A — no GPT |
| `routers/portfolio.py::portfolio_dashboard` (live) | No | No | No | No | No | Not applicable — pure counts/narrative, no risk/readiness/priority concept touched at all | N/A — no GPT |
| `routers/health_index.py` (live, wired in `dash_load()`) | No | No | No | No | No (reads raw `predmeti.rizik_nivo` column) | **The largest finding this phase**, see below | **GPT-decided, ungrounded** — see below |
| `routers/admin_dashboard.py` | — | — | — | — | — | Not applicable — founder-only ops (security/notifications), no case concept | N/A |
| **`routers/cio.py` (this sprint's own migration target)** | **No** | **No** | **No** | **No** | **No** | **Yes — entire portfolio built from raw `case_dna` fields** | **GPT-decided** — see `docs/tau/CIO_FORENSIC_REPORT.md` |

## `dashboard.py::command_center` — a smaller, real finding, out of this sprint's own migration scope

`predmeti_visok_rizik`/`pad_procene` parse a STORED, historical risk JSON blob out of `predmet_istorija`
rows (`pitanje LIKE '[Rizik]%'`) — not `calculate_procesni_rizik`, not `build_case_context()`, an
unidentified prior write path. `ai_preporuke` is a separate, explicitly-commented "rule-based (without AI
call)" heuristic built directly from raw table counts — no GPT decision, but a 2nd, independent
prioritization surface running alongside `case_actions`/Workspace's own canonical next-action list. No GPT
call in this endpoint itself, so it is out of Phase 5's own GPT-boundary concern, but it is a real
parallel-reasoning finding for a future `TAU-012`-style migration sweep.

## `health_index.py` — the standout finding, explicitly NOT migrated this sprint

A complete, independent 6-component "Firm Health Score" (0-100): Deadline Pressure / Case Strength /
Billing / Client Engagement / Portfolio Risk / Caseload — entirely hand-rolled, zero use of any canonical
engine. Case Strength reads Genome's own `case_dna.snaga_predmeta_procent` directly (bypassing
`build_case_context()`, the same bypass pattern `cio.py` has). Portfolio Risk reads a raw `predmeti.rizik_nivo`
column directly, never `calculate_procesni_rizik`. **`_compute_chief_partner` asks GPT to independently
generate "3 concrete actions a partner would take today," fed only by this file's own bespoke `alerts`
list — never `case_actions`, never Workspace, never Case Commander.** This is a live, GPT-decided, fully
independent "what should the firm do today" recommendation system running alongside `case_actions`/
Workspace, feeding on a wholly separate scoring model — the same class of `TAU-017` finding as `cio.py`,
in a different file, not previously named as its own debt item.

**Why not migrated this sprint**: the mission's own explicit Phase 3 instruction names `cio.py` specifically
("Migriraj cio.py"), and this whole program's own repeated discipline (Tau 005/006/007 each scoped to
exactly one file) exists because each migration surfaces its own field-level nuances that don't compress
safely into a single sprint alongside another. Named here, formalized as a new debt item, prioritized in
`docs/tau/TAU_FINAL_HANDOVER.md` — not silently deferred without a trail.

## Confirmed clean / already canonical

`morning_briefing.py` (Tau 002/003, reconfirmed by direct import/usage check) and `workspace.py` (no GPT
call at all — a pure deterministic aggregation over `case_actions`, architecturally exempt from this
mission's own GPT-boundary concern by construction). `portfolio.py` touches no risk/readiness/priority
concept at all — genuinely out of scope, not a finding.
