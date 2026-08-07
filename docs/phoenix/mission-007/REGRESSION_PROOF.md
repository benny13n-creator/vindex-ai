# Mission 007 — Regression Proof

## Fix 1 — `_consequence_timeline_entry` duplicate guard

**Claim**: the new pre-insert duplicate check does not change behavior for the normal
(non-reclaim) case, and does not cross `predmet_id` or event-content boundaries.

- `test_timeline_entry_creates_row_when_no_recent_duplicate` proves the normal path is
  unchanged: no prior row → the query returns empty → `.insert()` still fires exactly once,
  same as before this mission.
- `test_timeline_entry_skips_duplicate_insert_on_reclaim` proves the guard fires only when a
  prior identical `(predmet_id, dogadjaj)` row exists inside the `_CONSEQUENCE_STALE_PENDING_SECONDS`
  window — the query used (`.eq("predmet_id", predmet_id).eq("dogadjaj", opis).gte("created_at", ...)`)
  matches on both `predmet_id` and the literal generated description text, so it cannot suppress
  a legitimately different timeline entry for a different case or a different document/event.
- The 300s window and helper (`_iso_seconds_ago`) are the exact same ones the module's own
  outer claim mechanism already uses to decide "is a pending claim stale enough to reclaim" —
  no new time constant, no new drift risk.

## Fix 2 — `NEW_EVIDENCE_REGISTERED` registry addition

**Claim**: adding `refresh_case_actions` to this event type does not create a duplicate
registration or conflict with its registration under other event types.

- `test_new_evidence_registered_now_includes_refresh_case_actions` confirms the registry list
  for `NEW_EVIDENCE_REGISTERED` contains both entries with no duplication.
- `refresh_case_actions` is a reconcile-style executor (recomputes/replaces current case-actions
  state from scratch) already registered independently under `DOCUMENT_ACCEPTED`,
  `REVIEW_ACCEPTED`, and `ROCISTE_ZAKAZANO` — each event type's registration is independent and
  the executor itself does not accumulate state across calls, so firing it once more (on
  evidence registration) is additive-safe by the same reasoning already relied on for the other
  3 event types.

## Subsystem regression

106 tests across the 10 files exercising `case_evolution.py`'s registry/timeline/genome logic:
**106 passed, 0 failed** (no pre-existing test needed modification).

## Full-suite regression

Baseline (post-Mission 006): 3,254 passed, 1 skipped, 0 failed.
Post-Mission 007: **3,257 passed, 1 skipped, 0 failed** (+3, exactly the 3 new mission tests;
no other test count moved, confirming zero collateral breakage).
