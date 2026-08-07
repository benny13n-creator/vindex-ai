# Program Phoenix — Mission 001: Archived-Case Visibility Consolidation

**Date**: 2026-08-07
**Debt items closed**: `LIVINGSYS-DEBT-037`, `LIVINGSYS-DEBT-048`, `LIVINGSYS-DEBT-038` (leak
part only — the calendar's separate 200-row-cap/no-truncation-signal issue remains open, not
in scope for this mission), `LIVINGSYS-DEBT-036`.

## Why these 4 were grouped

Same architecture, same root cause, same fix pattern: each is a proactive or operational
surface reading `rocista`/`rokovi`/`predmet_hronologija`/`case_actions` without checking
whether the parent case is archived/closed (or, for `-048` specifically, without checking the
hearing's own status). Operation Living System already proved and shipped this exact fix
pattern twice the same week (the email cron and Command Center) — this mission ports it to
the remaining 4 confirmed sites, no new pattern invented.

## Phase 1 — Reproduction

All 4 confirmed present in current code before any edit:
- `routers/zastarelost.py::guardian_scan` — `rokovi` query filtered only by `user_id`/date
  range, no join or filter against `predmeti.status`.
- `routers/matter_intel.py::get_matter_intel` — `rocista` query filtered only by `predmet_id`,
  no `.eq("status","zakazano")` (unlike `dashboard.py`/`health_index.py`'s identical
  computation).
- `routers/kalendar.py::_aggr_events` — fetched `predmeti` (id, naziv) but never checked
  `status`; both the `rocista` and `predmet_hronologija` loops rendered every row unconditionally.
- `routers/case_actions.py::get_worklist` — `predmeti` fetch had no status filter, so
  `_fetch_open_actions` was queried with archived cases' ids included.

## Phase 2 — Root cause

Same class the debt register already names: none of these 4 endpoints reuses the canonical
"active case" concept dashboard.py/email_notif.py's own fixed sites established
(`status not in ("zatvoren","arhiviran","odbijen")`) or the sibling status-filter pattern
(`.eq("status","zakazano")` for hearings). Each read query was written independently, before
that pattern existed or without cross-referencing it.

## Phase 3 — Fix

- `zastarelost.py`: fetch `predmeti(id,status)` for the user, build `arhivirani_ids` (archived
  only), exclude `rokovi` rows whose `predmet_id` is in that set. A `rokovi` row referencing an
  unknown/absent `predmet_id` is NOT excluded (fails open — same convention verified in the
  kalendar.py fix below).
- `matter_intel.py`: added `.eq("status", "zakazano")` to the `rocista` query, matching
  `dashboard.py`/`health_index.py` exactly.
- `kalendar.py`: extended the `predmeti` select to include `status`; built `arhivirani_ids`
  (positively-confirmed archived only, not "active"); excluded matching rows from both the
  `rocista` and `predmet_hronologija` loops. Deliberately NOT excluding on "predmet_id absent
  from the fetch" — a pre-existing test proved that scenario must fail open (see Phase 4).
- `case_actions.py`: added the same `not_.in_(...)` status filter directly to the `predmeti`
  query-level fetch (cleanest of the 4 — no post-filter ambiguity since `_fetch_open_actions`
  is only ever called with already-active ids).

No new algorithm, table, or migration. Every fix reuses the exact 3-value exclusion set
(`zatvoren`/`arhiviran`/`odbijen`) `dashboard.py` already established, or the exact
`.eq("status","zakazano")` pattern `dashboard.py`/`health_index.py` already established.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_001_archived_case_visibility.py`, 4 tests, one per fix.
Full detail in `ROOT_CAUSE_ANALYSIS.md`/`FIX_LOG.md`.

One pre-existing test (`test_rocista_kalendar.py::test_aggr_events_predmet_name_fallback`)
initially broke against the first draft of the kalendar.py fix — it proved a real design
requirement (an unresolvable `predmet_id` must fail open, not be silently dropped), which
directly shaped the final "positively-confirmed archived only" filter logic rather than a
blanket "not in active set" filter. This is exactly the kind of genuine regression-test value
this program's own rules describe — not a nuisance to route around.

## Phase 5 — Original scenario rerun

Each new test directly reproduces its original finding's scenario (archived case + active case
both present, asserting only the archived one is excluded) and confirms the failure no longer
occurs. See `REGRESSION_PROOF.md`.

## Phase 6 — Subsystem tests

`test_synapse_health_deadline_events.py` + `test_matter_intel.py` + `test_rocista_kalendar.py`:
75 passed (1 pre-existing failure root-caused and fixed via the design correction above, not
weakened).

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
