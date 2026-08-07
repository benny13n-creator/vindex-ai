# Mission 005 — Root Cause Analysis

## Common root cause

Both findings conflate "did the underlying database action run" with "should a new durable
event fire" — two genuinely separate questions that happen to usually coincide, but diverge
exactly on a retry (where the DB action is correctly a no-op, but the event-emission code path
was never taught to check that).

## Per-item detail

- **`-010`**: `resolve_review()`/`reject_review()` were built with correct idempotency from the
  start (`.is_("resolved_at","null")`). The durable-event-emission code was added AFTER, as
  part of Program Delta Sprint 002's event migration, and its own author correctly reused the
  existing `job.get("predmet_id")` check for a DIFFERENT purpose (distinguishing pre- vs.
  post-finalize semantics for the consequence chain) but didn't also gate emission itself on
  `review_resolved_now` — the field that already existed for exactly this purpose one line
  above.
- **`-043`**: `rocista.py`'s own code comments show its ROCISTE_ZAKAZANO emission was migrated
  from an in-process `asyncio.create_task` call to a durable event as part of the same Sprint
  003 event migration that gave idempotency-conscious treatment to Pipeline C (Smart Intake)
  but not to this simpler, older endpoint — the durable-outbox migration pattern was applied
  file-by-file, and idempotency hardening for the CREATE path specifically wasn't part of that
  pass's scope (it was about WHERE consequences are decided, not about retry-safety of the
  triggering write itself).

## Why the fixes differ in mechanism

`-010`'s fix is a pure gating change (an existing boolean already answers the right question).
`-043`'s fix needs an actual duplicate-detection query since no existing signal distinguishes
"this predmet_id/sud/datum/vreme combination was already just inserted" — the 30-second window
approach is deliberately narrow (matches "immediate client retry," the debt item's own
reproduction scenario) rather than a broader dedup window that could incorrectly collapse two
genuinely different hearing-creation requests separated by more time.
