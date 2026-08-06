# Notification Deduplication Report — Program Omega, Final Sprint 007 (2026-08-06)

Phase 5's own required deliverable: prove that the same event/case/document/deadline/task never produces
2 active notifications, backed by code, tests, or reproduced scenarios — not asserted. Covers every SOURCE
generator from `TRIGGER_REGISTRY.md`.

## Mechanism-by-mechanism proof

| Generator | Mechanism | Proof |
|---|---|---|
| `case_actions` refresh | `dedupe_key` + partial UNIQUE index `idx_case_actions_open_dedupe` (migration 099), reconcile-target-vs-existing loop | Pre-existing (Sprint 003), re-verified unchanged this sprint — `tests/test_omega_sprint003_action_engine.py` |
| `_consequence_project_case_actions_to_notifications` (new) | Same `dedupe_key` reused directly + partial UNIQUE index `idx_notifications_open_dedupe` (migration 101), reconcile loop (create/update/close), benign duplicate-key-exception handling on insert | **New this sprint** — `tests/test_omega_sprint007_project_notifications.py`, 8 tests: `test_retry_100_times_still_exactly_one_notification` directly proves mission Scenario 2 for this path; `test_same_target_and_existing_key_updates_not_duplicates` proves an updated fact re-uses the same row; `test_resolved_deadline_closes_the_orphaned_notification` proves stage 8 (Resolved); `test_concurrent_duplicate_insert_is_swallowed_not_raised` proves the DB-index race path degrades gracefully, not as a crash |
| `email_notif.py` cron | `(user_id, datum_roka, dana_pre)` checked against persistent `email_notif_log` BEFORE send (`routers/email_notif.py:298`) | Pre-existing, already correct — re-verified by reading, no regression introduced this sprint (no test file existed or was added for this specific router this sprint — see Residual Gaps below) |
| `sms.py` cron | **Fixed this sprint.** Was: function-local `vec_poslato: set()`, reset every call — zero cross-invocation protection. Now: persistent batch pre-check against `notification_log` for a `rok_podsetnik:<datum>`-tagged sent/deferred row from earlier today, same pattern as email | `tests/test_omega_sprint007_sms_reminder_dedup.py`, 3 tests: `test_second_cron_run_same_day_does_not_resend_sms` directly reproduces the exact bug found (2 separate cron invocations, same day, same deadline) and proves the fix — mission Scenario 2, this pathway; `test_different_deadline_next_day_still_sends` proves the fix is scoped to the exact occurrence, not over-broad; `test_log_tip_is_date_qualified_not_the_old_bare_string` proves the persisted log key itself is correct |
| `notifications.py`'s own `rok`/`hitan_rok` computed block | Computed fresh per `GET /notifications` call from `predmet_hronologija` — not a create-a-new-row-per-occurrence generator; the SAME underlying `predmet_hronologija` row is read and re-rendered every call, never re-inserted | Not a duplicate-INSERT risk by construction (read-only computation over a table this module doesn't write to for this block) — re-verified unchanged this sprint |
| `on_rok_kritican`/`on_health_score_promenjen` | Application-level check-before-emit at the CALLER (`matter_intel.py:145-171`): queries for an existing UNREAD alert of the same `tip`+`predmet_id` before calling `emit()` | Pre-existing (Project Synapse, 2026-08-03) — **not DB-enforced**, a real TOCTOU race remains (see Concurrency Findings and Residual Gaps below); not fixed this sprint (see reasoning there) |
| `on_document_job_failed` | None found at the consequence-ledger level — relies on `fail_intake_job` RPC only being called once per job's terminal failure | Not independently re-verified against a replayed `events` row with a fresh `event_id` this sprint — named as a residual gap below, not silently assumed safe |

## The 8 mandatory scenarios — mapped to what was actually proven

| # | Scenario | Proven for | Test |
|---|---|---|---|
| 1 | New deadline → exactly one notification | `case_actions` (pre-existing), the new `notifications` projection | `test_new_open_deadline_action_creates_one_notification_with_translated_priority` |
| 2 | Same deadline, retry 100× → still one active notification | `case_actions` (pre-existing), the new `notifications` projection, SMS cron (fixed this sprint) | `test_retry_100_times_still_exactly_one_notification`, `test_second_cron_run_same_day_does_not_resend_sms` |
| 3 | Restart all workers → no new warnings | Covered by `handle_case_changed`'s own pre-existing per-`(event_id, consequence_name)` crash/retry tests (`test_delta_sprint004_certification.py`), re-verified this sprint with `project_notifications` now included in the registry | `test_full_chain_crash_after_one_consequence_real_dispatch_retry_resumes` |
| 4 | 500 documents → no event explosion | Not independently load-tested this sprint (would require a real or heavily-simulated 500-document batch run); `DOCUMENT_BATCH_COMPLETED`'s own existing design (ONE Genome recompute per batch, not per document — Omega Sprint 002/`OMEGA-001`) already structurally prevents an N-document batch from firing N independent notification-generation passes, since `project_notifications` runs once per batch dispatch, not once per document | Structural argument, not a load test — named as a residual gap below |
| 5 | Parallel upload → no duplicate attention items | The DB-level partial UNIQUE index (migrations 099/101) is the actual concurrency-safety mechanism, not application locking — proven at the unit level (`test_concurrent_duplicate_insert_is_swallowed_not_raised`), not under a real concurrent-process race | Unit-level proof of the exception-handling path; no live concurrent-process test was run this sprint (see Phase 6 below) |
| 6 | Event replay → no new notifications | `test_full_chain_replay_same_row_produces_no_duplicate_work` (updated this sprint to include `project_notifications` in its own pre-seeded completed-consequence set) | `tests/test_delta_sprint004_certification.py` |
| 7 | Crash during delivery → recovery without duplicates | Same crash-recovery test above; SMS/email's own persistent log-before-send-completion pattern (a crash between send and log-write could in principle double-send on the NEXT run — see Residual Gaps) | `test_full_chain_crash_after_one_consequence_real_dispatch_retry_resumes` |
| 8 | Manual closure → Workspace/Notification/Dashboard/Inbox immediately consistent | Workspace and the bell icon share the SAME `case_actions`-derived dedupe_key after this sprint's projection; Dashboard/Inbox remain independent PROJECTIONS reading their own source tables directly (`predmet_hronologija`, `predmet_dokumenti`) — a manual `case_actions` closure does not itself change `predmet_hronologija`, so Dashboard's own view of that underlying row is unaffected, which is CORRECT (they are different facts, not a consistency bug) | `test_resolved_deadline_closes_the_orphaned_notification` (Notification side); Workspace/Dashboard consistency reasoned from ownership matrix in `CANONICAL_NOTIFICATION_ENGINE.md`, not a dedicated cross-surface test |

## Residual gaps (named honestly, not fixed this sprint, with reasoning)

1. **`proactive_alerts`' own check-before-emit is a TOCTOU race, not a DB constraint.** Two near-simultaneous
   case-opens for the same predmet could both pass the "no existing unread alert" check before either
   insert completes, producing 2 rows. `shared/proactive_alerts.py::create_proactive_alert` has no
   `dedupe_key`/unique-index concept at all (Program Alpha's own 2026-08-04 consolidation covered the write
   PATH, not idempotency). Fixing this properly would mean a new migration (dedupe_key column + partial
   unique index on `proactive_alerts`, mirroring 099/101) plus updating 3 callers — a real, scoped, safely-
   plannable fix, but larger than this sprint's remaining time budget allowed to implement AND fully test
   with the same rigor as the SMS fix. Recorded as a new debt item (`OMEGA-023`) rather than silently left
   out.
2. **`on_document_job_failed` has no consequence-ledger idempotency check** — unlike every
   `CONSEQUENCE_REGISTRY`-registered consequence, it is a direct Event Bus subscriber with no
   `(event_id, consequence_name)` guard of its own. A duplicate `events` row for the same failed job
   (a genuinely rare but not impossible case — e.g., a retried `fail_intake_job` RPC call) could produce 2
   `proactive_alerts` rows. Recorded as `OMEGA-024`.
3. **500-document batch / true concurrent-process races** were reasoned about structurally, not exercised
   under real load or with real parallel OS processes — the unit tests prove the exception-handling CODE
   PATH is correct, not that a live Postgres instance under real concurrent connections behaves identically
   (a reasonable, standard limitation of unit-level proof, not a false claim of full load-test coverage).
4. **A crash between `_send_sms`/`_smtp_send` succeeding and `log_notification`/`email_notif_log.insert`
   completing** could in principle cause a duplicate send on the next cron run (the message went out, but
   the log write that would have prevented a resend never happened). This is a pre-existing risk in BOTH
   the email and SMS patterns (log-after-send, not a single atomic operation) — not introduced or worsened
   by this sprint's fix, and outside this sprint's scope to redesign (would require a different delivery
   architecture, e.g. log-before-send with a "sending" state) — recorded as `OMEGA-025`.
5. **`notification_log` (SMS) and `email_notif_log` (email) have NO unique DB constraint** — confirmed by
   reading `migrations/048_reliability_hardening.sql:108-127` (regular indexes only, no `UNIQUE`). Their
   dedup is a SELECT-then-INSERT check at the application level, exactly like `proactive_alerts` (gap #1)
   — safe against 2 sequential invocations (today's fix/pre-existing pattern), but NOT safe against 2
   truly concurrent invocations racing past the SELECT before either INSERT lands. Unlike `case_actions`/
   `notifications`, which get this guarantee for free from migrations 099/101's own partial UNIQUE
   indexes, no equivalent exists here. Not fixed this sprint — a unique constraint on either log table
   needs careful design (both tables intentionally allow multiple legitimate rows per user/day, e.g.
   `deferred_quiet_hours` followed later by `sent`), which is a real schema decision, not a
   canonicalization, and was judged too risky to guess at in the time remaining. Recorded as `OMEGA-026`.
   In practice, both cron endpoints are invoked by GitHub Actions on a fixed schedule (not
   naturally concurrent) — real-world exposure is low, but not zero (an overlapping manual re-run during
   a slow batch would still race).
