# Program Phoenix — Mission 011: Billing & Reference Integrity

**Date**: 2026-08-08
**Debt items addressed**: `LIVINGSYS-DEBT-054` (fully), `LIVINGSYS-DEBT-044` (fully).

## Why these 2 were grouped

Both are "an entity references a `predmet_id`/sequence position that was never validated or
protected against a concurrent write" — same architectural category (reference/sequence
integrity under concurrency), same fix shape available (validation gate / DB constraint +
retry-on-conflict), and both explicitly named as deferred-pending-decision items in the debt
register.

## Phase 1 — Reproduction

- `-054`: confirmed `routers/billing.py::faktura_create` writes `body.predmet_id` straight into
  the `fakture` row with zero check that the fetched `billing_entries` rows (`entries`, keyed by
  `body.entry_ids`) actually carry that same `predmet_id`. A user's own entries from ANY of
  their cases can be invoiced under an arbitrary `predmet_id`.
- `-044`: confirmed `routers/smart_intake.py`'s finalize loop fetches the next `redni_broj` via
  a plain `SELECT MAX+1` once before its document loop, then increments only in-process. This
  app runs 4 gunicorn workers (`gunicorn.conf.py`) — 2 concurrent finalize calls to the same
  `predmet_id` landing on different workers can compute the identical next number.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

- `-054`: `faktura_create` now rejects (400) if any fetched entry's `predmet_id` doesn't match
  `body.predmet_id`, before the `already_billed` check.
- `-044`: new migration 106 (`CREATE UNIQUE INDEX ... ON predmet_dokumenti (predmet_id,
  redni_broj)`, drafted, not applied — founder runs it per standing convention) plus a
  retry-on-conflict wrapper around `smart_intake.py`'s existing 6-variant fallback insert ladder:
  a `23505`/"duplicate key" error whose text mentions `redni` bumps `_sledeci_redni` and retries
  the whole ladder (bounded 3 attempts), mirroring `billing.py`'s own established
  `LAMBDA008-CONC-003` idiom exactly. An application-level lock was explicitly rejected — it
  would not protect against the actual cross-worker-process race this deployment can produce.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_011_billing_reference_integrity.py`, 5 tests. 3
pre-existing tests corrected (2 in `tests/test_lambda008_certification.py`, 1 in
`tests/test_blackswan_mission001.py`) — their mocked `billing_entries` rows gained the
`predmet_id` field `faktura_create` now requires; no assertion weakened.

## Phase 5 — Original scenario rerun

- `test_redni_broj_conflict_retries_with_next_number_and_succeeds` directly reproduces the
  debt item's exact scenario: the DB rejects the first candidate number (another concurrent
  finalize call already claimed it), and the retry picks the next number and succeeds.
- `test_faktura_create_rejects_entry_from_different_case` directly reproduces the debt item's
  exact scenario: one of 2 entries belongs to a different case than the invoice's own
  `predmet_id`.

## Phase 6 — Subsystem tests

175 tests across `billing.py`, `smart_intake.py` finalize (3 test files), and dependent
certification suites: **175 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
