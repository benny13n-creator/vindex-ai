# DISASTER_RECOVERY_REPORT — Operation Black Swan, Mission 001

What has automatic recovery, what needs a human, and what was found to be silently and permanently lost
before this mission's fixes.

## Automatic recovery — confirmed working

- **Event Bus dispatch**: SKIP-LOCKED claim + per-row heartbeat (this mission closed the residual gap where
  the currently-processing row itself wasn't heartbeated) → a crashed or slow worker's claimed rows are
  correctly reclaimed once genuinely stale, not before. Confirmed via direct reproduction.
- **Smart Intake finalize**: atomic claim RPC + resume-flag → a crash mid-finalize is correctly picked back
  up on retry without duplicating the created case/documents.
- **Genome data integrity**: a GPT failure or a crash mid-refresh never corrupts the live `case_dna` column
  (a destructive-replace guard from a prior certification, re-verified under this mission's own crash
  simulation).
- **Billing entry re-billing**: even when the orphan-invoice bug (below) occurred, the underlying billable
  work (`billing_entries` rows) was never destroyed — `obracunato` stayed `False`, so the work remained
  billable via a fresh invoice. The bug was a dangling invoice record, not lost billable time.

## Needed a human before this mission (now automatic)

- **Orphan draft invoices** (CRITICAL): previously silently permanent, no reap mechanism existed at all
  (confirmed via grep — `timer_sessions` had stale-auto-expire, `fakture` never did). Now: a connection-
  exception trigger is caught and rolled back in-request; a process-crash trigger (which no in-request
  try/except can catch) is caught by a new daily reap sweep (`reap_orphan_fakture`, wired into
  `/api/cron/daily`).
- **Missing Case Pipeline trigger**: previously silently permanent for a case created during a connection
  blip on the events-outbox insert. Now: a short retry closes the common transient-blip case in-request; a
  new daily reap sweep (`reap_missing_pipeline_events`) backfills the durable event for any case still
  missing one after 10+ minutes, so `dispatch_pending_events()` picks it up normally on the next poll.

## Still needs a human (named debt, not silently accepted)

- **Genome audit-trail gap** (`DEBT-010`): a blip during the `GenomeUpdated` outbox insert leaves the live
  Genome data correct but that version's compliance hash-chain entry missing, with nothing reconciling
  `events` against `case_dna.verzija`. The reap-and-backfill pattern this mission built for the 2 items
  above is a direct, named precedent for closing this — flagged as the natural next mission, not attempted
  here due to fix-cycle time.
- **Event Bus handler duplicate-execution on a mark-dispatched blip** (`DEBT-009`): 4 specific handlers
  (`on_rok_kritican`, `on_predmet_kreiran`, `on_dokument_uploadovan`, `on_health_score_promenjen`) lack a
  per-event idempotency key on their own side-effect inserts — a reclaim-and-rerun after this specific blip
  shape produces a duplicate `proactive_alerts` row. Contained fix, named for a follow-up.
- **Cross-worker-process Genome-refresh coalescing** (`DEBT-011`): the in-process guard this mission
  strengthened is inherently blind to a second gunicorn worker process racing the same case — a real gap,
  self-disclosed in the code's own prior comment, re-confirmed by 2 teams this mission. Needs a DB-level
  claim, not an in-process set.

## What "silently lost forever" meant, concretely, before this mission

For the 2 CRITICAL findings specifically: a lawyer would have seen a normal-looking, successful response
("faktura kreirana" / "predmet kreiran") in both failure cases — the failure was invisible at the moment it
happened, discoverable only much later (an invoice with no line items sitting in the drafts list; a case
whose deadlines/risk score/strategy briefing simply never got computed, with no error anywhere pointing at
why). This is the specific failure shape this mission's own STOP RULE ("don't end while any critical problem
exists") existed to catch before beta — a failure mode a lawyer would have no way to diagnose themselves.
