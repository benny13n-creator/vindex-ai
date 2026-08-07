# Mission 011 — Root Cause Analysis

## `-054` — faktura_create's missing cross-reference validation

`FakturaReq.predmet_id` was added as the field that TAGS an invoice with a case for reporting
purposes, but `entry_ids` is the field that determines what actually gets billed and how much —
the 2 were never cross-checked against each other. `billing_entry_create` (the entry's own
creation endpoint) DOES validate the entry's `predmet_id` against a real, owned `predmeti` row
at creation time, so each individual entry's `predmet_id` is trustworthy — the gap is purely that
`faktura_create` never re-reads that already-correct field to confirm it matches the invoice's
own claimed case before billing.

## `-044` — redni_broj's non-atomic sequence assignment

This exact function already carries a comment (Zero-Touch Case investigation, 2026-08-03) noting
that `redni_broj` was fetched once and incremented locally specifically to avoid a WITHIN-one-
finalize-call collision (multiple documents in one bundled upload). That fix correctly solved
the problem it was scoped to, but a `SELECT MAX+1` computed in Python, with no DB-side locking
or constraint, is fundamentally non-atomic across SEPARATE requests — the exact same class of
bug `LAMBDA008-CONC-003` found and fixed for `billing.py`'s `broj_fakture` one day earlier in
this same certification lineage. This deployment's 4-worker gunicorn topology
(`gunicorn.conf.py`) makes the cross-request race concrete, not theoretical: 2 concurrent
finalize calls for the same case are routed to different worker processes with no shared
in-memory state between them.

## Why the DB-constraint + retry-on-conflict fix (not an app-level lock)

The debt register named 2 valid options. An `asyncio.Lock` keyed by `predmet_id` would correctly
serialize concurrent finalize calls WITHIN one worker process, but this deployment's 4 gunicorn
workers are separate OS processes with no shared memory — a lock in worker process A's memory is
invisible to worker process B. The DB-level unique constraint is enforced by Postgres itself,
which every worker process talks to as the single shared source of truth — the only mechanism
that actually closes the race in this deployment's real topology. This is precisely why
`billing.py`'s own prior fix for the identical bug class chose the same approach; Mission 011
reuses that established, already-proven idiom rather than introducing a new one.
