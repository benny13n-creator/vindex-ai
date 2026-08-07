# Mission 005 — Regression Proof

## New tests (`tests/test_phoenix_mission_005_evidence_event_idempotency.py`)

| Test | Proves |
|---|---|
| `test_resolve_job_review_skips_event_emission_on_retry` | `review_resolved_now=False` → zero event emissions |
| `test_resolve_job_review_emits_event_on_genuine_resolution` | `review_resolved_now=True` → event still fires normally |
| `test_reject_job_review_skips_event_emission_on_retry` | Same guard for the reject path |
| `test_kreiraj_rociste_returns_existing_row_on_immediate_retry` | An identical recent row → no new insert, no new event, existing row returned |
| `test_kreiraj_rociste_creates_new_row_when_no_recent_duplicate` | No matching recent row → normal creation + event, unaffected |

## Original-scenario rerun

Each pair of tests (skip-on-retry / proceed-on-genuine-action) directly reproduces both halves
of the debt items' own scenarios, confirming neither over-corrects (blocking legitimate new
actions) nor under-corrects (still allowing the duplicate).

## No pre-existing test corrections needed this mission

`test_kreiraj_rociste_success` (pre-existing) passed unmodified — its generic MagicMock chain's
auto-configured `__iter__` (returns `iter([])` by default) safely absorbs the new duplicate-
check query as "no existing rows found," exercising the normal creation path exactly as before.
