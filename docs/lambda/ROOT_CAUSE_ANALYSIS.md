# Root Cause Analysis — Program Lambda, Certification 003A

Per this mission's own rule: no implementation before at least 2 independent investigations agree. Two
separate, genuinely independent forks (each instructed to re-derive the root cause from scratch and
specifically challenge the coordinator's own prior partial-fix attempt, not just confirm it) converged on the
same mechanism, from different angles.

## The mechanism

`tests/test_doc_pitanje_api.py` and `tests/test_uploaded_doc_api.py` both install a `MagicMock()` into
`sys.modules["main"]` via bare, module-level `sys.modules.setdefault("main", _mock_main)` — code that executes
at **collection time** (the moment pytest imports the file to discover its tests), not at test-execution time.

Pytest's own lifecycle (confirmed from source, `_pytest/main.py::_main()`):
```python
config.hook.pytest_collection(session=session)   # imports EVERY test file first
config.hook.pytest_runtestloop(session=session)  # THEN executes tests, one by one
```
Collection completes for the entire session before execution of any single test begins. So by the time
`tests/test_akcija2_faza4_2026_07_24.py`'s own tests execute (alphabetically earlier than
`test_doc_pitanje_api.py`'s own tests), `sys.modules["main"]` has already been mutated during collection —
`test_akcija2`'s own `from main import _batch_segments_za_map` (function-local imports) resolves against the
mock, not the real module.

**Independent controlled-experiment proof** (Fork B, not just theoretical tracing): removing the 2 offending
files from the collection eliminates the failure entirely (53/53 pass); adding either file back alone
reproduces all 7 failures. This is causal proof, not inference.

## Why Certification 003's own `teardown_module` fix didn't work

`teardown_module` is a real, correctly-implemented pytest hook (verified against `_pytest/python.py`) that
restores `sys.modules` — but only after **that file's own tests finish executing**. Since the pollution
happens at collection (before ANY test runs) and `test_akcija2` executes before `test_doc_pitanje_api.py`'s
own tests do, `teardown_module` hadn't fired yet at the moment it was needed. The fix was mechanically
correct but targeted the wrong point in the test lifecycle — not a logic error, a lifecycle-phase error.

## Timeline — pre-existing, not introduced by Certification 002 or 003

Git-verified, not assumed:
- `test_doc_pitanje_api.py`'s `sys.modules.setdefault("main", ...)` line dates to commit `e11762d`
  (2026-05-11, the file's own creation).
- `test_uploaded_doc_api.py`'s equivalent dates to `285c007`, same era.
- `test_akcija2_faza4_2026_07_24.py` was created `4d2f05d` (2026-07-24), last modified `cf1fd87`
  (2026-08-04) — both months after the pollution mechanism already existed in the repo.
- `git diff c960a13 75525a3` (Certification 003's own commit) on the two offending files shows the ONLY
  change was *adding* the `teardown_module` hook — no other content changed, confirming Certification 003
  did not introduce or worsen the underlying mechanism, only attempted (and failed) to fix it.

**One open, unresolved point, explicitly not guessed at**: why an earlier full-suite run in this engagement's
own history reported "0 failed" when this exact colliding-file state already existed is not resolved by
either investigation. Possible explanations (different test-selection scope used for that run, a difference
in collection-order caching between sessions) were considered but not confirmed with evidence — flagged
honestly as an open question per this mission's own "never guess" rule, not asserted as settled.

## Ruled out (with evidence, not assumption)

- **Real production bug**: `git log -S "_batch_segments_za_map" -- main.py` shows the function was last
  touched in a pre-Certification-003 commit, unrelated. Certification 003's own diff to `main.py` (the
  `ask_agent` cache-isolation fix) touches only lines 3143-3525, zero overlap with the affected function.
- **Race condition / flakiness**: 100% deterministic under full collection, 100% passing under isolated-file
  execution — not timing-sensitive in either direction.
- **Dependency/version issue**: no package version changed; `pinecone`/`supabase` are real, correctly
  installed packages (confirmed importable), not stand-ins requiring a mock to function.
- **A different, unrelated bug hiding behind the same symptom**: exhaustive repo-wide re-grep (both
  investigations, independently) confirms these are the only 2 files in `tests/` performing a module-level
  (collection-time) `sys.modules[...]` mutation of any module name without a proper execution-time guard —
  every other file touching `sys.modules["main"]` already used a correct import-time stash/restore pattern.

## Two independent investigations, one converged conclusion

Both forks agreed on: the mechanism, the collision files, the reason the prior fix failed, and the timeline
(pre-existing). They differed slightly on the RECOMMENDED fix mechanism (one suggested patching `api.py`'s
own bound reference via `monkeypatch`; the other suggested moving the mutation into a `setup_module` hook) —
this is a implementation-detail difference, not a root-cause disagreement, and is resolved in
`FIX_JUSTIFICATION.md`.
