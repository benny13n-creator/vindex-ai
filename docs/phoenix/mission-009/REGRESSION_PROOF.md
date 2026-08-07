# Mission 009 — Regression Proof

## Fix 1 — argument grounding disclosure

**Claim**: the disclosure is additive and cannot change `uspesnost_procena`/`boja`/any existing
field, and cannot mislabel a genuinely grounded argument as ungrounded except via a benign,
safe-direction text-match miss.

- `test_argument_reputation_discloses_grounded_argument_as_true` and
  `..._discloses_ungrounded_argument_as_false` prove the flag reflects the actual retrieval
  outcome for a single argument in each direction.
- `test_argument_reputation_arguments_beyond_fifth_never_grounded` proves the boundary at
  exactly 5 arguments, and proves it's structural (never queried) rather than data-dependent
  (would still be `False` even if a query for argument 6 would have succeeded).
- Pre-existing `test_argument_reputation_boja_derived_not_raw_llm` (RAG disabled entirely)
  continues to pass unmodified — `boja` derivation is untouched by this fix.

## Fix 2 — critique-pass disclosure

**Claim**: `critique_applied` accurately reflects whether the pass verified or fixed the draft,
and the draft TEXT returned is byte-identical to pre-mission behavior in every branch (only the
signal is new, not the content).

- All 3 `_critique_and_refine_draft` branches (clean, fixed, exception, unfixed-problem) are
  covered by the 5 corrected tests in `test_faza3_drafting_engine_2026_07_24.py` plus 3 new
  tests in this mission's own file — every one asserts the nacrt TEXT is unchanged from its
  pre-mission value, only the added `critique_applied` bool is new.
- `test_podnesak_response_includes_critique_applied_field` (structural) confirms the call site
  correctly unpacks the tuple and threads it into the response dict.
- `test_frontend_shows_critique_warning_banner_when_not_applied` (structural) confirms the
  conditional banner and its exact trigger condition are present.

## Subsystem regression

173 tests across `court_predictor.py`, `drafting.py`, `templates/podnesci.py`, and the frontend
structural suite (including the `node --check` syntax gate): **173 passed, 0 failed** — 6
pre-existing tests needed correction for the additive shape change (documented in Mission
Report), none needed behavioral weakening.

## Full-suite regression

See `TEST_RESULTS.md` for the exact before/after counts.
