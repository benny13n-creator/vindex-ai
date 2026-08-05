# Batch Intelligence Validation Report — Program Omega, Sprint 002 (2026-08-06)

Phase 5's own 5 required extreme scenarios, each mapped to a specific test in
`tests/test_omega_sprint002_case_intelligence.py`.

## Scenario 1 — one predmet, 500 documents (one batch)

**Test**: `test_scenario1_single_case_large_batch_produces_one_summary_with_correct_diffs`

Simulates a single `DOCUMENT_BATCH_COMPLETED` event with `dokumenata_dodato=500`. Proves: `genome_refresh`
runs exactly ONCE (not 500 times — this is `OMEGA-001`'s own direct fix, verified by test, not just
architecturally implied); the `case_intelligence_summary` consequence produces exactly ONE
`case_intelligence_summaries` row; the diff-based fields (`kontradikcije_pronadjene`, `novi_dogadjaji`)
correctly compute against the "before" snapshot rather than reporting raw totals.

## Scenario 2 — one predmet, 500 documents, 5 separate upload sessions

**Test**: `test_scenario2_five_separate_batches_for_the_same_case_each_produce_their_own_summary`

Simulates 5 DIFFERENT `DOCUMENT_BATCH_COMPLETED` events (5 different `event_id`s, matching 5 real, distinct
upload sessions) for the SAME `predmet_id`. Proves: each session's own Genome refresh runs independently (5
total, not deduplicated against each other — they are 5 legitimately different real events, not repeats of
one), producing 5 separate, individually-sourced summary rows — a queryable history of "what changed, and
when, across the whole intake process," not a single overwritten aggregate. ALSO proves replaying any ONE of
the 5 sessions again produces zero additional Genome calls and zero additional summaries — idempotency is
per-event, correctly, not per-case.

## Scenario 3 — two users, same case, concurrent upload

**Test**: `test_scenario3_two_concurrent_batches_same_case_no_cross_contamination`

Two `DOCUMENT_BATCH_COMPLETED` events for the SAME `predmet_id`, dispatched concurrently
(`asyncio.gather`). Proves: both complete correctly, both produce their own correctly-attributed summary row
(200 documents / 300 documents, never mixed up), no cross-contamination of consequence state between the two
concurrent events — the SAME architectural invariant Program Delta Sprint 004 already certified generically
(Architectural Invariants Report, "two different events, same predmet, no cross-contamination"), now proven
specifically for `DOCUMENT_BATCH_COMPLETED`. Underlying Genome-level concurrency safety (two real, concurrent
`_run_genome_background` calls for the same case) is provided by that function's own pre-existing in-flight
coalescing mechanism (`tests/test_ztc_genome_scale_and_race.py`, built before this sprint, reused unchanged —
no new locking was added).

## Scenario 4 — AI processing interrupted at 50%, restart

**Two tests**:
- `test_scenario4_crash_after_genome_before_summary_retry_does_not_redo_genome` — simulates the crash point
  the mission's own scenario describes: Genome ALREADY completed (marked `completed` in
  `case_evolution_consequences`), summary NOT yet run. A retry (a fresh `handle_case_changed` call for the
  SAME event) proves Genome is NOT re-triggered, and the summary step completes exactly once, producing
  exactly one summary row — "nastavlja gde je stalo," not "restarts from zero."
- `test_scenario4_failed_summary_step_propagates_for_outer_retry` — simulates the summary step itself failing
  (a DB error during the risk-engine queries). Proves the consequence is marked `failed` (not silently
  swallowed) and the exception propagates so the Event Bus's own existing retry/dead-letter mechanism
  (`MAX_DISPATCH_ATTEMPTS=5`, unchanged since Program Delta Sprint 001) takes over — no new retry machinery
  built, the existing one is trusted, matching every prior Delta/Omega sprint's own discipline.

## Scenario 5 — document reclassification, does Genome/Timeline/Evidence/Tasks stay synchronized?

**Not newly tested this sprint — explicitly named, not silently assumed.** Reclassification of an
already-accepted document has no dedicated event or consequence anywhere in the platform (`DOCUMENT_MODIFIED`
remains one of the 3 declared-but-not-wired events, unchanged since Program Delta Sprint 001, re-confirmed by
Program Delta Sprint 004's own certification and unchanged by this sprint). This sprint did not build
`DOCUMENT_MODIFIED`'s own wiring — doing so would be new functionality requiring its own scoped design (what
SHOULD happen when a document's classification changes — does it need a NEW evidence-classification pass? A
Genome refresh? Does the old classification's own downstream effects need to be reversed?), correctly outside
this sprint's own charter (Case Intelligence AGGREGATION, not classification-change propagation). Named here
so "Scenario 5 not covered" is an explicit, visible gap, not a silent one.

## Full regression

9 new tests (`tests/test_omega_sprint002_case_intelligence.py`) plus 3 pre-existing Program Delta
certification tests updated to reflect the new 7th wired event and 21st `EventType` member (living-document
drift detectors doing exactly the job they were built for, not broken by this sprint — updated, not
suppressed). Full suite: **2,653 passed, 1 skipped, 0 failed** (was 2,644 at end of Program Omega Sprint 001)
— exactly +9, zero regressions.
