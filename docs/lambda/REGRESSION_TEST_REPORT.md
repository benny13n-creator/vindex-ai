# Regression Test Report — Program Lambda, Certification 002

## Full suite result

**2,971 passed, 1 skipped, 0 failed** (baseline entering this sprint, end of Lambda Master Sprint 001:
2,947 passed, 1 skipped, 0 failed). **+24 exact delta, zero regressions.**

## New test files (24 new tests)

| File | Tests | Covers |
|---|---|---|
| `tests/test_lambda002_ownership_idor_fixes.py` | 12 | `smart_intake.py::correct_entity`, `api.py::predmet_confirm_links`, `zadaci.py::obrisi_zadatak` admin branch, `workflow.py::pokreni_workflow` template visibility, `billing.py::billing_entry_create`/`timer_start`, `copilot.py::_handle_akcija_povezi_klijenta`, `intake.py::intake_kreiraj` — each with a "rejects foreign resource" test AND a "legitimate owner still works" no-regression test |
| `tests/test_lambda002_multi_agent_context_leak.py` | 4 | `multi_agent.py::run_agent` billing/deadline context gating — proves the leak is closed by inspecting the actual prompt string sent to GPT (not just absence of an exception), plus 2 no-regression tests for the legitimate-owner path |
| `tests/test_lambda002_rpc_ownership_lockdown.py` | 4 | Static guard on `migrations/102_lambda002_rpc_ownership_lockdown.sql` — proves the migration file exists and contains the exact `REVOKE ... FROM PUBLIC/anon/authenticated` + `GRANT ... TO service_role` statement for every one of the 5 flagged RPC functions, so a future edit can't silently drop the fix before the founder applies it |
| `tests/test_lambda002_profiles_column_lockdown.py` | 4 | Static guard on `migrations/103_lambda002_profiles_column_lockdown.sql` (added on the post-commit manual re-review pass — see `RLS_CERTIFICATION.md`) — proves the migration revokes blanket `UPDATE` from `authenticated`/`anon`, re-grants only the `full_name` column, never grants `is_pro`/`plan`/`trial_kraj`/`onboarding_done`, and keeps `service_role` unaffected |

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

- **`migrations/102_lambda002_rpc_ownership_lockdown.sql` and `103_lambda002_profiles_column_lockdown.sql`
  themselves**: the new tests guard each migration FILE's content (proves the fix is written correctly and
  can't silently regress), but cannot prove either fix is EFFECTIVE against a live Supabase instance, since
  neither migration has been applied yet. Both migrations' own trailing comments instruct the founder to
  manually verify a `permission-denied` response after running them — this is a live-environment check, not
  something a unit test in this repo can perform. `RLS_CERTIFICATION.md` names running both as the sprint's
  single highest-priority outstanding action.
- **Storage bucket policies**: no test can verify Supabase Dashboard-configured policies from this repo
  (see `STORAGE_SECURITY_REPORT.md`).
- **Race conditions under real concurrent load**: reasoned through at the code level
  (`EVENT_OWNERSHIP_REPORT.md`), not exercised with actual parallel requests, since no running deployment
  exists in this environment.

---

## Addendum — Program Lambda, Certification 003 (2026-08-06)

**Full suite: 2,984 passed, 1 skipped, 7 failed, 22 warnings.**

### The 7 failures: pre-existing, root-caused, confirmed unrelated to this sprint

All 7 failures are confined to `tests/test_akcija2_faza4_2026_07_24.py` (contract-analysis Map-Reduce/batch-
segmentation tests — a feature this sprint never touched). Root cause: `tests/test_doc_pitanje_api.py` and
`tests/test_uploaded_doc_api.py` both install a `MagicMock()` into `sys.modules["main"]` at **collection
time** (module-level `sys.modules.setdefault("main", _mock_main)`, executed the moment pytest imports the
file to discover its tests — before ANY test in the whole session runs, since pytest collects all files
before executing any). Neither file ever restored the real module afterward. Since pytest's collection phase
runs for every file before execution begins for any of them, this mock is already installed in `sys.modules`
by the time `test_akcija2_faza4_2026_07_24.py`'s own tests execute (which happens earlier, alphabetically,
than `test_doc_pitanje_api.py`'s own test execution) — so those tests import what they believe is the real
`main` module and get the mock instead, and `main._batch_segments_za_map(...)` silently returns a
`MagicMock()` instead of running the real function.

**Proven unrelated to this sprint's changes**:
- The affected file passes 23/23 when run in isolation (confirms the bug is purely an inter-file collection-
  order artifact, not a logic defect in the affected tests or any code this sprint touched).
- This sprint's own code changes never touch `main.py::_batch_segments_za_map`, the contract-analysis
  Map-Reduce pipeline, or `routers/dokument.py`'s analysis code.
- None of this sprint's 19 new test files execute before `test_akcija2_faza4_2026_07_24.py` alphabetically
  (all are named `test_lambda003_*`, sorting well after `test_akcija*`), so they cannot be the source of the
  pollution.
- The exact hazard is independently self-documented as a KNOWN, pre-existing risk in
  `tests/test_ask_agent_gate_bias.py`'s own docstring (predates this sprint entirely), describing the same
  `sys.modules["main"]` replacement mechanism.

### Partial mitigation applied, full fix out of scope

Added a `teardown_module` hook to both `test_doc_pitanje_api.py` and `test_uploaded_doc_api.py` that restores
`sys.modules` to its pre-file state after each file's own tests finish executing — this is real, verified
protection for any test that executes AFTER these two files in the session, but does **not** retroactively
fix `test_akcija2_faza4_2026_07_24.py`, whose tests execute earlier (alphabetically) than the point where
teardown fires, while the pollution itself happens at collection time, before any execution begins. A
complete fix would require restructuring these 2 files' own mocking strategy (patching `api.py`'s bound
reference to `main` instead of replacing the module in `sys.modules` globally) — a larger, out-of-scope change
to unrelated test infrastructure, not a security finding, and not attempted here per this sprint's own
discipline against unrelated refactoring. Tracked as `LAMBDA003-TEST-001` (test-infrastructure debt, not a
security or product finding) for a future cleanup pass.

### This sprint's own 19 new tests: all pass, individually and combined

`tests/test_lambda003_ask_agent_cache_isolation.py` (8), `tests/test_lambda003_klijenti_role_fail_closed.py`
(5), `tests/test_lambda003_hoisted_ownership_checks.py` (6) — all new files, 19 tests, 19 passing. Plus 2 new
tests added to the pre-existing `tests/test_tau002_case_context.py` (now 30/30). Every file this sprint
modified (`main.py`, `klijenti/router.py`, `shared/case_context.py`, `routers/case_commander.py`,
`routers/digital_twin.py`, `routers/copilot.py`) was individually re-verified green both alone and combined
with its full surrounding test suite (`test_ask_agent_gate_bias.py`, `test_copilot_povezi_klijenta.py`,
`test_copilot_ambient.py`, `test_celina3_copilot_multiagent_2026_07_24.py`,
`test_synapse_copilot_genome_context.py`, `test_tau007_case_commander_consolidation.py`,
`test_sigma_sprint005_commander_consolidation.py`, `test_celina2_predictor_commander_2026_07_24.py`,
`test_lambda001_beta_readiness_fixes.py`'s digital-twin tests) before the full-suite run — zero regressions
in any of them.
