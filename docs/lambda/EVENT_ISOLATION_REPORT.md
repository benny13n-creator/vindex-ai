# Event Isolation Report — Program Lambda, Certification 003

**Agent**: Event Bus Isolation. Attacked `services/event_bus.py` (durable outbox) and `services/
case_evolution.py` (the Canonical Consequence Engine) with replay, forgery, duplicate-execution, orphan,
race, double-consequence, and wrong-correlation techniques.

## Result: no cross-tenant/cross-user ownership crossing found anywhere in the Event Bus

Every technique attempted either found a CERTIFIED-safe mechanism or, in one case, a real but same-tenant-
only correctness bug (below). None crossed a `user_id`/`predmet_id` boundary.

- **Replay**: CERTIFIED for all 7 event types wired to `handle_case_changed` — `_get_consequence_status`
  checks `"completed"` before every consequence and skips; the function structurally refuses to run at all
  without a durable `event.event_id`. CERTIFIED for `PREDMET_KREIRAN` — independently marker-based idempotent
  via `run_case_pipeline`. `on_rok_kritican`/`on_health_score_promenjen`/`on_document_job_failed`/
  `on_genome_updated` have no dedup check and would produce a duplicate SAME-owner row on replay — a
  correctness/noise issue, not new (matches migration 091's own documented risk), not a security finding.
- **Forgery**: CERTIFIED, no path found. Every webhook handler checked (integracije.py, integrations.py,
  viber.py) has zero `events`-table write or `emit_durable`/`bus.publish` call. Every durable-event insert
  site derives `user_id` from an already-authenticated request or an already-ownership-verified internal
  caller — none from raw client body content.
- **Orphan events**: CERTIFIED, fails safely. A deleted-`predmet_id` scenario traced through
  `_consequence_genome_refresh`'s own verification (before/after version check) correctly raises into the
  standard retry/dead-letter path, never silently succeeds or misattributes the effect. `on_document_job_failed`
  explicitly checks for an unresolvable `uid` and fails safe.
- **Race (cross-ownership)**: CERTIFIED. No shared in-memory structure exists between concurrent handler
  executions — every handler opens its own DB queries scoped by the `Event` object's own fields, passed as an
  immutable dataclass argument. No mechanism found where processing User X's event could write into User Y's
  row. The `claim_pending_events()` RPC itself (migration 091) is correctly atomic.
- **Double consequence (sequential retry)**: CERTIFIED by design — "Retry-safe by construction," explicitly
  the mechanism Scenario 2/3/5 (crash-after-Genome, crash-after-Timeline, replay) rely on.
- **Wrong correlation**: CERTIFIED for the one loop-based emission site checked (`finalize_intake_jobs_batch`)
  — `emit_durable` is awaited synchronously inside the loop body (no late-binding closure bug), and every
  `predmet_id` in the loop is already ownership-verified upstream.

## Finding — ARCHITECTURAL DEBT: TOCTOU race in consequence-dedup, same-tenant only

`services/case_evolution.py:1039-1052` — the idempotency check is **read-then-write across two separate
round trips**, not one atomic claim: `_get_consequence_status` (read) → `if completed: skip` → `_mark_pending`
(an `upsert`, which does NOT fail/block if a row already exists — it just overwrites) → `c.executor(event)`.
If the SAME event row is genuinely dispatched twice concurrently (requires either migration 091's atomic-claim
RPC being unapplied live — `KEYSTONE-007`, unverifiable from source — OR a handler running longer than the
claim RPC's own 30-second stale-claim window), both concurrent calls can pass the read-check before either
writes `pending`, and both then execute the consequence concurrently — genuine double-execution, gated only
by whether that specific executor happens to be independently idempotent (`_consequence_genome_refresh` is,
via its own version-check; not verified for every executor in `CONSEQUENCE_REGISTRY`).

Independently re-verified by Agent 8 (Adversarial Certification): read `case_evolution.py:1015-1118` and all
4 tracking helpers directly — confirmed no module-level mutable state, no shared dict; every DB write scoped
by the composite `(event_id, consequence_name)` key; the race stays strictly within one event's own identity.
**CONFIRMED, "stays same-tenant" claim upheld, not refuted.**

**Why not fixed this sprint**: a correct fix (traced during triage) requires replacing the read-then-write
sequence with an atomic claim — either a fresh `INSERT ... ON CONFLICT DO NOTHING` (winning path), or, for
retrying a `failed`/stale-`pending` row, a conditional `UPDATE ... WHERE status='failed'` / `WHERE
status='pending' AND updated_at < <staleness cutoff>` (a compare-and-swap via Postgres row-level locking,
achievable via `supabase-py`'s `ignore_duplicates=True` upsert mode without a new migration, since the table
already has `created_at`/`updated_at` and a `UNIQUE(event_id, consequence_name)` constraint). The remaining
open question is the staleness-cutoff NUMBER (how long is "still legitimately running" vs. "abandoned, safe
to reclaim") — choosing this without production data on real executor runtime distributions is exactly the
"guessing a number" pattern this engagement has repeatedly and correctly refused to do (`LAMBDA-001`'s own
precedent). **Status: ARCHITECTURAL DEBT** (`LAMBDA003-EVT-001`), fix shape fully specified above for whoever
picks it up with real production timing data, or once migration 091 is confirmed live (which alone would
already close most of the practical exposure, per `KEYSTONE-007`).
