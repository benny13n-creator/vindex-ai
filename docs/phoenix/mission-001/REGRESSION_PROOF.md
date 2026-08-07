# Mission 001 — Regression Proof

## New tests (`tests/test_phoenix_mission_001_archived_case_visibility.py`)

| Test | Proves |
|---|---|
| `test_guardian_scan_excludes_deadline_on_archived_case` | An archived case's deadline (`r2`) is excluded from `guardian_scan`'s scan list while an active case's (`r1`) is retained |
| `test_matter_intel_rocista_query_filters_zakazano_status` | The `rocista` query in `get_matter_intel` carries `.eq("status", "zakazano")` (structural — the mechanism itself, not just an outcome) |
| `test_aggr_events_excludes_archived_case_hearing_and_deadline` | Both a hearing and a deadline for an archived case are excluded from `_aggr_events`'s output while the active case's own hearing+deadline are retained (2 of 4 input rows survive) |
| `test_worklist_excludes_archived_case` | `get_worklist`'s `predmeti` fetch only ever returns/passes the active case's id downstream to `_fetch_open_actions` — asserted via the fake's own `assert predmet_ids == ["pred-active"]` |

All 4 fail against the pre-fix code (verified during development — each test's assertion is
exactly the condition the original finding violated) and pass against the post-fix code.

## Original-scenario rerun

Each test's fixture directly encodes the original reproduction scenario from the source Wave
report: an active case and an archived case, each carrying the relevant hearing/deadline/action,
in the same query result set — exactly the "same day, same session, two cases" framing the
original Living System findings used.

## Pre-existing test interaction

`tests/test_rocista_kalendar.py::test_aggr_events_predmet_name_fallback` broke against the first
implementation draft (a blanket "not in active set" filter) and was NOT weakened — the fix
itself was corrected to respect the pre-existing test's own proven requirement (fail open on an
unresolvable `predmet_id`). Final state: this test passes unmodified.
