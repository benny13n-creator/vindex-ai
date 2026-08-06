# Event & Background-Worker Ownership Report — Program Lambda, Certification 002

Covers the mission's Event Bus (replay/forged/duplicated/reordered), Background Workers (does a worker trust
input without re-verifying ownership), Batch (ownership drift within a group), and Race (100-parallel-requests
class) checklist items together, since they share one execution model: everything in this app that isn't a
direct HTTP request runs through the same durable outbox (`services/event_bus.py`) or the same
`SELECT...FOR UPDATE SKIP LOCKED` queue pattern (`shared/intake_queue.py`).

## Method

No live deployment exists in this environment, so race/replay/concurrency scenarios are reasoned through at
the code level — read the actual locking/idempotency mechanism, then construct the specific interleaving that
would have to occur for an attacker to benefit. This is the same "code-level proof, not live chaos testing,
flagged as such" discipline every reliability-shaped audit in this engagement has used, extended to ownership.

## 13 worker/job-processing functions examined: 11 SAFE, 0 VULNERABLE, 2 NEEDS-DEEPER-LOOK

| # | Function | Verdict | Why |
|---|---|---|---|
| 1 | `IntakeWorker._tick/_process` | SAFE | Operates purely on `job_id`; ownership enforced one layer up (every HTTP read filters `.eq("uploaded_by", uid)`); `uploaded_by` is immutable, set once at enqueue from the authenticated uploader |
| 2 | `reap_stale_jobs` | SAFE | Same immutable `job_id`, no payload-trusted owner |
| 3 | `finalize_intake_job`/`_core` | SAFE | Every lookup re-filters `.eq("uploaded_by", uid)` from the CURRENT caller; `claim_intake_finalize` RPC atomically gates concurrent finalize calls |
| 4 | `finalize_intake_jobs_batch` | SAFE | **The mission's own named batch check**: loops `job_ids` and re-does the full per-job ownership check for EACH item via `_finalize_intake_job_core` — a foreign `job_id` in a batch cannot slip through on the strength of the other items being owned |
| 5 | `dispatch_pending_events`/`DispatchLoop` | NEEDS-DEEPER-LOOK | Builds `Event` from the outbox row's own `user_id`/`predmet_id` with no re-verification at dispatch time (see below) |
| 6 | `handle_case_changed` — 5 of 7 consequence executors | NEEDS-DEEPER-LOOK | Trust `event.user_id`/`predmet_id` verbatim (see below); the 6th, `_consequence_project_case_actions_to_notifications`, already does it correctly — proves the codebase knows the right pattern |
| 7 | `run_case_pipeline` (`on_predmet_kreiran`) | SAFE | Explicitly re-verifies `.eq("id", predmet_id).eq("user_id", user_id).single()` at the top — the strongest example in the codebase of a worker re-checking ownership at process time |
| 8 | `_check_escalations` (workflow cron) | SAFE | Notifies each row's own `assigned_uid`, read fresh from DB |
| 9 | `posalji_podsetnike` (email) | SAFE | Every downstream query scoped by the profile row's own `uid` |
| 10 | `posalji_podsetnike` (SMS/WhatsApp) | SAFE | Batches by `.in_("user_id", user_ids)`, regrouped by each row's own `user_id` |
| 11 | `/api/cron/daily` dispatcher | SAFE | Secret-gated, fans out to already-scoped workers above |
| 12 | `batch_ingest.py` admin ingest | SAFE (N/A) | Shared knowledge-base namespace, no per-tenant ownership dimension |
| 13 | `shared/proactive_alerts.py::create_proactive_alert` | N/A | Not a worker — a shared insert helper; safety inherited from callers |

### The one real finding: event-consequence executors don't re-verify at dispatch time

`services/event_bus.py:609-619` builds an `Event` directly from the durable `events` outbox row's own
`user_id`/`predmet_id` columns. 5 of `services/case_evolution.py`'s 7 consequence executors
(`_consequence_genome_refresh`, `_consequence_timeline_entry`, `_consequence_refresh_case_actions`,
`_consequence_case_intelligence_summary`, `_consequence_conflict_check`) use that `event.user_id`/`predmet_id`
directly with no fresh DB check that this pairing is still valid at the moment the consequence actually
runs — which can be up to `MAX_DISPATCH_ATTEMPTS=5` retries later. `_consequence_project_case_actions_to_notifications`
is the one exception: it re-reads `predmeti.user_id` fresh (`:829-836`) rather than trusting the event.

**Why NEEDS-DEEPER-LOOK, not VULNERABLE**: all 9 call sites across the repo that write an `events` row
(`smart_intake.py` ×6, `rocista.py` ×1, `matter_intel.py` ×2, `api.py` ×2) independently re-verify `predmet_id`
ownership synchronously, BEFORE emitting — confirmed by reading each site. There is no endpoint that lets a
client insert an `events` row directly (writes only ever go through the service-role client from trusted
server code). `predmeti.user_id` is never reassigned anywhere in the repo (grepped for reassignment/transfer
patterns — none exist). The premise "ownership changed between enqueue and process" therefore has **no code
path to occur through today** — this is a latent gap, not a live one.

**Why it would matter later**: if a future feature adds case reassignment or multi-user firm sharing of
`predmeti` rows (already named as deferred — "Faza 1: office-scoped review queue" — in
`routers/smart_intake.py:204`), or if a future emission call site is added without first re-checking ownership,
these 5 executors would silently write Genome/Timeline/case_actions/notifications/conflict-check data
attributed to whatever `user_id`/`predmet_id` pairing was captured at emission time. Not fixed this sprint —
noted here rather than opened as new architectural debt, since the fix is well-understood (mirror the one
executor that already does it right) and small; recommend closing it opportunistically the next time any of
these 5 executors is touched, rather than as a standalone patch to 5 files for a currently-unreachable gap.

## Event Bus adversarial checklist (mission points: replay, forged event, duplicated event, reordered event)

- **Replay**: `claim_pending_events` RPC uses `SELECT...FOR UPDATE SKIP LOCKED` for cross-worker-safe claiming;
  `case_evolution_consequences` (migration 096) tracks per-`(event_id, consequence_type)` idempotency, so a
  redelivered/retried event cannot double-apply a consequence. No ownership bypass follows from a replay —
  worst case is the NEEDS-DEEPER-LOOK gap above firing again with the same (currently inert) blast radius.
- **Forged event**: not reachable — no endpoint accepts a client-supplied event row; every emission call site
  is trusted server code that already verified ownership.
- **Duplicated/reordered event**: the idempotency key above handles duplicates. Reordering (e.g. a
  `document_uploaded` event processed after a `case_closed` event) was not found to have an ownership
  consequence — every executor examined re-reads current state rather than trusting event ORDER for anything
  security-relevant.

## Race (100-parallel-requests class)

No live deployment to actually fire 100 concurrent requests against. Reasoned through the two places in this
codebase with a documented TOCTOU history: `billing.py::timer_start`'s check-then-insert race was found and
fixed in a PRIOR sprint (migration 084's partial unique index + 23505-conflict-to-409 handling) — re-verified
still correctly handled this sprint, not a fresh finding. `claim_intake_finalize`/`claim_pending_events`/
`claim_intake_job` all use `FOR UPDATE SKIP LOCKED` or a DB-level unique constraint specifically to make
concurrent-claim races safe by construction, not by application-level locking that could be raced around.

## Verdict

- **Batch ownership drift**: CERTIFIED — `finalize_intake_jobs_batch` re-checks every item independently.
- **Worker input trust**: CERTIFIED for 11/13 examined; the 2 event-consequence executors are a real but
  currently-unreachable gap, left as a documented latent issue rather than a debt-register entry (small,
  well-understood fix, not requiring a founder decision the way the sprint's other 2 debt items do).
- **Replay/forged/duplicate/reorder**: CERTIFIED — durable idempotency + no client-writable event path.
- **Race**: CERTIFIED for the one documented historical TOCTOU (already fixed in a prior sprint, re-verified);
  no new race found this sprint, reasoned at the code level only.
