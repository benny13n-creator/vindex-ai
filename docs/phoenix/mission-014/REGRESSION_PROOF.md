# Mission 014 — Regression Proof

## Claim 1 — the disclosure is accurate in both directions

- `test_cio_report_discloses_no_truncation_when_under_cap` proves `truncated: False` when the
  true count matches what was fetched.
- `test_cio_report_discloses_truncation_when_over_cap` proves `truncated: True` and the correct
  `ukupno_u_bazi` when the true count exceeds the cap — the flagship reproduction.
- `test_empty_portfolio_path_also_discloses_truncation` proves the early-return branch (no case
  has a Genome model) carries the same disclosure fields, not just the main path.

## Claim 2 — the fail-soft/fail-hard split is correctly asymmetric

- `test_cio_report_count_query_failure_fails_soft` proves a count-query failure degrades to
  `truncated: False` (unknown, not fabricated) without breaking the report.
- `test_cio_report_pred_query_failure_still_propagates` proves the CORE fetch's original
  fail-hard behavior is unchanged — this is the regression guard against the exact mistake
  caught and corrected during this mission's own implementation (an earlier draft accidentally
  wrapped both queries in `return_exceptions=True`, which would have silently turned a real DB
  outage into a false "0 active cases" report).

## Claim 3 — the frontend disclosure doesn't change the non-truncated rendering

`test_frontend_discloses_truncation_in_cio_widget` confirms the new conditional block exists;
since it's gated on `pg.truncated` (only ever `true` for a portfolio genuinely over the cap),
every existing non-truncated rendering path is byte-identical to before this mission.

## Subsystem regression

101 tests across `cio.py` and dependent Tau/Singular-Intelligence/frontend-structural suites:
**101 passed, 0 failed** — zero pre-existing tests needed modification, because the existing
`_make_supa` test helper (in `test_tau008_cio_consolidation.py`) returns the same mocked
response object regardless of query args, so the new count query's `.count` attribute
auto-resolves to a non-int `MagicMock`, correctly triggering this fix's own `isinstance(...,
int)` fallback (`truncated: False`) rather than breaking those tests' existing assertions.

## Full-suite regression

See `TEST_RESULTS.md`.
