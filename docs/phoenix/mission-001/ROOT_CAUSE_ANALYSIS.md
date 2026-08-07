# Mission 001 — Root Cause Analysis

## Common root cause

All 4 findings share one architectural gap: **the concept of "is this predmet still active"
(or, for hearings specifically, "is this hearing still scheduled") was never centralized as a
canonical filter every reader must apply — each endpoint independently decided its own query
shape, and 4 of them never applied the filter at all.**

This is the same "declared control ≠ enforced control" pattern this engagement has named
repeatedly (Forensic Remediation Mission, Program Lambda): `dashboard.py` and `health_index.py`
correctly filter; `email_notif.py` and `dashboard.py`'s own hearings/deadlines panels were
fixed for it earlier this week (Operation Living System); but `zastarelost.py`,
`matter_intel.py`, `kalendar.py`, and `case_actions.py` were never audited against that same
pattern until this mission's Red Team/simulation passes found them.

## Per-item detail

- **`LIVINGSYS-DEBT-037`**: `guardian_scan`'s `rokovi` query was written independently of
  `dashboard.py`'s own deadline-fetch logic (different table entirely — `rokovi`, not
  `predmet_hronologija`), so it never inherited the fix applied to the latter.
- **`LIVINGSYS-DEBT-048`**: `matter_intel.py` is (per `calculate_procesni_rizik`'s own
  docstring) the file the risk-scoring algorithm was originally extracted FROM — meaning its
  own hearing query predates the `.eq("status","zakazano")` convention that was only added to
  its downstream siblings (`dashboard.py`, `health_index.py`) later, and was never backported
  to the origin file.
- **`LIVINGSYS-DEBT-038`** (leak part): `kalendar.py::_aggr_events` already fetches `predmeti`
  for name-resolution purposes (`pred_map`) — the status field was simply never selected or
  checked, an omission rather than a missing capability (the data was one column-select away).
- **`LIVINGSYS-DEBT-036`**: `case_actions.py::get_worklist` fetches `predmeti` purely for
  `naziv` lookup (identical shape to kalendar.py's own gap) — same omission class.

## Why a query-level filter is the correct fix, not a data-hygiene fix

The debt register's own original note on `-036` suggested the "correct" fix might be a new
consequence executor that closes `case_actions` rows on case archival. That remains real,
separate debt (data hygiene: a closed case's `case_actions` rows stay `status='open'` forever
in the database). This mission's fix is narrower and correct for its actual target: the
**lawyer-facing visibility** harm — a query-level filter is the same category of fix Operation
Living System's own L2/L7 fixes already used successfully for the identical class of finding,
and matches the "minimum-risk, reuse existing canonical filter" mandate. The data-hygiene
question is a different debt item, not silently resolved by this fix and not claimed as such.

## Why kalendar.py and zastarelost.py use "positive confirmation" but case_actions.py doesn't

`case_actions.py` filters at the SQL query level (`predmeti` fetch itself excludes archived
cases) — every id downstream is already known-active, no ambiguity possible.

`kalendar.py` and `zastarelost.py` instead fetch the full predmeti set, then post-filter deadline
rows against a separately-computed archived-id set. Here, a deadline referencing a `predmet_id`
NOT found in that fetch at all (cross-user edge case, hard-deleted case, or a genuine query
hiccup) is architecturally different from "positively confirmed archived" — a pre-existing test
(`test_aggr_events_predmet_name_fallback`) proved the codebase's own existing convention is to
fail OPEN in that case (show the event with a name-fallback), not silently hide it. The fix
respects that pre-existing, tested convention rather than overriding it.
