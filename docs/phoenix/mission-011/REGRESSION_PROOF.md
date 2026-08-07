# Mission 011 — Regression Proof

## Claim 1 — the predmet_id gate rejects mismatches and passes matches

- `test_faktura_create_rejects_entry_from_different_case` proves a 2-entry set where 1 entry
  belongs to a different case than the invoice's `predmet_id` is rejected with 400 before any
  `fakture` row is written.
- `test_faktura_create_succeeds_when_all_entries_match_predmet_id` proves the normal, correct
  case (all entries genuinely belong to the invoiced case) is completely unaffected — same
  success path, same response shape as before this mission.
- The 3 pre-existing tests exercising `faktura_create`'s OTHER behavior (invoice-number conflict
  retry, orphan-invoice rollback) continue to pass with the `predmet_id` field added to their
  mocks — proving this gate doesn't interfere with either of those pre-existing guarantees.

## Claim 2 — the redni_broj retry only fires on a genuine sequence conflict

- `test_redni_broj_conflict_retries_with_next_number_and_succeeds` proves a conflict on the
  first candidate number is caught and the retry with the next number succeeds — the flagship
  reproduction.
- `test_redni_broj_conflict_exhausts_retries_without_crashing` proves a pathological
  always-conflicting sequence fails that one document gracefully after exactly 3 bounded
  attempts, never looping forever or crashing the whole finalize call.
- `test_non_conflict_insert_failure_does_not_trigger_redni_retry` proves a non-conflict error
  (schema mismatch, connection blip) is NOT mistaken for a redni_broj race — it exhausts the
  existing 6-variant fallback ladder exactly once (6 attempts total) and stops, matching
  pre-mission behavior exactly.
- The pre-existing `test_one_document_insert_failure_does_not_lose_or_block_sibling` (in
  `tests/test_sprint006_finalize_assimilation.py`, untouched, still passing) independently
  confirms the same non-conflict-failure-isolation guarantee at the multi-document level: one
  document's failure never blocks its sibling.

## Subsystem regression

175 tests across `billing.py`, `smart_intake.py` finalize (`test_sprint006_finalize_
assimilation.py`, `test_ztc_scenario_b_attach.py`), and dependent certification suites
(`test_lambda008_certification.py`, `test_blackswan_mission001.py`, `test_living_system_
fixes.py`): **175 passed, 0 failed** — only the 3 documented mock-data additions needed, zero
assertions weakened.

## Full-suite regression

See `TEST_RESULTS.md` for the exact before/after counts.
