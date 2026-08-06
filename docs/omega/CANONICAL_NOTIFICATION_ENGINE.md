# Canonical Notification Engine — Program Omega, Final Sprint 007 (2026-08-06)

Phase 2 (Ownership Analysis) and Phase 3 (Trigger Consolidation) deliverable. For every generator in
`TRIGGER_REGISTRY.md`, an explicit ownership classification (SOURCE / PROJECTION / DEAD / LEGACY — no
UNKNOWN), and, where 2+ systems independently detected the same underlying fact, an honest account of what
was consolidated this sprint and what was deliberately left independent, with the reasoning.

## Ownership matrix

| Generator | Ownership | Owns which fact |
|---|---|---|
| `case_actions` Canonical Action Engine | **SOURCE** | "This case has an open, actionable problem" — deadlines from `rocista`, risk findings from `identify_case_problems`. The canonical action-tracking domain. |
| `notifications.py`'s `rok`/`hitan_rok` detection | **SOURCE** | "A `predmet_hronologija` entry is due soon" — a broad, 14-writer deadline log (contract deadlines, Genome-extracted deadlines, document-extracted deadlines, the `rokovi_lanac` deadline-chain feature, etc.) |
| `_consequence_project_case_actions_to_notifications` (new) | **SOURCE** (of a projection) | "This case's canonical hearing-deadline action needs to also appear in the bell icon" — narrower, hearing-domain-only |
| `email_notif.py` cron | **SOURCE** | Its own read of `predmet_hronologija`, own 7/3/1-day cadence, own durable send-log |
| `sms.py` cron | **SOURCE** | Its own read of `predmet_hronologija`, own 48h window, own durable send-log (fixed this sprint) |
| `on_rok_kritican`/`on_health_score_promenjen`/`on_document_job_failed` | **SOURCE** | `proactive_alerts` — a genuinely different attention channel (Case Commander / firm-level alerting), not the same table as `notifications` |
| `zastarelost.py::guardian_scan` | **SOURCE**, different domain | Statute-of-limitations risk — never was, and is not made this sprint, part of the deadline-reminder lifecycle |
| `dashboard.py`'s `hitni_rokovi` | **PROJECTION** | Reads `predmet_hronologija` directly; no fact of its own |
| `inbox.py` | **PROJECTION** | Reads `predmet_dokumenti`/billing/inactivity directly; no fact of its own |
| `workspace.py` / `predmet_workspace` | **PROJECTION** | Read models over `case_actions` (canonical) |
| `shared/notify_quiet.py` | **INFRASTRUCTURE** | Not a fact-owner — shared quiet-hours check + audit log for #4/#5 |
| `shared/proactive_alerts.py` | **INFRASTRUCTURE** | Not a fact-owner — canonical WRITE PATH for `proactive_alerts`, callers own the fact |
| `api.py`'s old computed `GET /api/notifications` | **DEAD** (removed Sprint 006) | — |
| Genome/CIO/strategija GPT-advisory fields | **LEGACY-ADVISORY** (deliberate, not migrated) | Opinions embedded in a JSON response, never independently persisted as an attention row |

No entry above is UNKNOWN — every generator found this sprint resolved to one of the four categories.

## What WAS consolidated this sprint

**The hearing-deadline domain now has one canonical write path feeding two surfaces.** Before this sprint,
a lawyer saw a court-hearing deadline in Workspace (via `case_actions`, Sprint 003/004) and, separately,
potentially never saw it at all in the bell icon — `notifications.py`'s own `rok`/`hitan_rok` block reads
`predmet_hronologija`, and `kreiraj_rociste` (hearing creation, `routers/rocista.py`) never wrote to
`predmet_hronologija`. `_consequence_project_case_actions_to_notifications` (new, `services/
case_evolution.py`) closes that gap: it runs as the trailing consequence on every event that already
refreshes `case_actions` (`DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`, `ROCISTE_ZAKAZANO`,
`DOCUMENT_BATCH_COMPLETED`), and projects `case_actions`' own `PRIPREMITI_PODNESAK` rows into `notifications`
using the SAME `dedupe_key` and a DB-enforced partial UNIQUE index (migration 101, mirroring 099) — one
fact, one write, reconciled (create/update/close) rather than blindly re-inserted, every time.

## What was deliberately NOT retired, and why (a correction to Sprint 006's own `OMEGA-020`)

Sprint 006's own debt register recorded `OMEGA-020` as "up to 3 independent writes for the same deadline
fact" and suggested retiring `notifications.py`'s own detection in favor of a single `case_actions`-sourced
feed. This sprint's own deeper investigation (tracing every writer of `predmet_hronologija`, and confirming
`kreiraj_rociste`'s own actual insert statements) found this assumption too narrow: `predmet_hronologija`
is written by roughly 14 different files covering contract deadlines, Genome-extracted deadlines,
document-extracted deadlines, and a dedicated deadline-chain feature — none of which `case_actions`' own
Rule 1 reads (it reads `rocista` only). Retiring `notifications.py`'s own detection would have been a real
coverage regression: every one of those ~13 non-hearing deadline sources would silently stop producing a
bell-icon notification, with no replacement. **Decision: keep `notifications.py`'s own `predmet_hronologija`
detection unchanged; the new projection is additive, scoped only to the hearing-deadline domain where a
true duplicate-detection risk existed.** `OMEGA-020` is updated (not closed) in the Debt Register to
reflect this corrected, narrower scope.

## What remains independent, and why it is not a violation

- **`email_notif.py`/`sms.py` cron reminders** still independently query `predmet_hronologija` rather than
  reading a canonical source. This is a genuinely different CHANNEL (email/SMS delivery, with its own
  legally-relevant cadence — 7/3/1 days for email, 48h for SMS) built for a different purpose (proactive
  push outside the app) than the in-app `notifications`/`case_actions` surfaces. Unifying their trigger
  logic with `case_actions` would change WHEN a lawyer is emailed/texted — a product decision, not a
  canonicalization, and explicitly out of scope per the mission's own "no new algorithm" constraint. Their
  OWN internal duplicate-send risk (the actual notification-identity problem within each channel) is what
  this sprint fixed for SMS and confirmed already-correct for email — see
  `NOTIFICATION_DEDUPLICATION_REPORT.md`.
- **`proactive_alerts`** (`on_rok_kritican`/`on_health_score_promenjen`/`on_document_job_failed`) remains a
  separate table/channel from `notifications`. It is Case Commander / firm-level alerting, historically
  and functionally distinct (different insert schema, different consumer UI) — not a duplicate of the
  in-app bell icon. Not merged.
- **`zastarelost.py::guardian_scan`** remains fully independent — a different domain (limitation risk),
  on-demand only, no persisted state, consistent with Sprint 006's own established "don't force-merge
  genuinely different concepts" principle.

## Trigger consolidation count

Before this sprint: the hearing-deadline fact had 2 independently-computed, non-cross-referencing
representations (Workspace via `case_actions`, and — inconsistently, depending on whether
`predmet_hronologija` happened to also have an entry — the bell icon). After this sprint: 1 canonical
write (`case_actions`), 1 reconciled projection (`notifications`), sharing one dedupe identity. This is a
genuine reduction in independent trigger paths for the one fact where duplication was real and
demonstrable — not a claim that every notification-adjacent system in the repo was merged into one (see
`FORENSIC_CERTIFICATION_REPORT.md` for the honest accounting of what still exists independently, and why
each is judged legitimate rather than left out by omission).
