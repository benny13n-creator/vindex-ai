# Mission 012 — Test Results

## New tests: `tests/test_phoenix_mission_012_duplication_race_gaps.py`

| Test | Verifies |
|---|---|
| `test_cooldown_claim_first_call_of_day_succeeds` | First call of the day claims cleanly |
| `test_cooldown_claim_concurrent_calls_only_one_wins` | **Flagship** (`-012`): race is closed |
| `test_cooldown_claim_succeeds_again_after_window_elapses` | Not a permanent lock |
| `test_consume_raises_429_when_cooldown_claim_fails` | `consume()`'s error shape unchanged |
| `test_validate_hronologija_datum_iso_accepts_valid_date` | Valid date passes through |
| `test_validate_hronologija_datum_iso_rejects_hallucinated_date` | **Flagship** (`-021`): bad date dropped |
| `test_validate_hronologija_datum_iso_handles_none_and_placeholders` | Absent/placeholder handling |
| `test_insert_hronologija_rows_persists_valid_rows_despite_one_bad_row` | Siblings survive one bad row |
| `test_coalesced_caller_waits_for_inflight_run_to_complete` | **Flagship** (`-045`): timing fixed |
| `test_genome_refresh_inflight_state_fully_cleaned_up_after_coalesce` | No state leak |
| `test_coalesced_caller_falls_back_after_timeout_instead_of_hanging_forever` | Bounded wait, no indefinite hang |
| `test_refresh_case_dna_endpoint_guard_unaffected_by_this_fix` | Manual endpoint's own guard untouched |
| `test_cio_run_concurrent_calls_charge_only_once` | **Flagship** (`-046`): race is closed |
| `test_cio_run_still_charges_on_a_genuinely_separate_call` | `/run` still repeatable |

**Result: 14 passed, 0 failed.**

## Corrected pre-existing test

1 in `tests/test_ztc_genome_scale_and_race.py`
(`test_concurrent_trigger_for_same_predmet_is_coalesced_not_dropped`) — see incident note below.

## Subsystem tests

497 tests across `shared/usage.py`, `api.py`'s upload endpoint, `case_dna.py`, `cio.py`, the
genome/case-evolution test families, and dependent certification suites: **497 passed, 0
failed.**

## Full repository regression suite

| | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline (post-Mission 011) | 3,289 | 1 | 0 |
| Post-Mission 012 | 3,303 | 1 | 0 |

Net +14 (exactly the new mission tests). **Zero regressions.** (347.14s — back to the normal
~6-minute baseline after the incident below was fixed.)

## Incident during this mission: a real deadlock risk, caught and fixed before certification

The first full-suite run for this mission did not complete within the normal ~6-7 minute window
(observed stuck at ~95-96% for 20+ minutes with zero further progress and the process still
alive) — a genuine hang, not a slow run. Investigation traced it to `-045`'s own fix: making a
coalesced caller `await` the in-flight run's completion event (instead of returning immediately)
is correct for the debt item's stated goal, but an **unbounded** wait meant a single hung/slow
underlying call would now also block every OTHER concurrent trigger for the same case — a
strictly worse failure mode than the one being fixed, and a real production risk (a genuine
OpenAI outage during a genome refresh would now cascade to every other concurrent trigger for
that case, not just its own caller).

Two fixes applied before re-certifying:
1. **Production code**: the wait is now bounded (`asyncio.wait_for(..., timeout=
   _GENOME_COALESCE_WAIT_TIMEOUT)`, 120s — one full retry/backoff cycle of the underlying 60s
   GPT-call timeout plus margin), falling back to pre-mission behavior (return without waiting
   further) on timeout rather than raising. Proven by the new
   `test_coalesced_caller_falls_back_after_timeout_instead_of_hanging_forever` test (patches the
   timeout constant to 0.05s to exercise the fallback deterministically, no real wait).
2. **Pre-existing test fix**: `test_ztc_genome_scale_and_race.py`'s own concurrency test directly
   `await`ed a coalescing call that (correctly, under the new behavior) now waits on a `release`
   event the test itself hadn't fired yet — a genuine deadlock in the TEST, not the production
   code, once the semantics changed. Fixed by launching that call as its own task (matching the
   test's own pattern already used for the first caller) instead of awaiting it inline.

The 2nd full-suite run (reported above, 3,303 passed, 347s) confirms the fix: normal runtime
restored, zero hangs, zero regressions. This is disclosed here rather than silently fixed and
omitted, per this program's own "no shortcuts" rule — the STOP GATE was genuinely triggered by
this discovery, addressed, and re-verified before certifying the mission.

## Red Team self-check

1. **Could the bounded timeout reintroduce the original false-failure blind spot for a
   LEGITIMATELY slow (but not hung) refresh?** Only if a single genome refresh genuinely takes
   longer than 120s — the existing single-call GPT timeout is 60s with retries, so a normal
   refresh completing within 120s is the expected case; a refresh that doesn't is already an
   anomaly the pre-mission code had no better answer for either (the coalesced caller would have
   returned instantly and reported false failure regardless).
2. **Could `-012`'s cooldown claim ever double-charge in the exact scenario it targets?** No —
   `test_cooldown_claim_concurrent_calls_only_one_wins` proves only one of two same-window calls
   claims; `UsageService.consume()`'s credit deduction only proceeds past a successful claim.
3. **Could `-021`'s per-row insert silently mask a systemic DB problem (e.g. table missing)
   entirely, by "successfully" logging 0/N with no visible error?** No — each row's exception is
   individually logged at WARNING level with the specific row's `dogadjaj` text; a systemic
   failure produces N warnings, not silence, and the function's own return value (`hron_count`)
   already flows into the existing `logger.info("... %d/%d ...")` summary line, visible in
   application logs either way.
4. **Could `-046`'s claim ever reject a genuinely first-ever `/run` call for a user?** No — no
   row existing yet always falls through to the `INSERT` branch, which only fails on an actual
   concurrent race (duplicate key), proven by `test_cio_run_still_charges_on_a_genuinely_separate_call`.

No further break found. **Mission 012 STOP GATE: PASS** (after 1 self-caught, self-fixed,
disclosed deadlock incident).
