# Mission 002 — Regression Proof

## New tests (`tests/test_phoenix_mission_002_concurrency_guards.py`)

| Test | Proves |
|---|---|
| `test_pred_inline_edit_sends_if_updated_at` | The frontend PATCH body includes `if_updated_at` and a `409` handler |
| `test_pred_inline_edit_refreshes_cached_updated_at_on_success` | The cache is refreshed from the server's response, preventing a spurious 2nd-edit 409 |
| `test_update_predmet_returns_new_updated_at_for_frontend_cache` | The backend actually returns the field the frontend depends on |
| `test_learning_outcome_guards_close_against_concurrent_reopen` | A lost race produces a safe no-op (0 rows updated) with no audit entry written for a close that didn't happen |
| `test_learning_close_write_uses_neq_guard_and_audit_trail` | The guard clause and audit-insert call are both present in the right order |
| `test_azuriraj_status_rejects_stale_write_with_409` | A stale `if_updated_at` on an existing, owned task produces a clean 409, not a silent overwrite |
| `test_zadaci_frontend_sends_if_updated_at_from_cache` | The frontend caller actually sends the precondition from its own cache |

## Original-scenario rerun

`test_azuriraj_status_rejects_stale_write_with_409` directly reproduces the debt item's own
narrative: "one marks a task 'završeno'; the other, working off a stale render, marks the same
task 'otkazano' a moment later" — the second (stale) write now gets a clean 409 instead of
silently winning.

## Pre-existing test corrections (not weakened)

`test_sentinel_reliability_fixes.py::test_update_predmet_without_if_updated_at_behaves_exactly_as_before`
and `::test_update_predmet_with_matching_if_updated_at_succeeds` asserted an exact
`{"ok": True}` dict equality. `update_predmet`'s intentional, additive new `updated_at` field
broke that exact match — both tests updated to assert `{"ok": True, "updated_at": None}`
(`None` because their own mock's row has no `updated_at` column, correctly reflecting what the
code actually does with that mock's data, not a loosened assertion).
