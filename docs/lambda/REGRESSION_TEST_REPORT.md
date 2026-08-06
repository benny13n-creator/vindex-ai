# Regression Test Report — Program Lambda, Certification 002

## Full suite result

**2,967 passed, 1 skipped, 0 failed** (baseline entering this sprint, end of Lambda Master Sprint 001:
2,947 passed, 1 skipped, 0 failed). **+20 exact delta, zero regressions.**

## New test files (20 new tests)

| File | Tests | Covers |
|---|---|---|
| `tests/test_lambda002_ownership_idor_fixes.py` | 12 | `smart_intake.py::correct_entity`, `api.py::predmet_confirm_links`, `zadaci.py::obrisi_zadatak` admin branch, `workflow.py::pokreni_workflow` template visibility, `billing.py::billing_entry_create`/`timer_start`, `copilot.py::_handle_akcija_povezi_klijenta`, `intake.py::intake_kreiraj` — each with a "rejects foreign resource" test AND a "legitimate owner still works" no-regression test |
| `tests/test_lambda002_multi_agent_context_leak.py` | 4 | `multi_agent.py::run_agent` billing/deadline context gating — proves the leak is closed by inspecting the actual prompt string sent to GPT (not just absence of an exception), plus 2 no-regression tests for the legitimate-owner path |
| `tests/test_lambda002_rpc_ownership_lockdown.py` | 4 | Static guard on `migrations/102_lambda002_rpc_ownership_lockdown.sql` — proves the migration file exists and contains the exact `REVOKE ... FROM PUBLIC/anon/authenticated` + `GRANT ... TO service_role` statement for every one of the 5 flagged RPC functions, so a future edit can't silently drop the fix before the founder applies it |

## Pre-existing tests updated (not counted in the delta — same test count, adjusted mocks)

| File | Change | Why |
|---|---|---|
| `tests/test_sprint004_review_resolve.py` | Added a `_get_supa` mock with the 3-table ownership-chain response shape | A sibling fork's fix to `smart_intake.py::correct_entity` added 3 new DB queries; the old test had no Supabase mock at all (the endpoint previously made zero DB calls), so it started hitting a real (unreachable in test) network call and failing with a connection/parsing error — not a logic regression, a test-infrastructure gap the fix exposed |
| `tests/test_mission001_predmet_klijenti.py` | Added a `klijenti` table mock returning the owned client id | `api.py::predmet_confirm_links`'s new ownership pre-check added a `klijenti` query this pre-existing test's mock didn't route; without it the mock would return a `MagicMock()` truthy-by-default object instead of real data, which happened to still pass but for the wrong reason — fixed to route it explicitly |
| `tests/test_billing_timer_race.py` | Added a `predmeti` ownership-chain mock (`_owned_predmet_chain()`) ahead of every `timer_sessions` call | `billing.py::timer_start`'s new ownership pre-check runs before the existing TOCTOU-race logic this file tests; needed a mock for the new query without changing what the race tests themselves assert |

## Verification method

Every new test follows the same two-sided pattern established across this whole engagement: one test proves
the ATTACK fails cleanly (404, silently-skipped link, empty prompt content — never a 500 or a silent success),
and a paired test proves the LEGITIMATE path still works exactly as before. This catches both "fix does
nothing" (attack test would fail) and "fix breaks the real feature" (owner test would fail) in the same pass.

For `multi_agent.py` specifically, the test asserts on the ACTUAL STRING passed to the mocked GPT call
(`user_msg`) rather than just checking the HTTP response shape — this is the same discipline
`test_tau002_case_context.py`'s own excerpt-content assertions established in a prior sprint (Lambda 001),
after finding that a 27-test suite could look thorough while never actually asserting on the field that
mattered. The same blind spot was checked for here and avoided.

## What is NOT covered by an automated test

- **`migrations/102_lambda002_rpc_ownership_lockdown.sql` itself**: the new test guards the migration FILE's
  content (proves the fix is written correctly and can't silently regress), but cannot prove the fix is
  EFFECTIVE against a live Supabase instance, since the migration has not been applied yet. The migration's
  own trailing comment instructs the founder to manually verify a `permission-denied` response after running
  it — this is a live-environment check, not something a unit test in this repo can perform.
  `RLS_CERTIFICATION.md` names this as the sprint's single highest-priority outstanding action.
- **Storage bucket policies**: no test can verify Supabase Dashboard-configured policies from this repo
  (see `STORAGE_SECURITY_REPORT.md`).
- **Race conditions under real concurrent load**: reasoned through at the code level
  (`EVENT_OWNERSHIP_REPORT.md`), not exercised with actual parallel requests, since no running deployment
  exists in this environment.
