# Regression Certification Report — Program Lambda, Certification 003A

## Full-suite result

| | Before this sprint | After this sprint |
|---|---|---|
| Passed | 2,984 | **2,991** |
| Skipped | 1 | 1 |
| Failed | **7** | **0** |
| Total collected | 2,992 | 2,992 |

Exact delta: +7 passed, 0 failed, 0 skipped-change, 0 change in total collected — the 7 previously-failing
tests now pass; nothing else moved in either direction. This is the cleanest possible signature of a correct,
narrowly-targeted fix: no new tests added, no tests removed, no collection count change, only the 7 affected
tests flipping from failing to passing.

## Test layers run, per this mission's own Phase 6 requirement

1. **Targeted tests**: `tests/test_doc_pitanje_api.py` alone (6/6 pass), `tests/test_uploaded_doc_api.py`
   alone (8/8 pass) — the 2 files actually modified.
2. **Affected module tests**: the 2 modified files run together with the previously-failing file plus its
   alphabetical neighbors (`tests/test_a6_fixes.py`, `tests/test_akcija1_faza4_bugfixes_2026_07_24.py`,
   `tests/test_akcija2_faza4_2026_07_24.py`) — 67/67 pass.
3. **Filtering edge case**: `pytest tests/test_doc_pitanje_api.py -k "happy_path"` (selecting 1 of 6 tests)
   — confirms the fix holds even when pytest's own `-k` selection reduces which tests in a file actually run,
   a scenario that could plausibly have broken an xunit-hook-based fix if implemented incorrectly.
4. **Full repository suite**: `python -m pytest -q` — **2,991 passed, 1 skipped, 0 failed.**

## Forensic review (Phase 7) — independently attempted to disprove the fix

A dedicated, separate fork was tasked with trying to prove the fix wrong, not confirm it. It independently
re-verified (not re-citing the coordinator's own reasoning):
- `routers/dokument.py:340`'s local `from main import ask_agent` is genuinely function-scoped (checked raw
  file bytes/indentation directly, not just a text search).
- Both modified files pass standalone in isolation (ruling out a new hidden inter-file dependency the fix
  itself might have introduced).
- `setup_module` fires correctly under `-k` test selection (ruling out silent mock-masking in a common
  developer workflow).
- No `skip`/`xfail` marker was added anywhere (ruling out a false-green shortcut).
- No other file in `tests/` performs the same unguarded collection-time `sys.modules` mutation (ruling out a
  second, still-latent instance of the same bug class).

**Verdict: the fix holds. No flaw found, no follow-up required.**

## No new regressions, silent behavior changes, or masking found

- **New regressions**: none — full-suite delta is exactly +7/-0, zero collateral movement anywhere else in
  2,992 collected tests.
- **Silent behavior changes**: none — the fix only changes WHEN a mock is installed (collection vs.
  execution), never WHAT is installed or how any test's own assertions behave.
- **Mock masking**: none — verified the mock still installs correctly for every test in the 2 modified files,
  under both full-run and filtered-selection scenarios.
- **Overfitted tests**: none — no test assertion was changed, weakened, or added to specifically accommodate
  this fix.
- **False green states**: none — no skip/xfail anywhere; the 7 previously-failing tests now pass with their
  original, unmodified assertions.
- **Dependency masking**: none — `pinecone`/`supabase` remain real, correctly-installed packages throughout;
  nothing was newly stubbed to hide an unrelated problem.

## Certification

Repository exits this sprint with: zero failing tests, zero unexpected regressions, root cause identified
with git-verified evidence for the one failure cluster, the repair independently reviewed by a dedicated
forensic pass, full suite green, and honest documentation of one still-open, explicitly-flagged uncertainty
(why an earlier full-suite run didn't show this failure — see `ROOT_CAUSE_ANALYSIS.md`'s own closing note).
The repository is in a clean, verified state suitable for continuing Certification 004.
