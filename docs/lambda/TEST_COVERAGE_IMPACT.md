# Test Coverage Impact — Program Lambda, Certification 003A

## Areas exercised by this sprint's own investigation and fix

- **`tests/test_doc_pitanje_api.py`** (6 tests) — re-verified in full, both standalone and combined, both
  before and after the fix.
- **`tests/test_uploaded_doc_api.py`** (8 tests) — re-verified in full, both standalone and combined, both
  before and after the fix.
- **`tests/test_akcija2_faza4_2026_07_24.py`** (23 tests, 7 previously failing) — re-verified in full,
  standalone (always passed) and combined with the fix (all 23 now pass in every combination tested).
- **`tests/test_akcija1_faza4_bugfixes_2026_07_24.py`**, **`tests/test_a6_fixes.py`** — included in the
  combined-file verification run as the immediate alphabetical neighbors of the affected files, to rule out
  any adjacent-collection-order interaction. Both unaffected, both passing before and after.
- **Pytest's own collection/execution lifecycle** — read directly from the installed `pytest==9.0.3` source
  (`_pytest/main.py`, `_pytest/python.py`) to confirm the actual hook-firing model, not assumed from
  documentation alone.
- **`routers/dokument.py::dokument_pitanje`** — read directly to confirm its `main` import pattern (local,
  function-scoped) is what makes the fix safe for its own tests.

## Areas NOT touched, and why that's correct for this sprint

Per this mission's explicit charter (Regression Recovery, not feature development): **no production code was
touched anywhere in this sprint.** `main.py`, `api.py`, `routers/dokument.py`, and every other application
file are byte-for-byte unchanged from the end of Certification 003. This sprint's entire diff is 2 test
files, moving 5 existing lines from module scope into a `setup_module` function each — nothing else.

- **The other ~10 test files that touch `sys.modules["main"]`** (`test_c6_schema_hardening.py`,
  `test_c7a_praksa.py`, `test_commit4_p0.py`, `test_guard_commit2/3.py`, `test_guard_v2.py`,
  `test_hallucination_guard.py`, `test_q5_fix.py`, `tests/unit/test_doc_type_detection.py`) were
  independently re-verified (twice, by 2 separate investigations) to already use a correct pattern and were
  never part of the failure — left untouched, correctly.
- **The remaining ~2,970 tests in the full suite** were exercised only as part of the full-suite regression
  run (Phase 6), not individually re-verified beyond that — appropriate given this sprint's own scope was one
  narrowly-bounded, fully-explained failure cluster, not a general audit.
- **`LAMBDA003-AUTH-001`/`LAMBDA003-EVT-001`/`LAMBDA003-RLS-001`/`LAMBDA003-AUTH-002`** (architectural debt/
  accepted risk items named in Certification 003) are unrelated to this sprint's own regression-recovery
  scope and were not revisited here — they remain exactly as characterized in Certification 003's own
  deliverables.

## Coverage gap, honestly noted

This sprint's own fix relies on `setup_module`/`teardown_module` firing correctly under pytest's default
collection/execution model. It was verified under: full-suite run, 2-file isolated runs, a 5-file combined
run, and one `-k`-filtered single-test run. It was **not** verified under `pytest-xdist` (parallel execution,
not installed in this environment) or `pytest --lf`/`--ff` (last-failed/failed-first re-run modes) — noting
this explicitly rather than claiming coverage that wasn't actually exercised. Given neither xdist nor these
rerun modes are configured as this project's standing CI invocation (per `pytest.ini`'s own minimal
`testpaths = tests` config, no parallelization plugin listed), this is a reasonable, disclosed limitation, not
a hidden one.
