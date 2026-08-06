# Workspace Integration Report — Program Omega, Final Sprint 005 (2026-08-06)

Phase 1's own required deliverable: `OMEGA-012` closed, not partially. Every screen, API call, worklist
display, and dashboard card mapped to exactly one of 3 verdicts — **ACTIVE**, **RETIRED**, or
**REDIRECTED**. No 4th option, per the mission's own explicit rule.

## Method

Builds directly on Sprint 004's own `WORKSPACE_SURFACE_REGISTRY.md` (12 surfaces) plus this sprint's
own 2 forensic passes: (1) direct reading of `static/vindex.js`'s `dash_load()`/`_dashRender()` call
graph, which found Sprint 004's own registry had mis-classified 3 surfaces as frontend-live when they
were actually already dead (see `docs/omega/SHADOW_WORKFLOW_AUDIT.md`, item 1); (2) a dedicated
read-only sweep of the full navigation tree, every `onclick="fn()"` handler cross-referenced against
actual function declarations, and every `fetch(BASE_URL+'/api/...')` call cross-referenced against
`routers/*.py`'s own registered routes.

## Classification — every surface, one verdict

| # | Surface | Verdict | Detail |
|---|---|---|---|
| 1 | `GET /api/workspace` | **ACTIVE** | Wired this sprint into `dash_load()`/`_dashRender` (`wsLoad()`/`_wsRender()`) — now the first substantive section on the home page. |
| 2 | `GET /api/case-actions/predmeti/{id}` (Sprint 003) | **ACTIVE** | Had zero frontend callers before this sprint. Wired this sprint into the case-detail view (`_predActionsLoad`, new "Otvorene akcije" panel) — closes the Case→Action navigation gap (Phase 3). |
| 3 | `GET /api/case-actions/worklist` (Sprint 003) | **RETIRED** as a distinct frontend surface | Superseded by `GET /api/workspace`, which is the strict superset (adds `zadaci`/`intake_jobs` buckets). Endpoint code kept (no known external consumer, zero cost to keep), never called by the frontend, by design — Workspace is canonical. |
| 4 | Command Center (`routers/dashboard.py`) | **ACTIVE**, demoted | Still the main body of the home page (case list, top cases, unpaid invoices) — its own redundant `ai_preporuke` text panel RETIRED (see #9). |
| 5 | Morning Briefing (`routers/morning_briefing.py`) | **REDIRECTED** | In-app card was ALREADY fully dead before this sprint (confirmed: its own DOM container only ever existed in an unrelated dead code path — see `SHADOW_WORKFLOW_AUDIT.md`). Its own `loadBriefing()` call REMOVED from `dash_load()`. Redirected to its own real, still-live channel: the automatic daily email cron (`POST /api/briefing/cron`), completely unaffected. |
| 6 | Case Commander `/jutarnji` findings widget | **REDIRECTED** | Same shape as #5 — in-app widget already dead, its own call REMOVED from `dash_load()`. Redirected to Workspace for "what needs attention" (its own content was a GPT rephrasing of the same rizici/kontradikcije Workspace now shows sourced). The endpoint itself and its own on-demand `/api/commander/analiza` stay fully callable. |
| 7 | CIO Daily (`routers/cio.py`) | **ACTIVE**, demoted | Genuinely live (confirmed rendering into `#kc-cio-section`), kept as a secondary portfolio-strategy narrative — its own docstring already corrected in Sprint 004 (commit `4f6bad4`) to no longer imply it's the canonical "one action for today" (Workspace is); unchanged this sprint. |
| 8 | Health Index (`routers/health_index.py`) | **ACTIVE**, restored | Was accidentally dead (same shadow-`_dashRender` bug as #5/#6) — its own container RESTORED into the live render this sprint, since Sprint 004 explicitly wanted it kept (different scope: firm-level, not per-case). |
| 9 | `_kcPanelPreporuke` ("Preporuke" panel) | **RETIRED** | Deleted — pure text rephrasing of facts now shown sourced in Workspace. See `SHADOW_WORKFLOW_AUDIT.md`, item 3. |
| 10 | `_kcPanelRokovi` ("Današnji rokovi" panel) | **ACTIVE** | Kept deliberately — real coverage gap: `case_actions` only populates via 4 events, so any pre-Sprint-003 case is invisible to Workspace until `scripts/backfill_case_actions.py` (`OMEGA-014`) runs. This panel has no such dependency. |
| 11 | `GET /api/inbox` (`routers/inbox.py`) | **ACTIVE**, narrowed | `rociste`/`rok` item generation RETIRED from the backend itself (shadow-duplicate of `case_actions`' own Rule 1). Remaining categories (`dokument`/`naplata`/`neaktivan`) — genuinely not covered elsewhere — kept, and a real pre-existing display bug fixed (they were computed but never shown; now shown, relabeled "Ostalo za pregled"). |
| 12 | `proactive_alerts` (4 real readers) | **ACTIVE** | Different function (FYI/notification), not merged. Unchanged. |
| 13 | `notifications` (bell icon, every page) | **ACTIVE** | Different function, global scope. Unchanged. |
| 14 | Zadaci `/predmet`, `/tim` (`routers/zadaci.py`) | **ACTIVE** | Genuinely distinct (human-assigned tasks). Unchanged. |
| 15 | `GET /api/zadaci/moji` | **RETIRED** as a canonical candidate, code kept | Zero frontend references (Sprint 004's own finding, re-confirmed) — superseded conceptually by Workspace's own "Na čekanju" bucket. Not deleted (no known consumer, zero cost to keep). |
| 16 | `zadaci.py::ai_analiziraj_predmet` | **ACTIVE** | On-demand, credit-metered, 2 unique GPT-only checks not covered by `case_actions`. Unchanged (still named as `OMEGA-008`'s own cheapest future consolidation candidate). |
| 17 | Case Intelligence briefing (`routers/case_intelligence.py`) | **ACTIVE** | Per-case, on-demand, lower overlap priority. Unchanged. |
| 18 | `case_intelligence_summaries` (migration 098) | **ACTIVE**, still no read API | `OMEGA-004` remains open, unchanged by this sprint. |
| 19 | `kalendarLoad` v1 (`static/vindex.js`) | **RETIRED** | Fully dead code (shadowed), deleted this sprint. See `SHADOW_WORKFLOW_AUDIT.md`, item 2. |
| 20 | `_dashRender` v1 + its exclusive helpers | **RETIRED** | Fully dead code (shadowed), deleted this sprint (~440 lines). See `SHADOW_WORKFLOW_AUDIT.md`, item 1. |

## Definition of Done check for this phase

- **"OMEGA-012 mora biti potpuno zatvoren, ne parcijalno"**: closed for its own literal scope (Workspace
  now genuinely reads by a lawyer on page load, proven by code, not claimed). The *broader* multi-surface
  fragmentation question (4 GPT widgets still present) is intentionally NOT the same claim — re-scoped
  honestly to `OMEGA-017`, a real but different, smaller problem than "Workspace isn't wired at all."
- **"Nijedan ekran više ne sme koristiti zastarele izvore podataka ako postoji kanonski Workspace API"**:
  checked directly — no remaining live screen reads a superseded source where a canonical one exists AND
  was safe to redirect to (the exceptions, #4/#7/#10/#16, are all cases where the canonical Workspace
  API does not yet have equivalent coverage — named honestly, not silently swapped in anyway).
- **Every surface has exactly one of 3 verdicts**: yes, 20/20 above, no surface left "maybe."
