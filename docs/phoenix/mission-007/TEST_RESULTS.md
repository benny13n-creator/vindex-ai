# Mission 007 — Test Results

## New tests: `tests/test_phoenix_mission_007_case_evolution_chain_integrity.py`

| Test | Verifies |
|---|---|
| `test_timeline_entry_skips_duplicate_insert_on_reclaim` | Crash-then-reclaim within the stale window returns the existing row's id and inserts nothing new |
| `test_timeline_entry_creates_row_when_no_recent_duplicate` | Normal path (no prior duplicate) still inserts exactly once |
| `test_new_evidence_registered_now_includes_refresh_case_actions` | Registry entry now contains both `evidence_classification` and `refresh_case_actions` |

**Result: 3 passed, 0 failed.**

## Subsystem tests (10 files touching `case_evolution.py`)

**Result: 106 passed, 0 failed.**

## Full repository regression suite

| | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline (post-Mission 006) | 3,254 | 1 | 0 |
| Post-Mission 007 | 3,257 | 1 | 0 |

Net +3 (exactly the new mission tests). **Zero regressions.**

## Red Team self-check

Attacked both fixes directly, adversarially:

1. **Timeline dedup — cross-case bleed?** Attempted to construct a scenario where two
   different cases produce the same `dogadjaj` text within the window. The query filters on
   `predmet_id` first — a match requires the SAME case, so no cross-case suppression is
   possible.
2. **Timeline dedup — different real events, same case, similar timing?** `dogadjaj` is
   built from event-specific payload text (e.g. document names) — two genuinely different
   accepted documents produce different `dogadjaj` strings and both get their own row; only
   byte-identical descriptions within 300s are collapsed, which is precisely the crash-reclaim
   signature this fix targets, not a normal double-event case.
3. **Timeline dedup — legitimate duplicate content, e.g. same document name uploaded twice on
   purpose by the user 60s apart?** This would also be collapsed by design — judged acceptable
   because `LIVINGSYS-DEBT-043`'s prior mission established the identical precedent
   (`rocista.py`, 30s window) and the debt register itself named "identical content in a
   recent window" as the intended idiom; a stricter per-event-id key isn't available since
   `predmet_hronologija` has no `event_id` column without a migration.
4. **`refresh_case_actions` double-fire — could evidence registration fire it twice in the
   same request if another registered event type also fires in the same transaction?** No —
   each `Event` carries exactly one `EventType`; the registry is keyed per-type and the outer
   claim mechanism (`(event_id, consequence_name)` uniqueness) already prevents the SAME
   `(event, consequence_name)` pair from executing twice regardless of registry contents.

No break found. **Mission 007 STOP GATE: PASS.**
