# Program Phoenix — Mission 002: Concurrency Guards Quick Wins

**Date**: 2026-08-07
**Debt items closed**: `LIVINGSYS-DEBT-007`, `LIVINGSYS-DEBT-033`, `LIVINGSYS-DEBT-034`.

## Why these 3 were grouped

Same architecture: each is a case-editing surface with either a declared-but-unenforced or
entirely-absent optimistic-concurrency guard, and each is closed by the exact same pattern
already proven correct in this codebase (`api.py::update_predmet`'s own `if_updated_at`
precondition, `routers/predmeti_close.py`'s own `.neq("status", ...)` write-time guard).

## Phase 1 — Reproduction

- `-007`: `api.py::update_predmet` genuinely supports `if_updated_at` (added by Program Lambda
  Certification 004), but `static/vindex.js::_predInlineEdit` (its only live caller) never sent
  it — confirmed via direct code read of `doSave()`'s PATCH body construction.
- `-033`: `routers/learning.py`'s case-outcome endpoint's `predmeti` status update had no
  `.neq(...)` guard and wrote no `predmet_hronologija` audit entry, unlike its 2 siblings in
  `predmeti_close.py`.
- `-034`: `routers/zadaci.py::azuriraj_status` had zero concurrency guard of any kind —
  confirmed via direct code read (`.update(...).eq(...).or_(...).execute()`, no precondition).

## Phase 2 — Root cause

All 3 are instances of "declared control ≠ enforced control" — a correct pattern exists
somewhere in the codebase but was never propagated to every relevant call site. `-007`'s
backend half was already correct; only the frontend caller needed wiring. `-033`/`-034` needed
the guard built from scratch, using the exact same shape as their own proven siblings.

## Phase 3 — Fix

- **`-007`**: `_predInlineEdit`'s `doSave()` now reads `window._predFull.predmet.updated_at`
  (the last value this tab actually saw) and sends it as `if_updated_at`; handles a `409`
  response with a clear message and reverts the visibly-edited span. `api.py::update_predmet`
  now additionally returns the row's new `updated_at` in its response so the frontend can keep
  its cached precondition fresh for the *next* edit — without this, a second field edited
  moments after the first would have spuriously 409'd against an already-stale cached value.
- **`-033`**: `learning.py`'s status update now carries `.neq("status", novi_status)`, and on a
  successful (non-raced) close, writes a `predmet_hronologija` entry — matching the audit-trail
  discipline `predmeti_close.py`'s own writer already has. Kept non-fatal-on-conflict (logged,
  not raised), consistent with this endpoint's own purpose (recording a learning outcome, not
  primarily closing the case).
- **`-034`**: `zadaci.py`'s `StatusUpdate` model gained an optional `if_updated_at` field (same
  opt-in, backward-compatible shape as `update_predmet`'s own). `azuriraj_status` applies it as
  a precondition when present, disambiguates a 404 (task not found/not yours) from a 409 (a
  concurrent edit won the race) via the same existence-recheck pattern `update_predmet` already
  uses. Frontend: added a simple `_zadaciCacheById` id→row cache (populated at the single
  `_zadaciRenderBoard` choke point both `zadaci_load`/`zadaci_g_load` funnel through), and wired
  `zadaci_setStatus` to read `updated_at` from it and send `if_updated_at`.

No new algorithm anywhere — every guard reuses the exact `if_updated_at`/`.neq()` shape already
proven in this codebase.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_002_concurrency_guards.py`, 7 tests.

Two pre-existing tests (`test_update_predmet_without_if_updated_at_behaves_exactly_as_before`,
`test_update_predmet_with_matching_if_updated_at_succeeds`) broke against an exact-dict-equality
assertion after `update_predmet`'s additive `updated_at` field was added — both corrected to
include the new field (their mock's row has no `updated_at` column, so the correct expected
value is `None`), not weakened or removed.

## Phase 5 — Original scenario rerun

Each new behavioral test directly reproduces its finding's scenario (a stale-precondition write
racing a fresher one) and confirms the previously-silent clobber now surfaces as a clean 409.

## Phase 6 — Subsystem tests

`test_sentinel_reliability_fixes.py` + `test_xss_sanitization_sweep.py` +
`test_celina4_tech_debt_2026_07_24.py`: 89 passed (2 corrected, not weakened — see above).
`test_beta_lockdown_zadaci_predmet_idor.py` + `test_lambda002_ownership_idor_fixes.py` +
`test_lambda003_klijenti_role_fail_closed.py` + `test_nexus_zadaci_ai_grounding.py` +
`test_singular_intelligence_fixes.py` + `test_zadaci.py`: 48 passed, 0 failed.

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced (2 pre-existing tests correctly updated for an intentional additive
API change, not silently broken), no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
