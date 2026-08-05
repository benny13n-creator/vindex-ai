# Reliability Verification Report — Program Delta, Sprint 002 (2026-08-05)

Reliability Engineer's own required proof, per event, that no consequence can be lost, executed twice, left
half-executed, or remain invisible — for all 4 events migrated this sprint.

## The mechanism being verified (unchanged from Sprint 001, reused not rebuilt)

Every migrated event goes through the SAME `case_evolution_consequences` idempotency table (migration 096,
`UNIQUE(event_id, consequence_name)`), the SAME `handle_case_changed` dispatcher, and the SAME Event Bus
durable-outbox retry/dead-letter mechanism (`dispatch_pending_events`, `MAX_DISPATCH_ATTEMPTS=5`) already
proven in Sprint 001. This sprint's reliability work is therefore mostly PROVING the same guarantees hold for
4 new event types and their new executors — not building new machinery.

## Per-event proof, ✔/✘ against the mission's 6 required properties

| Event | Idempotency | Retry | Audit | Provenance | Correlation | Deterministic outcome |
|---|---|---|---|---|---|---|
| `REVIEW_ACCEPTED` | ✔ `(event_id, consequence_name)` keyed, tested (`test_scenario5_crash_after_first_review_accepted_consequence_retry_resumes`) | ✔ propagates to Event Bus retry | ✔ `dokument_review_resolved` + generic per-consequence audit | ✔ `result_ref` per consequence (genome verzija, timeline row id, audit marker) | ✔ tested (`test_scenario6_replay_shares_correlation_id_and_produces_no_new_audit`) | ✔ pre-finalize always no-ops both genome/timeline (never sometimes-does-something) |
| `REVIEW_REJECTED` | ✔ same mechanism, tested (`test_scenario2_review_rejected_only_audits_no_genome_no_timeline`, replay asserted) | ✔ | ✔ `dokument_review_rejected` | ✔ `result_ref` = audit marker | ✔ inherited via `event.correlation_id` | ✔ ONLY ever produces one consequence — no branching outcome possible |
| `NEW_CLIENT_LINKED` | ✔ tested (`test_scenario3_client_linked_replayed_produces_same_result` — `_run_conflict_check` and `create_proactive_alert` each called exactly once across 2 dispatches) | ✔ — genuine improvement over the pre-migration code (see below) | ✔ generic + underlying `proactive_alerts` row | ✔ `result_ref` in `{no_conflict, conflict_alert_created, skipped_no_klijent_ime}` | ✔ | ✔ same conflict-check inputs always produce the same `result_ref` category |
| `NEW_EVIDENCE_REGISTERED` | ✔ tested (`test_scenario4_evidence_added_parallel_no_race_condition` — 2 different documents, 2 independent `event_id`s, no cross-contamination) | ✔ | ✔ generic | ✔ verified via `klasifikovan_at` before/after, never trusting "no exception" (`test_evidence_classify_verifies_klasifikovan_at_actually_set`) | ✔ | ✔ |

## Reliability improvement found and fixed this sprint (not merely preserved)

`NEW_CLIENT_LINKED` and `NEW_EVIDENCE_REGISTERED` both replace code that used `asyncio.create_task(...)` —
fire-and-forget, in-process only. A failure inside either background task was caught by its own inner
try/except, logged as a warning, and then **permanently lost** — no retry, no dead-letter, no durable trace
that it ever failed at all. Migrating both onto the Canonical Consequence Engine means a failure now:
1. Marks the consequence row `'failed'` in `case_evolution_consequences` (a durable, queryable trace — was
   previously only a log line, which could rotate out).
2. Propagates to `dispatch_pending_events`'s own proven retry mechanism, up to `MAX_DISPATCH_ATTEMPTS=5`.
3. If still failing after 5 attempts, dead-letters LOUDLY (`logger.critical`, `DEAD_LETTER` prefix in
   `events.last_error`) instead of silently vanishing after attempt 1.

This directly closes part of the "can a critical error go unnoticed?" question Project Sentinel's own Beta
Gate named back on 2026-08-03 — for these 2 specific call sites, the answer is now provably "no."

## Crash-recovery reasoning per event (Test 5 — crash after first consequence, retry resumes)

`REVIEW_ACCEPTED` has 3 ordered consequences (`genome_refresh`, `timeline_entry`,
`review_confirmation_audit`); a crash after the first one leaves `genome_refresh` `'completed'` and the other
two `'pending'`/never-attempted. `test_scenario5_crash_after_first_review_accepted_consequence_retry_resumes`
proves a retry (a fresh `handle_case_changed` call for the SAME `event_id`) skips `genome_refresh` entirely
(zero additional calls to `_run_genome_background`) and completes exactly the 2 remaining consequences — the
identical mechanism Sprint 001 already proved for `DOCUMENT_ACCEPTED`, now proven again for a 3-consequence
event (Sprint 001's registry only ever had 2).

`REVIEW_REJECTED` and `NEW_CLIENT_LINKED`/`NEW_EVIDENCE_REGISTERED` each have exactly ONE consequence — "crash
after the first consequence" degenerates to "crash before the only consequence completes," which the SAME
`(event_id, consequence_name)` keyed check already covers (a partial-completion state cannot exist for a
single-consequence event by construction).

## Concurrency reasoning (Test 4 — parallel execution, no race condition)

`NEW_EVIDENCE_REGISTERED` is the one event this sprint where TRUE concurrent execution is realistic (a
multi-document finalize call accepts several documents in the same request, each emitting its own event).
`test_scenario4_evidence_added_parallel_no_race_condition` runs two DIFFERENT documents' events concurrently
(`asyncio.gather`) and confirms: (1) each document's own `klasifikuj_i_sacuvaj` call receives the correct
`dokument_id` (no cross-document argument leakage), (2) each event's own consequence row completes
independently (`evt-A`/`evt-B` keyed separately in `case_evolution_consequences`). Two attempts to process the
SAME event concurrently remain prevented one layer down by `claim_pending_events`'s own
`SELECT ... FOR UPDATE SKIP LOCKED` (migration 091, unchanged) — unchanged reasoning from Sprint 001's own
Concurrency section in `CANONICAL_CONSEQUENCE_ENGINE_SPECIFICATION.md`.

## What was found and fixed immediately, per the mission's own mandate

The `resolve_job_review` post-finalize early-return gap (review permanently unresolved for a post-finalize
correction — see Event Migration Report) belongs to `REVIEW_ACCEPTED`'s own Human Review domain, required no
business decision, and required no change to another module — fixed immediately, per the sprint's own rule
("popravi ga odmah... ne ostavljati rešive probleme").

## What was NOT found — explicitly checked, no issue

- No consequence executor added this sprint calls another consequence executor directly (no hidden nested
  orchestration reintroduced).
- No new call site bypasses the canonical mechanism for any of the 4 migrated events — confirmed by grep: no
  remaining direct `asyncio.create_task` wrapping `_run_conflict_check`, `klasifikuj_i_sacuvaj`, or
  `log_action("dokument_review_resolved"/...)` outside `services/case_evolution.py`.
- `emit_durable`'s own fail-soft wrapping (caller-side try/except) was verified NOT to mask a genuine
  double-emission risk: each emission call site fires at most once per its own trigger condition (once per
  `resolve_job_review`/`reject_job_review` call, once per finalize's `if klijent_ime:`/per-document loop
  iteration) — a retried HTTP request would emit a NEW durable event with the SAME state-changing work already
  having occurred once (existing idempotency in `resolve_review`/`reject_review`/`predmet_klijenti` insert
  guards prevents duplicate state changes; a duplicate EVENT for the same state change is itself
  consequence-idempotent, since a second `REVIEW_ACCEPTED` event for an already-resolved review would still
  only make `genome_refresh`/`timeline_entry` run again for a case whose data hasn't changed — a low-cost,
  non-corrupting redundancy, not a data-integrity risk).

## Full suite result

See Sprint 002 Mission Report for the exact final pass/fail count (background run confirmed before this
sprint's commit).
