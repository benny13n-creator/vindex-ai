# Program Phoenix — Mission 009: Hallucination Disclosure Mitigations

**Date**: 2026-08-07
**Debt items addressed**: `LIVINGSYS-DEBT-047` (fully), `LIVINGSYS-DEBT-015` (fully).

## Why these 2 were grouped

Both are the exact same shape named explicitly in the debt register: a real AI-groundedness gap
that's expensive to fully close (extend RAG to all 10 arguments; make the critique pass
retry-until-success) but cheap and honest to *disclose* — "the same 'make the gap visible'
pattern as Part A's Fix 9/10." Different files, but the identical fix philosophy and the
identical minimal-fix shape the debt register itself already named as the plausible next step
for both.

## Phase 1 — Reproduction

- `-047`: confirmed `routers/court_predictor.py::argument_reputation` only calls
  `retrieve_sudska_praksa` for `payload.argumenti[:5]` — an endpoint that accepts up to 10
  arguments. GPT still returns an `argumenti_analiza` entry (with a `relevantne_odluke` count
  and a confident `uspesnost_procena`) for every argument submitted, with no signal
  distinguishing which ones had a real retrieval pass behind them.
- `-015`: confirmed `_critique_and_refine_draft` had 2 silent-degradation paths — the outer
  `except Exception` (LLM call/parse totally failed) and the inner "`ima_problema` is True but
  `ispravljen_tekst` is empty" branch (model detected a problem but didn't fix it) — both
  returned the plain original `nacrt` string with zero signal to the caller or the response
  payload that the anti-hallucination check didn't reliably run.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

- `-047`: added `_grounded_argumenti: set[str]` tracking which of the first 5 arguments'
  retrieval calls actually returned decision matches; after parsing the LLM response, each
  `argumenti_analiza` item gets `"rag_grounded": bool` (text-matched against the argument the
  model echoed back, fails safe to `False` on a match miss). `static/vindex.js`'s Argument
  Reputation renderer now shows a ⚠ note under any argument marked `rag_grounded: false`.
- `-015`: `_critique_and_refine_draft` now returns `(nacrt, critique_applied)` instead of a bare
  string; `critique_applied` is `True` only when the pass genuinely ran and either verified the
  draft clean or successfully produced a fix, `False` for both silent-degradation paths.
  `/api/podnesak`'s response gained a `critique_applied` field. `static/index.html`'s podnesak
  preview gained a 2nd, conditional warning banner (`podnesak-preview-critique-warn`) shown only
  when `critique_applied === false`.

`static/sw.js` `CACHE_NAME` bumped `vindex-v101` → `vindex-v102` (this mission touched
`vindex.js`/`index.html`).

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_009_hallucination_disclosure.py`, 8 tests. Plus 6
pre-existing tests corrected for the additive tuple/field shape (5 in
`tests/test_faza3_drafting_engine_2026_07_24.py`, 1 marker-string fix in
`tests/test_phoenix_mission_004_financial_credit_gating.py`).

## Phase 5 — Original scenario rerun

- `test_argument_reputation_arguments_beyond_fifth_never_grounded` directly reproduces the
  debt item's exact scenario (6 arguments, only the first 5 grounded) and confirms the 6th is
  disclosed `rag_grounded: false` even when a real retrieval call for it would have succeeded.
- `test_critique_and_refine_draft_signals_false_on_exception` and
  `..._signals_false_when_problem_reported_but_unfixed` directly reproduce both silent-
  degradation paths and confirm both now signal `critique_applied is False`.

## Phase 6 — Subsystem tests

173 tests across `court_predictor.py`, `drafting.py`, `templates/podnesci.py`, and the frontend
structural suite: **173 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
