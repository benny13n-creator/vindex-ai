# Program Phoenix — Mission 014: CIO Portfolio Truncation Disclosure

**Date**: 2026-08-08
**Debt items addressed**: `LIVINGSYS-DEBT-003` (CRITICAL — partially, via the disclosure-only
sub-fix).

## Why this became its own mission

`-003` is 1 of only 2 CRITICAL-severity items in the entire Living System debt register (the
other, `-013`, was closed in Mission 010) and had not been touched by any of the prior 13
missions — it was correctly deferred because its 2 named fix options (raise/remove the 40-case
cap; change the oldest-first ordering) both require a founder decision this coordinator can't
make unilaterally (a genuine query-cost-at-scale tradeoff, and which cases should represent a
portfolio when not all can be shown). But the debt item's own wording names a THIRD, narrower
gap that doesn't require either decision: "no `total_in_db`/`truncated` disclosure anywhere in
the response or UI." That gap is bounded, mechanical, and matches the exact "make the gap
visible" precedent already proven in Missions 006/009/010 — worth its own focused mission rather
than folding into the low-severity sweep, given its CRITICAL severity.

## Phase 1 — Reproduction

Confirmed `routers/cio.py::_generiši_cio_izvestaj` fetches at most 40 active cases
(`.order("updated_at", desc=False).limit(40)`, oldest-first) and returns
`portfolio_zdravlje.ukupno_aktivnih` as if it were the firm's whole active caseload — with zero
field anywhere in the response indicating a 41st+ case exists. A firm with more than 40 active
cases would see a CIO report confidently describing itself as complete when it silently excludes
their most-neglected cases (the ones oldest-first ordering surfaces last, which is precisely the
population most likely to need attention).

## Phase 2 — Root cause

The cap and ordering were both deliberate engineering decisions (bounding GPT cost and query
size) made without a corresponding disclosure decision — the report's own internal accounting
never distinguished "this is the whole portfolio" from "this is a sample of it."

## Phase 3 — Fix

- A new lightweight `count="exact"` query (no row data, `.limit(1)`) runs concurrently with the
  existing capped fetch, giving the TRUE total active-case count. Kept deliberately **fail-soft**
  (a count-query failure logs a warning and falls back to "truncation unknown," never taking down
  the whole report) — distinct from the core `predmeti` fetch, which keeps its original fail-hard
  behavior (a genuine DB error there must still propagate as the caller's existing 500, not be
  silently reinterpreted as "0 active cases").
- `portfolio_zdravlje` gained `ukupno_u_bazi` (true total) and `truncated` (bool) in BOTH return
  paths (the main report and the early-return "no portfolio with a Genome model" path).
- Frontend: the CIO widget's header now shows "prikazano N/M" (shown N of M) when truncated,
  with a title-attribute explaining why, instead of silently showing only "N predmeta."
- The cap itself (40) and the ordering (oldest-first) are **unchanged** — those remain the
  founder's decision to make.

`static/sw.js` `CACHE_NAME` bumped `vindex-v104` → `vindex-v105` (this mission touched
`vindex.js`).

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_014_cio_truncation_disclosure.py`, 6 tests. Zero
pre-existing tests needed modification (confirmed via a targeted 101-test subsystem run).

## Phase 5 — Original scenario rerun

`test_cio_report_discloses_truncation_when_over_cap` directly reproduces the debt item's exact
scenario (more active cases exist than the cap returns) and confirms the response now discloses
it.

## Phase 6 — Subsystem tests

101 tests across `cio.py` and dependent Tau/Singular-Intelligence/frontend-structural suites:
**101 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`. Run under a hard shell-level `timeout` wrapper, continuing this
program's post-Mission-012 precaution.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk, no hang.
**PASS.**
