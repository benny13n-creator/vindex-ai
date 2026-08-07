# CASE_STATUS_CANONICAL_MODEL.md — Operation Single Brain, Mission 002

## Current state (Team 5's independent audit, re-confirmed by Team 1)

`predmeti.status` is a free-text column (`supabase_setup.sql:287`, `TEXT NOT NULL DEFAULT
'aktivan'`) with **no DB-level CHECK constraint** and **no enum validation on write**
(`PATCH /api/predmeti/{id}`, `api.py:3644-3652`, passes the value through unchecked). In
practice, only 2 values are ever actually written anywhere in the codebase — `"aktivan"` and
`"zatvoren"` — but 5 different modules independently classify "is this case active" with
non-identical predicate logic:

| Module | Active/closed rule |
|---|---|
| `analytics.py` / `copilot.py` | closed = `("zatvoren", "arhiviran")` |
| `dashboard.py` | active = "not in a 3-value closed set" |
| `cio.py` / `morning_briefing.py` / `zakon_monitoring.py` | active = 3-value allow-list `("aktivan", "u_toku", "pending")` |
| `conflict_check.py` | active = 5-value allow-list, now includes both `"u toku"` and `"u_toku"` (Mission 001 fix) |
| `predmeti_close.py` (implicit) | the only real writer of `"zatvoren"` |

This is currently low-risk in practice **only because** no writer produces `"arhiviran"`,
`"u_toku"`, or `"pending"` today — every module's extra allow-list values are dead weight, not
active divergence. It is a landmine, not a live bug: the day any writer starts producing one of
those values (a plausible future feature — e.g. an actual archive action, or a pending-review
intake state), 4 of these 5 modules would silently disagree about whether that case counts as
active, with no test or constraint to catch it.

## Why this mission does not fully close it

Unifying 5 independently-evolved classification call sites into one shared predicate is a
larger, riskier change than this mission's time budget supports safely — each site's "active"
definition subtly affects a different feature's own behavior (portfolio counts, conflict
screening, briefing inclusion), and collapsing them without individually verifying each
call site's actual intent risks introducing a NEW behavior change rather than removing a
duplicate. This is explicitly named as debt (`SINGLEBRAIN2-DEBT`, see
`FRAGMENTATION_ELIMINATION_REPORT.md`), not silently dropped.

## What a genuine canonical model requires (specification for the next mission, not implemented here)

1. **CANONICAL_OWNER**: a single `shared/case_status.py::is_active(status: str) -> bool`
   function, matching the pattern this mission established for readiness
   (`READINESS_AUTHORITY_SPEC.md`) — one place every module imports from instead of
   redeclaring its own predicate.
2. **Validation rules**: the canonical predicate should recognize `"aktivan"` as the only
   currently-real active value and `"zatvoren"` as the only currently-real closed value, with
   documented future values (`"arhiviran"`, `"pending"`, etc.) added explicitly and
   simultaneously to the DB CHECK constraint (a migration, run by the founder per this
   engagement's standing convention — never auto-run by the coordinator) and the canonical
   function together, so the two can never drift.
3. **All consumers**: `analytics.py`, `copilot.py`, `dashboard.py`, `cio.py`,
   `morning_briefing.py`, `zakon_monitoring.py`, `conflict_check.py` — each migrated one at a
   time, with its own before/after test proving the case population it operates over is
   unchanged for real data (all `{"aktivan","zatvoren"}` cases), before removing its local
   predicate.
4. **DB CHECK constraint**: `ALTER TABLE predmeti ADD CONSTRAINT status_valid CHECK (status IN
   (...))`, matching the pattern `case_actions.tip`/`prioritet`/`status` already demonstrates is
   achievable (migration 099) — currently the one clean counter-example in the whole `predmeti`
   table's own column set.

This document exists so the next mission does not need to re-derive the diagnosis from zero —
Team 5's and Team 1's full citations are in `SINGLE_BRAIN_DECISION_MAP.md` and
`docs/singlebrain/TRUTH_REGISTRY.md` (from Mission 001, §14).
