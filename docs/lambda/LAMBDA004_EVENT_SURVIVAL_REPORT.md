# Event Survival Report — Program Lambda, Certification 004

**Agent**: Distributed Systems Engineer, with the atomic-claim fix implemented by the coordinator and
adversarially re-attacked by a dedicated Phase 6 fork.

## Worker crash mid-processing (Smart Intake) — SAFE

`claim_intake_job` RPC atomic claim; `reap_stale_jobs` genuinely wired into the tick loop; `_process`'s own
idempotency check detects and cleans up a crash-landed partial state.

## Worker crash between consequences — SAFE mechanism, was NOT uniformly safe outcome — now FIXED

`handle_case_changed` correctly resumes at the next unstarted consequence on retry (skip-completed
mechanism, genuinely proven for `genome_refresh`→`case_intelligence_summary`). But this only prevents
*skipped* work — it did not by itself guarantee a *replayed* consequence was side-effect-free.

## Duplicate event delivery / consequence idempotency — MIXED, now FIXED at the root

Before this sprint: 4 of 9 consequence executors (`_consequence_timeline_entry`,
`_consequence_review_confirmation_audit`, `_consequence_review_rejection_audit`, `_consequence_conflict_check`,
`_consequence_case_intelligence_summary`) had no downstream dedup protection — a replay under the
`LAMBDA003-EVT-001` race would produce a visible duplicate row (a second Timeline entry, a second audit row,
a second conflict-of-interest alert, a second intelligence summary violating that table's own documented
"one row per predmet+event" invariant with no DB-level enforcement). 2 newer consequences
(`_consequence_refresh_case_actions`, `_consequence_project_case_actions_to_notifications`) already had a
reconciler + DB-level partial-unique-index safety net.

**Root-cause fix, not a per-table patch**: `services/case_evolution.py::_try_claim_consequence` replaces the
read-then-write dedup check with a genuinely atomic claim (see `LAMBDA004_FIX_REPORT.md` Fix D for full
detail). Fixing the SHARED claim mechanism closes the race for ALL 9 consequences at once — the 2
already-hardened ones keep their own belt-and-suspenders protection, but no longer need it to stay safe.

## Stuck / dead-lettered events — mechanism SAFE, alerting gap named as debt

`dispatch_pending_events` correctly stops retrying after `MAX_DISPATCH_ATTEMPTS=5`, writes an explicit
`"DEAD_LETTER after N attempts"` marker, logs at CRITICAL — durably provable, never silently vanishes. Gap:
purely passive (queryable/log-visible), nothing actively pages a human despite the log message's own text
asserting manual intervention is needed. Named in `LAMBDA004_HANDOVER.md`, not fixed this sprint (a genuine
new capability — an alerting/paging integration — explicitly out of scope for a "fix confirmed reliability
problems, no new capabilities" sprint).

## Forged events / orphan events / cross-tenant race — CERTIFIED, no findings

Zero unauthenticated-input path reaches event construction (every webhook handler checked). Orphan
`predmet_id` scenarios fail safely into the standard retry/dead-letter path. No shared mutable state exists
between concurrent handler executions of different events — the TOCTOU race (now fixed) always stayed
strictly within one event's own identity, never crossed a tenant boundary.

## Scenario 4, per this mission's own brief ("Event cascade, consumer crashes between consequences. Expected:
safe retry.") — was PARTIALLY SURVIVES, now fully CERTIFIED after the fix.

## The fix, adversarially verified (Phase 6)

The coordinator's own first implementation attempt (unconditional reclaim of a 'pending' status) was proven
wrong by a regression test the coordinator wrote immediately after implementing it — a self-referential
precondition=target-value transition that any number of concurrent callers could all satisfy. Corrected via a
staleness gate reusing `shared/intake_queue.py::reap_stale_jobs`'s own already-shipped 300-second threshold
(not a newly-guessed number) for the identical "claimed but never finished" problem shape. A dedicated Phase
6 adversarial fork then specifically re-attacked the corrected version — traced the row-locking semantics
under Postgres READ COMMITTED isolation, checked for residual self-referential traps, checked the
read-then-conditional-write gap in `_get_consequence_status` for staleness — **CONFIRMED HOLDS**, one
documented assumption noted (default READ COMMITTED isolation, not explicitly configured but is Postgres's
own default and not overridden anywhere in this codebase).

**Status: FIXED.** Proof: `tests/test_case_evolution.py` (10 new tests covering fresh-claim, race-losing,
failed-reclaim, completed-never-reclaimed, stale-pending-reclaim, and fresh-pending-not-reclaimed), plus 6
test files' own fake-Supabase harnesses updated to correctly model the new atomic-claim semantics (55 tests
total, all passing).
