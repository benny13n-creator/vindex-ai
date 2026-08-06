# Fix Justification — Program Lambda, Certification 003A

## The fix

In both `tests/test_doc_pitanje_api.py` and `tests/test_uploaded_doc_api.py`: moved the 5
`sys.modules.setdefault(...)` calls (for `main`, `templates.podnesci`, `knowledge.vks_standards`, `pinecone`,
`supabase`) and their preceding `_PRE_EXISTING_MODULES` capture out of bare module-level code and into a
`setup_module(module)` function — the pytest/unittest-recognized xunit-style hook that runs immediately
before that file's own **first test executes**, pairing naturally with the `teardown_module` hook
Certification 003 already added (which fires after that file's own last test). Nothing else in either file
changed — no test function, no fixture, no import statement, no assertion.

## Why this is the correct fix, not a workaround

The root cause (`ROOT_CAUSE_ANALYSIS.md`) is a **lifecycle-phase mismatch**: the mutation happened at
collection time (too early — before any test in the session runs) and the only prior cleanup
(`teardown_module`) happened at execution-teardown time (too late for earlier-executing files). `setup_module`
is the exact missing counterpart: it defers the mutation to the correct lifecycle phase (immediately before
THIS file's own tests need it), closing the gap `teardown_module` alone couldn't close, with zero change to
the mocking strategy itself, the tests' own logic, or any other file.

## Why it's safe (not just "makes the failing tests pass")

Two independent forks converged on the mechanism; a third, dedicated Phase 7 forensic-review fork
specifically tried to disprove the fix and found no flaw. Reasoning verified independently by 2 of the 3:

1. **`test_doc_pitanje_api.py`'s own 6 tests remain correct**: the only endpoint they exercise
   (`POST /api/dokument/pitanje`, handled by `routers/dokument.py::dokument_pitanje`) does its own
   function-body-**local** `from main import ask_agent` (confirmed at `routers/dokument.py:340`, verified via
   raw byte inspection that it is genuinely inside the function body, not module-level) — this re-resolves
   fresh from `sys.modules["main"]` at HTTP-request-handling time (during test execution, after
   `setup_module` has run), completely independent of whatever `api.py`'s own top-level
   `from main import ask_agent, ...` (api.py:94) bound at ITS OWN import time. No other code path in this
   file's tests touches `main.*`.
2. **`test_uploaded_doc_api.py`'s own 8 tests remain correct**: exhaustive grep confirms zero references to
   `main.*`/`sys.modules["main"]` anywhere in this file's own test bodies — its mock exists purely to avoid
   `api.py`'s own import-time overhead, not because any test exercises `main`-backed behavior.
3. **`pinecone`/`supabase` mocks deferring to `setup_module` doesn't break `import api` at collection time**:
   both are real, installed, importable packages (verified directly: `import pinecone`/`import supabase`
   both succeed) — `api.py`'s own top-level imports of them succeed with or without the mock in place;
   the mock is a runtime-isolation nicety for these 2 files' own tests, not a requirement for `api.py` to
   import successfully.
4. **Isolation and filtering both verified empirically, not just reasoned about**: `test_doc_pitanje_api.py`
   alone → 6/6 pass. `test_uploaded_doc_api.py` alone → 8/8 pass. `pytest tests/test_doc_pitanje_api.py -k
   "happy_path"` (selecting 1 of 6 tests) → the selected test still passes, confirming `setup_module` fires
   correctly even under `-k` filtering, per pytest's own documented xunit-fixture semantics.
5. **No latent pollution elsewhere**: re-grepped, independently, twice — these are the only 2 files in
   `tests/` doing an unguarded module-level `sys.modules[...]` mutation of any module name. Every other file
   that touches `sys.modules["main"]` already used the correct stash-then-restore-at-import pattern and was
   never part of the problem.

## What was NOT done, and why

- **No change to `main.py`, `api.py`, `routers/dokument.py`, or any production code.** The failing tests were
  themselves the defect's symptom; the defect was entirely in test infrastructure. Per this mission's own
  "no opportunistic cleanup, no unrelated refactor" rule, production code was not touched.
- **The alternative fix direction one fork suggested** (patching `api.py`'s own bound `main` reference via
  `unittest.mock.patch`/a `monkeypatch` fixture, instead of a global `sys.modules` mutation) was considered
  and rejected as the chosen implementation: it would require restructuring how both files patch dependencies
  throughout every test function (a larger, higher-risk change touching more surface), whereas the
  `setup_module` fix is a minimal, 2-function timing correction with an exact existing precedent
  (`teardown_module`) already in the same files. Per Phase 5's explicit "minimal repair only" rule, the
  smaller, lower-risk fix was chosen once both were confirmed to close the same root cause.
- **No test was skipped, xfailed, deleted, or had its assertions weakened.** Confirmed via grep: zero new
  `@pytest.mark.skip`/`xfail`/`pytest.skip(` markers anywhere in the affected files or elsewhere.
