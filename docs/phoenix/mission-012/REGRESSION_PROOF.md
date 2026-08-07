# Mission 012 — Regression Proof

## Claim 1 — cooldown claim is correct under both contention and normal use

- `test_cooldown_claim_first_call_of_day_succeeds` and
  `test_cooldown_claim_concurrent_calls_only_one_wins` prove the claim/race behavior directly.
- `test_cooldown_claim_succeeds_again_after_window_elapses` proves this isn't a permanent lock —
  a genuinely later call still claims successfully.
- `test_consume_raises_429_when_cooldown_claim_fails` proves `consume()`'s own error response
  shape (429, `COOLDOWN` code) is unchanged from the caller's point of view.
- No pre-existing test exercised a truthy `cooldown_seconds` through `consume()` before this
  mission (confirmed by grep across `tests/`) — this is genuinely new coverage, not a
  modification of prior behavior.

## Claim 2 — hronologija validation/insert changes don't lose valid data

- `test_validate_hronologija_datum_iso_accepts_valid_date` proves a well-formed date passes
  through unchanged.
- `test_validate_hronologija_datum_iso_rejects_hallucinated_date` and
  `..._handles_none_and_placeholders` prove only genuinely bad values are dropped.
- `test_insert_hronologija_rows_persists_valid_rows_despite_one_bad_row` proves 2 of 3 rows
  (the good ones) still persist when 1 fails — the exact fix for the "one bad row kills the
  batch" defect.

## Claim 3 — the genome coalescing fix doesn't touch the manual endpoint's own guard

- `test_refresh_case_dna_endpoint_guard_unaffected_by_this_fix` proves `refresh_case_dna`'s
  own BLACKSWAN-HIGH-003 reject-if-busy guard (a plain-set `in`/`.add()`/`.discard()` usage)
  still works exactly as before — this fix added a SEPARATE dict, never touching that set's
  type or the endpoint's own code.
- `test_genome_refresh_inflight_state_fully_cleaned_up_after_coalesce` proves no state leaks
  after 2 concurrent callers finish — the next trigger for the same case starts clean.

## Claim 4 — cio_run's claim doesn't break its own "always regenerate" purpose

- `test_cio_run_concurrent_calls_charge_only_once` proves the race is closed.
- `test_cio_run_still_charges_on_a_genuinely_separate_call` proves a call outside the 5s window
  still works normally — `/run` remains usable repeatedly, not accidentally rate-limited to once
  per day like `/daily`.

## Subsystem regression

365 tests across `shared/usage.py`, `api.py`'s upload endpoint, `case_dna.py`, `cio.py`, and
dependent certification suites: **365 passed, 0 failed** — zero pre-existing tests needed any
modification (this mission's changes were purely additive to previously-untested or
newly-separated code paths).

## Full-suite regression

See `TEST_RESULTS.md` for the exact before/after counts.
