# Mission 011 — Test Results

## New tests: `tests/test_phoenix_mission_011_billing_reference_integrity.py`

| Test | Verifies |
|---|---|
| `test_faktura_create_rejects_entry_from_different_case` | 400 when any entry's case doesn't match |
| `test_faktura_create_succeeds_when_all_entries_match_predmet_id` | Normal case unaffected |
| `test_redni_broj_conflict_retries_with_next_number_and_succeeds` | **Flagship**: conflict → retry → success |
| `test_redni_broj_conflict_exhausts_retries_without_crashing` | Bounded 3 attempts, graceful failure |
| `test_non_conflict_insert_failure_does_not_trigger_redni_retry` | Non-conflict errors don't loop |

**Result: 5 passed, 0 failed.**

## Corrected pre-existing tests

2 in `tests/test_lambda008_certification.py`, 1 in `tests/test_blackswan_mission001.py` — mocked
`billing_entries` rows gained `predmet_id` matching their own `FakturaReq`; no assertion
weakened.

## Subsystem tests (billing/smart_intake finalize/dependent certifications)

**Result: 175 passed, 0 failed.**

## Full repository regression suite

| | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline (post-Mission 010) | 3,284 | 1 | 0 |
| Post-Mission 011 | 3,289 | 1 | 0 |

Net +5 (exactly the new mission tests). **Zero regressions.** (357.63s)

## Red Team self-check

1. **`-054`'s gate — could it ever reject a genuinely valid invoice?** No — it only compares
   each entry's own `predmet_id` (already validated as real and owned at entry-creation time by
   `billing_entry_create`) against the invoice's claimed `predmet_id`; a matching set always
   passes, proven by `test_faktura_create_succeeds_when_all_entries_match_predmet_id`.
2. **`-054`'s gate — bypassable via a different `entry_ids` ordering or a partial mismatch?** No
   — the check iterates ALL fetched entries unconditionally; a single mismatched entry among N
   still triggers rejection (proven with a 2-entry set, 1 matching, 1 not).
3. **`-044`'s retry — could it ever assign the SAME redni_broj to 2 different documents in one
   finalize call?** No — `_sledeci_redni` is a single local variable incremented after every
   attempt (success, non-conflict failure, or conflict) within the SAME outer per-document loop
   this file already serialized (Zero-Touch Case investigation's own prior fix); this mission
   only adds cross-REQUEST protection via the DB constraint, it doesn't change the existing
   within-request sequencing at all.
4. **`-044`'s retry — infinite loop risk under sustained contention?** No — bounded to 3 attempts
   per document, proven by `test_redni_broj_conflict_exhausts_retries_without_crashing`; a
   persisting conflict degrades to "this one document isn't linked" (visible, reportable) rather
   than hanging the request.
5. **`-044`'s conflict-detection string match — could it misfire on an unrelated constraint
   violation?** The check requires BOTH a duplicate-key signal (`"23505"` or `"duplicate key"`)
   AND the substring `"redni"` in the error text — the migration's own constraint is named
   `predmet_dokumenti_predmet_redni_unique`, so a genuinely unrelated unique-violation on this
   table (none currently exist) would not match and would instead fall through to the existing
   non-conflict debug-log-and-continue path, never silently misclassified as a redni race.

No break found. **Mission 011 STOP GATE: PASS.**
