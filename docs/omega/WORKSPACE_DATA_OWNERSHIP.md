# Workspace Data Ownership — Program Omega, Sprint 004 (2026-08-06)

Phase 4's own required deliverable: does the same fact, the same status, or the same task exist in
more than one place? If so, eliminate it. This document lists every duplication `WORKSPACE_SURFACE_REGISTRY.md`
found, and states plainly what was eliminated this sprint versus what was found, decided, and
deliberately deferred (with a debt-register item), matching this whole engagement's own "no
conclusion without source, no silent gap" discipline.

## Finding 1 — 3 independent alert/notification tables

`proactive_alerts` (Sprint Alpha, 2026-08-04), `notifications` (`routers/notifications.py`, its own
16-type taxonomy), and `case_actions` (Sprint 003) each independently store "something needs
attention," none aware of the other 2.

**Eliminated this sprint**: nothing — genuinely different functions once examined closely (see
`UNIFIED_WORKSPACE_ARCHITECTURE.md`'s Responsibility Matrix: `case_actions` = operational
must-do-and-verifiable, `proactive_alerts`/`notifications` = passive FYI). Merging 3 live, separately-
consumed tables into one schema is a real migration, not a read-side aggregation — out of this sprint's
safe scope.

**Decision**: named as `OMEGA-010` — a future sprint should decide whether `proactive_alerts` becomes
an additional Workspace input tier (below `case_actions` in urgency, above pure silence), and whether
`notifications`' own independent deadline/inactivity computation (a 6th one found, Phase 1) should
instead be TRIGGERED by Case Evolution events rather than its own polling.

## Finding 2 — At least 5 independent priority vocabularies

`case_actions.prioritet` (critical/high/medium/low/informational), `identify_case_problems`'s own
`ozbiljnost` (kritican/vazan/info), `notifications.priority` (urgent/high/normal/low/info),
`zadaci.prioritet` (hitno/visoko/normalan/nisko), and CIO's own informal 0-100 `kriticnost` score — 5
different words/scales for the same underlying concept of "how urgent is this."

**Eliminated this sprint**: the 2 that collide inside `GET /api/workspace` itself —
`case_actions.prioritet` and `zadaci.prioritet` are translated onto ONE shared vocabulary
(`_ZADACI_PRIORITET_MAP`, `routers/workspace.py`) FOR THIS VIEW ONLY, so a Workspace item's priority
means the same thing regardless of which underlying table it came from. Neither source table's own
schema/API changed.

**Decision**: named as `OMEGA-011` — a platform-wide canonical priority scale (with per-system
translation adapters, the same pattern applied here) is a real future consolidation, deliberately not
attempted for `notifications`/CIO/`identify_case_problems`'s own callers this sprint (would require
touching 3+ more live modules without dedicated verification).

## Finding 3 — Command Center's own internal duplication (`dashboard.py`)

Verified directly this sprint (not just cited from the registry): `command_center` reads its own
`predmet_istorija` rows tagged `"[Rizik]"` (a historical log of past GPT risk assessments) to detect
"did risk get WORSE between two successive readings" — investigated closely and found to be a
genuinely DIFFERENT question from `risk_engine.py::calculate_procesni_rizik`'s own live deterministic
score (a trend-over-time comparison of stored history, not a live recompute) — NOT the same duplication
shape as the already-fixed `ccc.py::_compute_health`/`dashboard.py::matter_health_score` cases from
earlier in this engagement (Project Nexus/Sentinel), where 2 code paths computed the identical live
number differently. **Not eliminated — verified as a legitimate, distinct feature, not a fixable
duplicate.** Its `rokovi` vs. `predmet_hronologija` dual-read (`dashboard.py:49-54`'s own 2026-07-24
comment) is also NOT new duplication — it's a previously-made, deliberate, already-reasoned merge to
cover 2 real, separate write paths, unrelated to this sprint's own action-tracking scope.

## Finding 4 — `predmet_dokumenti` query missing `tip_dokaza` (carried over from Sprint 003's own `OMEGA-006`)

Re-confirmed this sprint: `routers/matter_intel.py` and Sprint 002's own
`_consequence_case_intelligence_summary` still omit `tip_dokaza` from their own `predmet_dokumenti`
selects (G-028) — `_compute_target_actions` (Sprint 003) was already fixed for its own call site.
**Not touched again this sprint** — same reasoning as `OMEGA-006`, unchanged.

## Finding 5 (NEW, found and fixed this sprint) — `closed_at`/`updated_at` written as the un-castable literal string `"now()"`

`_consequence_refresh_case_actions` (Sprint 003) wrote `{"closed_at": "now()"}`/`{"updated_at": "now()"}`
as literal JSON string payload values sent to PostgREST. PostgreSQL's `timestamptz` input parser
recognizes the special value `'now'` (no parentheses) but does NOT document `'now()'` (with
parentheses) as an equivalent — a pattern copied from elsewhere in the codebase (9 other files use the
same literal, e.g. `routers/evidence.py`) but never previously load-bearing for a query that FILTERS
by that column. This sprint's own `zavrseno_nedavno` bucket is the first thing in the platform to
`.gte("closed_at", since)` against this specific column — making this the first place the bug would
have visibly broken something (an always-empty Completed bucket, or a hard query error, depending on
exact Postgres behavior).

**Eliminated this sprint**: `services/case_evolution.py::_consequence_refresh_case_actions` now computes
a real Python `datetime.now(timezone.utc).isoformat()` once per call and reuses it for both the
`updated_at` and `closed_at` writes — unambiguously correct regardless of Postgres's exact parsing
behavior for the old literal.

**Decision**: the other 9 pre-existing `"now()"` call sites elsewhere in the repo are UNCHANGED —
verifying/fixing all of them is a real, separate, repo-wide audit outside this sprint's own Workspace
charter. Named as `OMEGA-013` in the Debt Register.

## Finding 6 — `zadaci.py::ai_analiziraj_predmet` still creates `zadaci` rows for facts `case_actions` already tracks automatically

Re-confirmed (already named in Sprint 003's own `ACTION_PRODUCER_REGISTRY.md`, Producer 5): its 3
`risk_engine.py`-grounded categories (missing evidence, missing doc types, critical deadlines) now
duplicate what `case_actions` already creates automatically, with a different lifecycle (manual
"mark done" vs. automatic close-on-resolution) and a different table.

**Not eliminated this sprint** — touching a live, credit-metered, on-demand GPT endpoint's own task-
creation behavior needs its own verification pass (would a lawyer who already clicked this button
expect their existing `zadaci` rows to suddenly stop appearing?). Named again, still open, tracked as
part of `OMEGA-008`'s own broader consolidation decision (Sprint 003).

## Summary: what actually changed this sprint

| Finding | Action |
|---|---|
| 3 alert tables | Documented, not merged (`OMEGA-010`) |
| 5 priority vocabularies | Translated locally inside Workspace only (`_ZADACI_PRIORITET_MAP`); platform-wide unification named (`OMEGA-011`) |
| Command Center's "3rd risk algorithm" | Verified as a legitimate, distinct feature — NOT a duplicate, no fix needed |
| `tip_dokaza` gap (2 remaining callers) | Unchanged, `OMEGA-006` still open |
| `"now()"` string literal (`case_actions`) | **Fixed** — real computed timestamp, own call site only |
| `ai_analiziraj_predmet` vs `case_actions` overlap | Documented, not touched, part of `OMEGA-008` |
