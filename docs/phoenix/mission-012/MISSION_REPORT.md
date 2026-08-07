# Program Phoenix — Mission 012: Document/Event Duplication & Race Gaps

**Date**: 2026-08-08
**Debt items addressed**: `LIVINGSYS-DEBT-012` (TOCTOU sub-item, fully), `LIVINGSYS-DEBT-021`
(fully), `LIVINGSYS-DEBT-045` (fully), `LIVINGSYS-DEBT-046` (fully).
**Explicitly not attempted**: `LIVINGSYS-DEBT-020` (blocked on a founder product decision —
silently skip vs. surface a duplicate-upload warning — not this coordinator's call);
`LIVINGSYS-DEBT-042` (the register's own assessment: needs new cron infrastructure and its own
design pass, not a bounded mechanical fix).

## Why these 4 were grouped

All 4 are "a check-then-write gap or an in-process guard's blind spot lets a concurrent
duplicate/racing operation slip through" — same architectural category as Missions 002/004/011's
concurrency work, reusing the same established idioms (claim-via-existing-unique-constraint,
retry-on-conflict) rather than inventing new ones.

## Phase 1 — Reproduction

- `-012` (TOCTOU): confirmed `UsageService.consume()` read `_seconds_since_last_call` (a SELECT)
  and only much later, after limit/credit checks, wrote the new call's timestamp (`_increment_
  usage`/`_log_usage_event`). No test in the repo exercised a truthy `cooldown_seconds` through
  `consume()` at all — this whole code path was previously untested.
- `-021`: confirmed `api.py`'s hronologija-extraction block built a Python list of rows then
  called ONE bulk `.insert(rows)` — a single malformed `datum_iso` value would make Postgres
  reject the whole statement, and the outer `except Exception` silently dropped every row,
  logging only a warning.
- `-045`: confirmed `_run_genome_background`'s coalesced (early-return) branch returned
  immediately when another trigger was already in-flight, before that in-flight run's own
  rerun-loop had actually finished — `case_evolution.py::_consequence_genome_refresh`'s own
  before/after `verzija` verification, reading immediately after that near-instant return, could
  observe stale data and misreport a genuinely-in-progress refresh as failed.
- `-046`: confirmed `routers/cio.py::cio_run` (`/run`, force regenerate) had zero claim/lock —
  unlike its sibling `/daily`, 2 concurrent calls could both charge credits.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

- `-012`: new `shared/usage.py::_claim_cooldown_atomic` reuses `feature_usage`'s existing
  `UNIQUE(user_id, feature_key, dan)` constraint (migration 064, no new migration) — an atomic
  conditional `UPDATE ... WHERE updated_at < cutoff`, falling back to an `INSERT` (with
  duplicate-key-as-loss handling) for the first call of the day. Wired into `consume()` in place
  of the old read-then-later-write sequence. Disclosed, deliberate behavior change: the claim now
  happens before limit/credit checks, so a call that later fails those checks still consumes the
  cooldown window — strictly more conservative, never less safe.
- `-021`: extracted `_validate_hronologija_datum_iso` (parses via `date.fromisoformat`, drops
  only the bad date, keeps the narrative event) and `_insert_hronologija_rows` (per-row insert,
  each independently try/excepted) as testable module-level functions in `api.py`; the endpoint
  now calls both instead of inlining a single bulk insert.
- `-045`: added `_genome_refresh_done_event: dict` (deliberately separate from
  `_genome_refresh_inflight`, which `refresh_case_dna`'s own reject-if-busy guard also reads/
  writes directly as a plain set — untouched). A coalesced caller now `await`s the in-flight
  run's completion event instead of returning immediately — **bounded** to 120s
  (`asyncio.wait_for`), falling back to pre-mission behavior on timeout. The bound was added
  after this mission's first full-suite run caught a real deadlock risk from an initially-
  unbounded wait — see `TEST_RESULTS.md`'s incident note for the full account.
- `-046`: `cio_run` gained the same 2-step claim `cio_daily` already has (reusing the same
  `UNIQUE(user_id, datum)` constraint, migration 050), with a short 5s race-detection window
  instead of `/daily`'s 6h cache window — appropriate for `/run`'s "always regenerate" semantics,
  which still must repeatedly work minutes/hours apart, not just once.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_012_duplication_race_gaps.py`, 14 tests. 1 pre-existing
test corrected (`test_ztc_genome_scale_and_race.py`'s own concurrency test — its coalescing call
needed to be launched as a task instead of awaited inline, once the coalescing semantics
genuinely changed; see `TEST_RESULTS.md` incident note).

## Phase 5 — Original scenario rerun

- `test_cooldown_claim_concurrent_calls_only_one_wins` directly reproduces the TOCTOU race.
- `test_validate_hronologija_datum_iso_rejects_hallucinated_date` +
  `test_insert_hronologija_rows_persists_valid_rows_despite_one_bad_row` directly reproduce the
  malformed-date-drops-the-batch scenario.
- `test_coalesced_caller_waits_for_inflight_run_to_complete` directly reproduces the coalescing
  false-failure timing gap.
- `test_cio_run_concurrent_calls_charge_only_once` directly reproduces the double-charge race.

## Phase 6 — Subsystem tests

365 tests across `shared/usage.py`, `api.py`'s upload endpoint, `case_dna.py`, `cio.py`, and
dependent certification suites: **365 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
