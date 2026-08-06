# Event Lifecycle Specification — Program Omega, Final Sprint 007 (2026-08-06)

Phase 4's own required deliverable: formalize Business Event → Canonical Trigger → Priority Engine →
Notification Engine → Workspace → Dashboard → Read → Resolved → Archived, with one owner, one input, and
one output per stage. Written against the actual, live architecture (verified this sprint) — not an
aspirational redesign. Where the real system's states do not match the mission's own 9-stage template
exactly, that gap is named explicitly rather than glossed over.

## The canonical chain, as it actually exists today

```
Business Event                Canonical Trigger              Priority Engine
(outbox row, events table)    (handle_case_changed,           (shared/attention_priority.py)
        │                      services/case_evolution.py)            │
        │  owner: whatever emits           │  owner: case_evolution.py│  owner: attention_priority.py
        │  (smart_intake.py,               │  (the ONE dispatcher —   │  (pure lookup/translation,
        │   rocista.py, ...)               │   Program Delta/Omega)   │   no new computation)
        ▼                                  ▼                          ▼
  Event(type, event_id, ...)   CONSEQUENCE_REGISTRY[type]     CANONICAL_ORDER /
                                → genome_refresh               CANONICAL_TO_NOTIFICATIONS
                                → timeline_entry                       │
                                → refresh_case_actions ─────► case_actions.prioritet
                                → project_notifications ────► notifications.prioritet (NEW)
                                                                        │
                                                                        ▼
                                                          Notification Engine
                                                (case_actions row + notifications row,
                                                 both dedupe_key-reconciled)
                                                                        │
                              ┌─────────────────────────────────────────┼───────────────┐
                              ▼                                         ▼               ▼
                        Workspace                                 Dashboard          Bell icon
                   (GET /api/workspace,                       (routers/dashboard.py,  (GET /notifications,
                    reads case_actions)                        reads predmet_          reads notifications)
                                                                 hronologija directly)
```

## Per-stage owner/input/output

| Stage | Owner | Input | Output | File |
|---|---|---|---|---|
| Business Event | Whatever domain action occurred (document accepted, review resolved, hearing scheduled, batch finalized) | The domain action itself | A durable row in `events` (outbox) | `smart_intake.py`, `rocista.py`, etc. — via `services/event_bus.py::emit`/`publish` |
| Canonical Trigger | `handle_case_changed` | `Event(type, event_id, predmet_id, payload)` | Executes the type's own `CONSEQUENCE_REGISTRY` list, sequentially, each idempotency-checked per `(event_id, consequence_name)` | `services/case_evolution.py:987-` |
| Priority Engine | `shared/attention_priority.py` | A source vocabulary's own value (e.g. `case_actions.prioritet`) | The canonical value + (this sprint) its translation into `notifications.prioritet`'s own vocabulary | `shared/attention_priority.py` |
| Notification Engine | `_consequence_refresh_case_actions` (case_actions) + `_consequence_project_case_actions_to_notifications` (notifications, NEW) | The freshly-recomputed Genome/risk facts | Reconciled (create/update/close) rows in `case_actions` and `notifications`, both dedupe_key-keyed | `services/case_evolution.py` |
| Workspace | `GET /api/workspace` | `case_actions` (open rows) | Portfolio-wide "what needs attention" read model | `routers/workspace.py` |
| Dashboard | `routers/dashboard.py` | `predmet_hronologija` directly (own query, own ≤2-day threshold) | A presentational summary card | `routers/dashboard.py` |
| Read | `procitano` boolean on `notifications`; no equivalent field exists on `proactive_alerts` beyond its own `procitana` | User marks read (frontend) or the reconcile loop closes an orphaned row | Row updated in place | `routers/notifications.py`, `_consequence_project_case_actions_to_notifications`'s own closing loop |
| Resolved | `case_actions.status = 'closed'`, `closed_at` set | The underlying fact (deadline passed, hearing occurred, problem no longer detected) stops appearing in `_compute_target_actions`' own target set | Row updated, `closed_at` timestamped | `services/case_evolution.py:752` |
| Archived | **Does not exist as a distinct state** — see Honest Gap below | — | — | — |

## Honest gap: no formal "Archived" state

Neither `case_actions` (`open`/`closed` only) nor `notifications` (`procitano` boolean only) has a
third, separate "archived" status distinct from "resolved"/"read." The mission's own 9-stage template
names Archived as its own stage; the real architecture collapses Resolved and Archived into one state per
table. This is not a bug — a lawyer has no current need to distinguish "this deadline passed" from "this
deadline passed AND I've filed it away" — but it is a real, not-invented gap between the template and the
live system, named here rather than silently assumed away. No new column was added to manufacture a
distinction the product does not currently need (would violate the mission's own "no new functions beyond
what's needed" — no evidence a lawyer has ever asked for a 3rd state).

## Cross-channel note: email/SMS reminders are NOT part of this chain

`email_notif.py`/`sms.py` cron reminders sit OUTSIDE this lifecycle entirely — they read
`predmet_hronologija` directly on their own cadence (7/3/1 days, 48h respectively), independent of the
Canonical Trigger/`case_actions`/`notifications` chain above. This is a deliberate, documented boundary
(see `CANONICAL_NOTIFICATION_ENGINE.md`), not an omission — they are a different delivery CHANNEL
(push-outside-the-app) with their own already-adequate (email) or now-fixed (SMS) internal idempotency, not
a duplicate of the in-app attention lifecycle.
