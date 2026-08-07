# Program Phoenix — Mission 005: Evidence & Event Idempotency

**Date**: 2026-08-07
**Debt items closed**: `LIVINGSYS-DEBT-010`, `LIVINGSYS-DEBT-043`.

## Why these 2 were grouped

Same root-cause family (per the debt register's own note on `-043`: "Same root-cause family as
`-010`") — both are HTTP endpoints with no protection against a client retry producing a
duplicate durable event / duplicate physical row.

## Phase 1 — Reproduction

- `-010`: confirmed `routers/smart_intake.py::resolve_job_review`/`reject_job_review` both call
  `emit_durable(...)` unconditionally, regardless of `result["review_resolved_now"]` — even
  though `resolve_review()`/`reject_review()` themselves are already idempotent
  (`.is_("resolved_at","null")` guard), a genuine retry still fires a brand-new durable event,
  triggering a full new consequence chain.
- `-043`: confirmed `routers/rocista.py::kreiraj_rociste` does a plain unconditional
  `.insert(payload)` with no idempotency check of any kind, and unconditionally emits
  `ROCISTE_ZAKAZANO` after.

## Phase 2 — Root cause

- `-010`: the endpoint's own docstring already correctly reasons that the underlying resolve/
  reject actions are idempotent — but that idempotency was never propagated to the SEPARATE
  decision of whether to emit a new durable event, treating "did the action run" and "should a
  new event fire" as the same question when they're not.
- `-043`: `rocista` (unlike `intake_jobs`, which has a real `idempotency_key` column) was never
  given any idempotency infrastructure — no column, no check-before-write.

## Phase 3 — Fix

- `-010`: both `emit_durable(...)` calls are now gated on `result["review_resolved_now"]` —
  the exact signal that already exists to distinguish "this call changed something" from "this
  call was a no-op retry."
- `-043`: before inserting, checks for an identical `(predmet_id, sud, datum, vreme)` row
  created in the last 30 seconds for the same user — reusing only existing columns (no
  migration). If found, returns the existing row and skips both the insert and the event
  emission. A 2nd real hearing on the same court/date/time for the same case is not a realistic
  scenario this window would ever wrongly collapse.

No new algorithm, no migration.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_005_evidence_event_idempotency.py`, 5 tests.

## Phase 5 — Original scenario rerun

Each test directly reproduces its finding's own scenario (a genuine retry vs. a genuine new
action) and confirms the correct branch fires.

## Phase 6 — Subsystem tests

168 tests across 7 files touching `smart_intake.py` review endpoints and `rocista.py`:
**168 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
