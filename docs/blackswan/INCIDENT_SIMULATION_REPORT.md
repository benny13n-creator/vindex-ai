# INCIDENT_SIMULATION_REPORT — Operation Black Swan, Mission 001

Detail on Scenarios 5 (DB blip) and 6 (worker crash) — the two mission scenarios most directly modeling a
real production incident. Both teams (4 and 5) actually executed reproduction scripts against real
application code with mocked failure injection, not code-trace speculation.

## Database connectivity blip (Scenario 5) — Team 4, 6 sequences tested

Method: real application functions imported and invoked directly; step 1 mocked to succeed and commit, the
target step mocked to raise a connection error, then a subsequent call made with a healthy mock representing
"connection recovered" — modeling a blip lasting a few seconds, not a permanent outage.

| Sequence | Blip point | Result | Status |
|---|---|---|---|
| `billing.py::faktura_create` | `billing_entries` UPDATE (after `fakture` INSERT committed) | Permanent orphan invoice, burned invoice number, zero try/except existed | **CRITICAL, FIXED** |
| `api.py::kreiraj_predmet` | `events` outbox INSERT (after `predmeti` INSERT committed) | Case Pipeline never runs for this case, silently, forever | **FIXED** (retry + reconciliation) |
| `event_bus.py::dispatch_pending_events` | `_mark_dispatched` UPDATE (after handler already executed a real side effect) | `claimed_at` cleared → reclaimed → handler runs AGAIN → duplicate `proactive_alerts` rows for 4 specific handlers | **DEBT-009** |
| `case_dna.py::_do_genome_refresh` | `_emit_genome_event`'s outbox insert (after `case_dna` already committed) | Live Genome correct; that version's audit-trail hash-chain entry never written | **DEBT-010** |
| `smart_intake.py::finalize` | (checked, not broken) | Atomic `claim_intake_finalize` RPC + resume-flag already close this exact gap | Verified protected |
| `intake.py::intake_bulk_import` | (checked, not broken) | Explicit compensating delete already present on the second insert's failure | Verified protected |

**Pattern**: the codebase's existing hardening (dup-checks, atomic claims, race-guards) protects well
against *concurrent logical conflicts* but, before this mission, nothing specifically targeted the
*connection-exception-mid-sequence* shape — a "fail-soft, log a warning" pattern used at several of these
sites silently drops the record with no retry queue. 2 of 4 real gaps found here are now fixed; 2 are named
debt with a clear reconciliation-pattern precedent (this mission's own `reap_orphan_fakture`/
`reap_missing_pipeline_events`) for a future mission to extend to the remaining 2.

## Worker crash mid-operation (Scenario 6) — Team 5, 5 operations × 3 crash points each

Method: 2 of 5 operations executed via real coroutines against a fake in-memory Supabase client, with a hard
crash simulated by an uncatchable exception raised at an exact point inside the mocked query chain
(`KeyboardInterrupt` was tried and discarded — it aborts the asyncio loop entirely rather than propagating
cleanly, confirmed empirically). 3 operations analyzed by direct source trace (too much surrounding
infrastructure to script safely), explicitly marked as such.

- **Genome refresh**: crash before any write → safe. Crash after history-insert, before `case_dna` update →
  live Genome stays at the OLD version (the prior certification's destructive-replace guard holds), only a
  harmless duplicate history row. Crash during the `GenomeUpdated` durable-event insert (after `case_dna`
  correctly updated) → **CONFIRMED silently lost forever** (audit-trail only, not the Genome data itself) —
  same finding as `DEBT-010` above, independently re-confirmed via a different trigger.
- **Event dispatch**: crash mid-handler for one row of a multi-row batch → the prior certification's own
  per-row claim heartbeat (added specifically for this scenario) **re-verified to hold** — both the crashed
  row and the never-reached row keep a fresh claim, correctly reclaimed only once genuinely stale. 0 losses.
- **Intake finalize**: PLAUSIBLE-UNCONFIRMED (code-trace only) — the resume path (re-detects an already-
  created predmet via `source_intake_job_id`) and the finalize-marker CAS guard both appear to correctly
  survive a crash at any of the 3 points traced. Most mature of the 5 operations, but not independently
  executed this mission.
- **Billing (`faktura_create`)**: crash after `fakture` INSERT, before `billing_entries` UPDATE →
  **CONFIRMED via execution — orphan draft invoice, permanent, no reap job existed**. Same finding as the
  Scenario 5 CRITICAL item above, independently reproduced via a different trigger mechanism (process crash
  vs. connection exception) — now fixed both ways (try/except for the connection-exception trigger, a reap
  sweep for the process-crash trigger neither try/except can catch).
- **Notification creation**: both `create_proactive_alert` and `_generate_notifications` are single atomic
  inserts (or a batch insert with a unique dedupe index) — there is no multi-step "partial write" state to
  interrupt. 0 findings, verified by code trace.

**Verdict**: 2 of 15 crash points produced a genuinely CONFIRMED "silently lost forever, no automatic
recovery" finding — both are variants of the SAME billing/orphan-invoice CRITICAL finding, now fixed with
both a connection-exception guard and a crash-tolerant reap sweep, and the audit-trail gap (`DEBT-010`),
which is real but bounded (compliance trail only, not data loss) and named as debt for a focused follow-up.
