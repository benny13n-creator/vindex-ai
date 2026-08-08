# Program Phoenix — Mission 013: Infra Reliability

**Date**: 2026-08-08
**Debt items addressed**: `LIVINGSYS-DEBT-040` (fully), `LIVINGSYS-DEBT-041` (partially — the
app-level timeout half; the visual progress-indicator half explicitly deferred, see below).
**Explicitly not attempted**: `LIVINGSYS-DEBT-005` (register's own assessment: needs a firm-wide
autosave/state-persistence architecture decision, not a bounded mechanical fix — "explicitly the
kind of new-system design this mission's own rules say not to invent blind"); `LIVINGSYS-DEBT-035`
(blocked on a founder product decision: re-fetch vs. staleness warning); `LIVINGSYS-DEBT-023`
(register's own assessment: "a new capability, not a fix").

## Why these were grouped, and why the deferred items were deferred

All 4 items in the "Infra/reliability" family were surveyed together. 2 (`-005`, `-035`)
explicitly require a decision only the founder can make; 1 (`-023`) is explicitly named as new
capability work, not a fix — all 3 correctly deferred rather than forced, consistent with this
program's treatment of `-020`/`-042` in earlier missions. `-040` and `-041` are the only 2
genuinely bounded, mechanical items remaining in this cluster.

## Phase 1 — Reproduction

- `-040`: confirmed `routers/dashboard.py::command_center` (13-way `asyncio.gather`),
  `::matter_health_score` (6-way), and `routers/workspace.py::get_workspace` (a standalone fetch
  plus a 3-way gather plus `_fetch_recently_completed`'s own 2-way gather) all rely purely on the
  Supabase client library's own implicit ~120s ceiling per query — no endpoint-level fast-fail.
- `-041`: confirmed `pred_upload_doc` (the primary case-document upload flow) calls plain
  `fetch()` with no `AbortController` — a hung/very slow upload leaves the user staring at a
  spinner indefinitely with no escape and no explicit error.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

- `-040`: new `shared/query_timeout.py` (`gather_with_timeout`, `single_with_timeout`) — the
  single canonical helper both files now use. `gather_with_timeout` wraps `asyncio.gather(...,
  return_exceptions=True)` in `asyncio.wait_for`; on timeout, returns a `TimeoutError`
  placeholder for every coroutine, transparently flowing through each caller's ALREADY-EXISTING
  `isinstance(r, Exception)` fallback handling (a pre-existing requirement of
  `return_exceptions=True`) with zero new call-site logic. `matter_health_score` additionally
  distinguishes a timeout on its ownership-check query from a genuine 404 (a timeout must never
  be misreported as "case doesn't exist").
- `-041`: new `_fetchWithTimeout()` JS helper (`AbortController`-based, 90s bound) wired into
  `pred_upload_doc` (the primary case-document upload flow), with a distinct, honest error
  message (`AbortError` → "otpremanje predugo trajalo," not the generic "no connection"
  message). **Scope decision**: only this one flagship endpoint was hardened this mission, not
  all 6+ upload call sites in the frontend — the pattern is now established for reuse, but
  applying it everywhere plus building a real percent-based progress bar (the debt item's other
  named option, `XMLHttpRequest.upload.onprogress`) is real, separate UI-design work, not a
  minimum-risk mechanical port.

`static/sw.js` `CACHE_NAME` bumped `vindex-v103` → `vindex-v104` (this mission touched
`vindex.js`).

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_013_infra_reliability.py`, 9 tests. Zero pre-existing
tests needed modification (confirmed via a targeted 200-test subsystem run, 8.31s, no hangs).

## Phase 5 — Original scenario rerun

- `test_gather_with_timeout_returns_timeout_placeholders_on_hang` and
  `test_command_center_degrades_gracefully_on_query_timeout` directly reproduce the "no
  fast-fail" scenario.
- `test_fetch_with_timeout_helper_present_and_used_by_pred_upload_doc` directly confirms the
  frontend timeout wiring.

## Phase 6 — Subsystem tests

200 tests across `dashboard.py`, `workspace.py`, and dependent Omega/Sigma/frontend-structural
suites: **200 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`. Given Mission 012's own deadlock incident, every test run this mission
was wrapped in a hard shell-level `timeout` command as an extra safety net, in addition to each
individual test's own internal `asyncio.wait_for` bounds.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk, no hang. **PASS.**
