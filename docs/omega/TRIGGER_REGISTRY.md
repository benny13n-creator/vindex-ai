# Trigger Registry — Program Omega, Final Sprint 007 (2026-08-06)

Phase 1's own required deliverable: every mechanism, repo-wide, that GENERATES a notification, alert,
badge, warning, reminder, toast, dashboard card, workspace item, inbox item, email reminder, morning
briefing entry, Case Commander entry, or health alert — "no exceptions." Builds directly on Sprint 006's
own `ATTENTION_SURFACE_REGISTRY.md` (which catalogued every priority VOCABULARY/ORDER dict) — this
registry catalogues the GENERATORS themselves and, for each, whether it independently decides to create a
user-facing attention item, and how (or whether) it protects against creating a duplicate one. Every claim
below cites a file:line actually read this sprint.

## Legend

- **SOURCE** — independently decides a fact is true and creates/updates a persisted, addressable
  attention item (a DB row) as a direct result.
- **PROJECTION** — reads an existing SOURCE's own data and renders/derives a view over it; creates no new
  fact and (before this sprint, for one case) no new persisted row.
- **DEAD** — code exists, is reachable, but is never actually invoked by anything live (zero callers).
- **INFRASTRUCTURE** — shared utility other generators call; does not itself decide facts.

## Generators

| # | Generator | File:line | Persists to | Type | Idempotency mechanism | Notes |
|---|---|---|---|---|---|---|
| 1 | `case_actions` Canonical Action Engine (`_compute_target_actions`, `_consequence_refresh_case_actions`) | `services/case_evolution.py` (Sprint 003) | `case_actions` | **SOURCE** | `dedupe_key` + partial UNIQUE index `idx_case_actions_open_dedupe` (migration 099) — DB-enforced, race-safe | The canonical deadline/problem-detection algorithm this whole engagement anchors on. Reads `rocista` (hearings) + `identify_case_problems` (risk engine) — NOT `predmet_hronologija`. |
| 2 | `notifications.py::_generate_notifications` — `rok`/`hitan_rok` block | `routers/notifications.py` (pre-existing, priority bug fixed Sprint 006) | `notifications` | **SOURCE** | None found — computed fresh on every `GET /notifications` call, not persisted as a distinct row per occurrence (see `NOTIFICATION_DEDUPLICATION_REPORT.md` for the exact mechanics) | Reads `predmet_hronologija` — a general 14-writer deadline log, NOT the same fact space as `rocista`. Kept this sprint (see Ownership Analysis, `CANONICAL_NOTIFICATION_ENGINE.md`) — retiring it would regress coverage for every non-hearing deadline source. |
| 3 | `_consequence_project_case_actions_to_notifications` (**NEW this sprint**) | `services/case_evolution.py` | `notifications` | **SOURCE** (of a projection) | `dedupe_key` (reused directly from `case_actions`' own key) + partial UNIQUE index `idx_notifications_open_dedupe` (migration 101) — DB-enforced, race-safe | Closes `OMEGA-020` for the hearing-deadline domain specifically: same fact now visible in Workspace AND the bell icon, one write path, no duplicate. Additive to #2, not a replacement (different, non-overlapping fact space — see Ownership Analysis). |
| 4 | `email_notif.py::posalji_podsetnike` (cron) | `routers/email_notif.py:255-339` | `email_notif_log` (audit) → SMTP send | **SOURCE** | `(user_id, datum_roka, dana_pre)` checked against `email_notif_log` BEFORE sending (line 298) — persistent, cross-run, already correct | Reads `predmet_hronologija` directly (own independent query, own thresholds: 7/3/1 days). Was already the correct pattern this sprint's SMS fix was modeled on. |
| 5 | `sms.py::posalji_podsetnike` (cron) | `routers/sms.py:217-369` | `notification_log` (audit) → Twilio SMS/WhatsApp | **SOURCE** | **FIXED this sprint** — was a function-local Python `set()` (`vec_poslato`), reset every call, zero cross-invocation protection (real bug, mission Scenario 2 failure). Now also checks `notification_log` for a `rok_podsetnik:<datum>`-tagged sent/deferred row from earlier today before sending — same pattern as #4. | Reads `predmet_hronologija` directly, own independent query (48h window, `vaznost="kritičan"` only). |
| 6 | `on_rok_kritican` (Event Bus handler) | `services/event_bus.py:109-169` | `proactive_alerts` | **SOURCE** | None inside `create_proactive_alert` itself (unconditional insert) — dedup happens at the EMITTER (`routers/matter_intel.py:157-171`): checks for an existing UNREAD `tip="rok_kritican"` alert for the same predmet before calling `emit()` at all | Emitted only from `matter_intel.py`'s own `_maybe_emit_health_and_deadline_events`, itself only fired from `get_matter_intel` (case-open). Application-level check-then-emit, not DB-enforced — a real TOCTOU race window exists between two near-simultaneous case-opens (see Concurrency findings). |
| 7 | `on_health_score_promenjen` (Event Bus handler) | `services/event_bus.py:202-226` | `proactive_alerts` | **SOURCE** | Same pattern as #6 — emitter-side check (`matter_intel.py:145-155`), same TOCTOU gap | Different fact (health score < 30), same infrastructure and same gap as #6. |
| 8 | `on_document_job_failed` (Event Bus handler) | `services/event_bus.py:229-` | `proactive_alerts` | **SOURCE** | None found — fires once per `DocumentJobFailed` event, and `fail_intake_job` RPC (migration 073) is itself only called once per job (a job cannot fail twice from the same terminal state) | Durable-outbox-connected (unlike #6/#7), so retried via `dispatch_pending_events()`'s own outer retry — but `case_evolution.py`'s per-`(event_id, consequence_name)` idempotency ledger does NOT cover this handler (it is not registered in `CONSEQUENCE_REGISTRY`; it is a direct Event Bus subscriber). A replayed/duplicate `events` row with a fresh `event_id` for the same job would create a second alert — see Forensic Certification. |
| 9 | `zastarelost.py::guardian_scan` | `routers/zastarelost.py:464-` | Nothing (on-demand response only) | **SOURCE**, different domain | N/A — stateless, computed fresh per request, nothing persisted | Own 4th priority vocabulary (`kritično/hitno/prati/ok`, line 525). Statute-of-limitations risk, not a deadline reminder — deliberately not merged into the canonical model (Sprint 006's own documented distinction extends here). |
| 10 | `routers/dashboard.py`'s `hitni_rokovi` widget | `routers/dashboard.py:41-301` | Nothing (response only) | **PROJECTION** | N/A — read-only query over `predmet_hronologija`, same source table as #2, own inline ≤2-day threshold | No persisted row; pure presentation. Confirms `OMEGA-021`'s own finding (day-count thresholds disagree across systems) still applies. |
| 11 | `routers/inbox.py::unified_inbox` | `routers/inbox.py:55-` | Nothing (response only) | **PROJECTION** | N/A — read-only, computes `dokument`/`naplata`/`neaktivan` items fresh per request | Sprint 005 already narrowed this away from `rociste`/`rok` items — no overlap with #1-#5 today. |
| 12 | `routers/workspace.py::get_workspace` | `routers/workspace.py` (Sprint 004/005) | Nothing (response only) | **PROJECTION** | N/A — reads `case_actions` (canonical) + `zadaci`, translates via `shared/attention_priority.py` | The canonical portfolio-wide "what needs attention" read model this whole Program Omega arc has built toward. |
| 13 | `api.py::predmet_workspace` (Cockpit) | `api.py:4944-` | Nothing (response only) | **PROJECTION** | N/A | Per-CASE detail aggregation, name-collides with #12 but different scope (`OMEGA-022`, unchanged). |
| 14 | `shared/notify_quiet.py` (`is_quiet_now`/`log_notification`) | `shared/notify_quiet.py` | `notification_log` | **INFRASTRUCTURE** | N/A — itself the audit substrate #4/#5 dedup against | Used by `routers/sms.py` and `routers/portal_monitoring.py`. Not a generator itself. |
| 15 | `shared/proactive_alerts.py::create_proactive_alert` | `shared/proactive_alerts.py:50-` | `proactive_alerts` | **INFRASTRUCTURE** | None (unconditional insert + retry) — dedup is the CALLER's responsibility (see #6/#7/#8) | Canonical single write-path for `proactive_alerts` (Program Alpha, 2026-08-04) — already consolidated from 12 independent call sites down to 1 function. Idempotency was never part of that consolidation's own scope. |
| 16 | `api.py::GET /api/notifications` (computed, dead) | *(deleted Sprint 006)* | — | **DEAD** (removed) | — | Confirmed already retired — listed here only for completeness against the mission's "no exceptions" mandate. |

## Genome/GPT-advisory fields (not wired to delivery — documented, not re-litigated)

`case_dna.upozorenja`/`najslabija_tacka`/`nedostaje[].hitnost` (`routers/case_dna.py`), `routers/cio.py`'s
`kriticnost`, `routers/strategija.py`'s `sledeci_koraci[].prioritet` — all GPT-advisory output embedded in
a JSON response, never independently inserted as a notification/alert row. Re-confirmed unchanged from
Sprint 006's own `ATTENTION_SURFACE_REGISTRY.md` — see Phase 7 (AI Governance) below for this sprint's own
re-verification.

## Scheduling — confirmed, no Python-level scheduler exists

`grep -rln "APScheduler\|apscheduler\|croniter\|BackgroundScheduler"` across the entire repo: zero matches.
Every periodic generator (#4 email, #5 SMS, and any weekly-digest/onboarding-cron variants in
`email_notif.py`) is driven externally by GitHub Actions cron workflows
(`.github/workflows/{sms,email}-cron.yml`) issuing authenticated HTTP POSTs to the dedicated FastAPI
endpoints above. There is no in-process timer that could itself double-fire; the ONLY duplicate-invocation
risk is an external cron misfire or manual re-trigger — which is exactly what #4's pre-existing pattern and
#5's fix this sprint both defend against.

## Toast/WebSocket/SSE — time-boxed, not exhaustively re-verified this sprint

Sprint 006's own Phase 1 forensic pass (`ATTENTION_SURFACE_REGISTRY.md`) already covered every
priority/warning-producing surface repo-wide. This sprint's own Phase 1 pass targeted specifically the
GENERATION/PERSISTENCE layer above (table writes) rather than re-auditing every frontend polling/toast call
site in `static/vindex.js` from scratch — `static/vindex.js::notif_load()` (bell icon) and the dashboard's
own polling both read the SOURCE tables above, not an independent client-side timer that invents its own
attention items. One WebSocket endpoint exists repo-wide (`routers/voice_realtime.py`, `WS
/api/voice/realtime/ws`) — confirmed unrelated to notifications/alerts (a realtime voice-session channel);
no SSE push channel exists. Named honestly, not hidden: a full poll-site-by-poll-site frontend audit was
out of this sprint's time budget.
