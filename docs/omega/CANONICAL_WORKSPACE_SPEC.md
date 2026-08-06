# Canonical Workspace Spec — Program Omega, Sprint 004 (2026-08-06)

Phase 3's own required deliverable: the ONE operational model, and the exact, grounded data source
behind every bucket. Implemented in `routers/workspace.py::get_workspace` (`GET /api/workspace`).

## The model

```
Workspace
 ├─ Danas           (Today)
 ├─ Kritično         (Critical)
 ├─ Predstojeće      (Upcoming)
 ├─ Za pregled       (Review Required)
 ├─ Na čekanju       (Waiting)
 └─ Završeno nedavno (Completed, last 3 days)
```

Buckets are **mutually exclusive** — an item appears in exactly one, chosen by precedence: anything due
today claims the "Danas" slot first (regardless of its own priority/type), then whatever remains is
sorted by priority into Critical/Upcoming, and Review/Waiting/Completed are their own independent,
non-overlapping data sources.

## Every bucket, grounded (Agent 4's own "no conclusion without source" rule, reused from Sprint 003)

| Bucket | Source | Query | Why this is honest, not invented |
|---|---|---|---|
| **Danas** | `case_actions` (`rok == today`) ∪ `zadaci` (`status='ceka'`, `rok_datum == today`) | `.eq("status","open")` + date compare; `.eq("status","ceka")` + date compare | Both are real, already-owned tables' own `rok`/`rok_datum` columns — no new date logic invented, just a today-vs-not-today split of data that already exists. |
| **Kritično** | `case_actions` where `prioritet='critical'`, `status='open'`, not due today | Reuses Sprint 003's own `_fetch_open_actions` unchanged | Sprint 003's own canonical, deterministic priority — never recomputed here. |
| **Predstojeće** | `case_actions` where `prioritet in ('high','medium')`, `status='open'`, not due today | Same source, same reuse | Same reasoning. `low`/`informational` actions are deliberately excluded from every active bucket (Scenario 6's own requirement — "only what's actually important") but remain reachable via `GET /api/case-actions/predmeti/{id}`, not deleted. |
| **Za pregled** | `intake_jobs` where `status='awaiting_review'`, `uploaded_by=uid` | New read query (`_fetch_review_jobs`) — SELECTs an already-existing column (`intake_jobs.status`, set by Smart Intake's own established review-queue mechanism, `routers/smart_intake.py`) | Not a new capability — this exact status value already existed and already blocked automation for that document; nothing computes it freshly here, it's read as-is. Always `prioritet='high'` (a pending review blocks Smart Intake's own automation for that specific document until resolved — never silently low-priority). |
| **Na čekanju** | `zadaci` where `status='ceka'`, `dodeljen_uid=uid`, not due today | New read query (`_fetch_waiting_zadaci`) | `"ceka"` is a real, pre-existing status value in `zadaci`'s own CHECK constraint (migration 045) — not invented for this sprint. |
| **Završeno nedavno** | `case_actions` where `status='closed'`, `closed_at >= now()-3d` ∪ `zadaci` where `status='zavrseno'`, `zavrseno_u >= now()-3d` | New read query (`_fetch_recently_completed`) | Both timestamp columns already existed for their own tables' own purposes (Sprint 003's `closed_at`, `zadaci`'s pre-existing `zavrseno_u`). The 3-day window is a display choice (an operational board shows what JUST changed, not full history — both tables already separately retain their own complete history, nothing is lost by windowing this ONE view). |

## Priority-vocabulary translation (the one piece of new logic)

`case_actions.prioritet` (`critical`/`high`/`medium`/`low`/`informational`) and `zadaci.prioritet`
(`hitno`/`visoko`/`normalan`/`nisko`) are 2 independently-worded vocabularies for the same underlying
concept (see `WORKSPACE_DATA_OWNERSHIP.md`). `routers/workspace.py::_ZADACI_PRIORITET_MAP` translates
zadaci's own vocabulary onto case_actions' own vocabulary FOR THIS VIEW ONLY — the underlying `zadaci`
table and its own API (`routers/zadaci.py`) are completely untouched; a `zadaci` row keeps its own
native `"visoko"` everywhere else, Workspace just needs one consistent sort order across 2 tables'
worth of items in the same list.

```python
_ZADACI_PRIORITET_MAP = {"hitno": "critical", "visoko": "high", "normalan": "medium", "nisko": "low"}
```

## Sort order within a bucket

Reuses Sprint 003's own `_PRIORITY_ORDER`/`_sort_key` (`routers/case_actions.py`) unchanged — imported
directly, not re-implemented — so an item's position is identical whether viewed via the old
`case_actions` Worklist or the new unified Workspace. One ordering, one owner (Core Consolidation
principle, applied again).

## What Workspace deliberately does NOT do

- **Does not write anything.** Every table it reads has exactly one existing, unchanged writer
  (`case_actions` ← `_consequence_refresh_case_actions`; `zadaci` ← `routers/zadaci.py`'s own endpoints;
  `intake_jobs` ← Smart Intake). Workspace is purely an aggregation/read layer — this is what makes it
  safe to build without touching 3 other live systems' own write paths.
- **Does not call GPT.** Zero LLM calls anywhere in `routers/workspace.py` — every bucket is a filter/
  sort over already-computed, already-deterministic data.
- **Does not merge `proactive_alerts` or `notifications`.** Both are a genuinely different function
  (passive FYI, not an operational action) — see `UNIFIED_WORKSPACE_ARCHITECTURE.md`'s own
  Responsibility Matrix. Named as a possible future FYI-tier extension (`OMEGA-010`), not attempted here.
- **Does not cache.** Every call reads live — this is what makes Phase 5's "no manual refresh" property
  true by construction: there is no cache to invalidate, so a write through `_consequence_refresh_case_actions`
  (or a `zadaci`/`intake_jobs` status change) is visible on the very next `GET /api/workspace` call,
  proven by `tests/test_omega_sprint004_case_to_workspace_flow.py`.
