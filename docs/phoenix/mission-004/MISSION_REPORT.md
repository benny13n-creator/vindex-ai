# Program Phoenix — Mission 004: Financial Credit-Gating Consolidation

**Date**: 2026-08-07
**Debt items closed**: `LIVINGSYS-DEBT-006`, `LIVINGSYS-DEBT-002`, `LIVINGSYS-DEBT-027`.

## Why these 3 were grouped

All 3 are financial-correctness gaps in how the platform charges AI credits, each closed by
reusing an already-proven pattern from elsewhere in this exact engagement.

## Phase 1 — Reproduction

- `-006`: confirmed `routers/case_commander.py::commander_jutarnji`'s cache-check → generate →
  charge sequence has no claim step — the identical race `routers/cio.py::cio_daily` had
  before Part A's fix, on a table (`commander_jutarnji`) that already has the same
  `UNIQUE(user_id, datum)` constraint (migration 057) CIO's fix relies on.
- `-002`: confirmed `routers/drafting.py::nacrt` calls `UsageService.consume(...)`
  unconditionally, regardless of `rezultat.get("status")` — contrast with the sibling
  `analiza()` 35 lines below, which correctly gates.
- `-027`: confirmed `routers/drafting.py::podnesak` calls `UsageService.consume(...)`
  unconditionally after 3 independent GPT sub-steps (entity extraction, RAG, enrichment), each
  wrapped in its own try/except that degrades to an empty default on failure.

## Phase 2 — Root cause

- `-006`: `commander_jutarnji`'s cache-then-generate-then-charge pattern was written
  independently of (and, per its own code, chronologically likely before) `cio_daily`'s fix —
  the SAME bug class existed in both files, only one got the fix when Part A found and closed
  it there.
- `-002`/`-027`: `drafting.py` has 2 different credit-gating conventions living side by side in
  the same file — `analiza()`'s correct success-gated pattern, and `nacrt()`/`podnesak()`'s
  unconditional charge — because each endpoint's failure modes were reasoned about
  independently when written, without cross-referencing the file's own already-correct sibling.

## Phase 3 — Fix

- `-006`: `commander_jutarnji` now claims today's row via a plain `INSERT` before
  generating/charging (this table's cache has no time-based staleness window — unlike CIO's,
  which needed a 2-step "claim stale-or-absent" dance — so a single INSERT-claim suffices).
  Relies on the table's existing `UNIQUE(user_id, datum)` as the real race-breaker; a losing
  request still returns its own freshly-generated brifing, just isn't the one charged/cached.
- `-002`: `nacrt()` now gates `UsageService.consume(...)` on
  `rezultat.get("status") == "success" and rezultat.get("data")`, calling
  `UsageService.balance(...)` instead on failure — exactly `analiza()`'s own pattern.
- `-027`: `podnesak()` now gates the charge on `entiteti` (the extracted-facts dict) being
  non-empty — the one sub-step whose complete failure makes the draft closest to worthless (a
  template with no real case facts). RAG/VKS/enrichment degrading individually still produces
  a substantially useful draft and is still charged, matching this debt item's own "Medium, not
  High" distinction from `-002`.

No new algorithm anywhere — `-006` reuses CIO's own claim idiom, `-002` reuses `analiza()`'s own
gating idiom.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_004_financial_credit_gating.py`, 4 tests.

## Phase 5 — Original scenario rerun

`test_commander_jutarnji_concurrent_calls_charge_only_once` directly reproduces 2
near-simultaneous calls for the same user/day and confirms only 1 charge fires (would have
been 2 against the pre-fix code). `test_nacrt_does_not_charge_on_generation_failure` reproduces
a total generation failure and confirms zero charge.

## Phase 6 — Subsystem tests

240 tests across 14 files touching `case_commander.py`/`drafting.py`: **240 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
