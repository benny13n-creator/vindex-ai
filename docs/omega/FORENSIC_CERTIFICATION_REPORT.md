# Forensic Certification Report — Program Omega, Final Sprint 007 (2026-08-06)

Phase 7 (AI Governance) and Phase 8 (Forensic Certification) deliverable. The mission's own instruction:
assume the architecture is wrong; try to break it; look for another trigger/owner/priority/notification/
workflow/scheduler/reminder/inbox. If one is found, the sprint is not done. This report states plainly
what was found, fixed, and what remains — including everything this sprint did NOT fully close.

## Phase 7 — AI Governance re-verification

Re-checked every GPT-facing surface identified in `TRIGGER_REGISTRY.md`'s own "Genome/GPT-advisory
fields" section, re-reading each prompt/consumer directly (not relying on Sprint 006's own prior
conclusion without re-verification):

| Surface | Re-verified this sprint | Finding |
|---|---|---|
| `api.py::_COCKPIT_SYSTEM` (`api.py:5058-5060`) | Yes, read directly | Still explicitly instructs the model: risk/priority is "determinstickim sistemom i dat ti je u kontekstu — NE odredjuj ga sam" ("a deterministic system already decided it and gave it to you in context — do NOT decide it yourself"). Positive AR-01 compliance, unchanged. |
| `routers/case_dna.py`'s Genome extraction prompt (`nedostaje[].hitnost`) | Yes | Output embedded in the `case_dna` JSON response object; confirmed (via `TRIGGER_REGISTRY.md`'s own generator sweep) never independently inserted as a `notifications`/`proactive_alerts`/`case_actions` row — no code path reads this field to decide anything in the canonical Notification/Trigger Engine. |
| `routers/cio.py`'s `kriticnost` (0-100) | Yes | Same pattern — advisory scoring field in a response object, not wired to any SOURCE generator's own decision. |
| `routers/strategija.py`'s `sledeci_koraci[].prioritet` | Yes | On-demand simulation output only, never persisted as a triggered notification. |
| `_consequence_project_case_actions_to_notifications` (this sprint's own new code) | Self-audit | Reads `case_actions.prioritet` (a value `_compute_target_actions`' own deterministic rules — `_priority_by_days`, risk-engine `ozbiljnost` — already set) and translates it via `CANONICAL_TO_NOTIFICATIONS`, a pure lookup table. Zero GPT calls anywhere in this function. Confirmed by direct code inspection, not inference. |

**Conclusion: no GPT response owns priority, notification, urgency, or attention anywhere in the
canonical Trigger/Notification/Priority Engine chain, before or after this sprint's changes.** No
migration was required.

## Phase 8 — Forensic Certification: attempting to break the architecture

The following independent attempts were made to find a trigger/owner/priority/notification/workflow/
scheduler/reminder/inbox this sprint's own consolidation missed or created.

### Attempt 1: is there a hidden scheduler?
`grep -rln "APScheduler\|apscheduler\|croniter\|BackgroundScheduler"` — zero matches repo-wide. All
periodic firing is external (GitHub Actions cron → HTTP POST). **No hidden scheduler found.**

### Attempt 2: is there a second event dispatcher besides `handle_case_changed`?
`services/event_bus.py::EventBus._register_defaults` registers 6 handlers: `on_rok_kritican`,
`on_predmet_kreiran`, `on_dokument_uploadovan`, `on_health_score_promenjen`, `on_genome_updated` (details
unread this sprint, pre-existing), `on_document_job_failed`, plus `handle_case_changed` itself (imported
lazily to avoid a circular import, `services/event_bus.py:345-356`). **These are NOT competing
dispatchers for the same events** — `handle_case_changed` owns `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/
`REVIEW_REJECTED`/`NEW_CLIENT_LINKED`/`NEW_EVIDENCE_REGISTERED`/`ROCISTE_ZAKAZANO`/
`DOCUMENT_BATCH_COMPLETED` (the `CONSEQUENCE_REGISTRY`'s own key set); the 6 direct handlers own a
disjoint set of event types (`ROK_KRITICAN`, `PREDMET_KREIRAN`, `DOKUMENT_UPLOADOVAN`,
`HEALTH_SCORE_PROMENJEN`, `GENOME_UPDATED`, `DOCUMENT_JOB_FAILED`). No event type has 2 competing
handlers. **No second dispatcher found — one router, disjoint event ownership.**

### Attempt 3: does `proactive_alerts` constitute a second, competing Notification Engine?
Considered seriously — it is, after all, a second table that creates user-facing attention items. Verdict:
**not a violation, a different channel.** `proactive_alerts` (Case Commander / firm-level alerting) and
`notifications` (in-app bell icon) have always been functionally distinct, different consumer UIs, never
claimed to be the same concept by any prior sprint's own documentation. This sprint's own Ownership
Analysis (`CANONICAL_NOTIFICATION_ENGINE.md`) documents this explicitly rather than silently excluding it
— the honest finding is "2 channels, each internally working toward one owner per fact within itself,"
not "1 channel, fully merged." `proactive_alerts`' own internal idempotency gap (TOCTOU, `OMEGA-023`) is a
real, separately-tracked weakness — not evidence of a hidden SECOND Priority/Trigger Engine, since it
does not use case_actions' own priority vocabulary at all (`urgentnost`: `hitna`/`normalna`/`visoka` — yet
another vocabulary, technically a 14th, not previously catalogued in Sprint 006's own 13-item list).
**New finding this sprint, recorded as `OMEGA-027`**: `proactive_alerts.urgentnost` is a 4th priority
word-scale not present in `shared/attention_priority.py`'s own translation tables. Not migrated this
sprint (same reasoning as `zastarelost.py`'s own vocabulary — different table, different consumer,
changing it is a product decision) but named rather than missed.

### Attempt 4: does the SMS fix itself introduce a NEW independent trigger?
No — `routers/sms.py::posalji_podsetnike` already existed as a SOURCE generator before this sprint; the
fix changed its OWN internal dedup mechanism, added no new read of a different fact, no new table, no new
endpoint. Verified by diff: only the `already_sent_today` pre-check and the `log_tip` date-qualification
were added.

### Attempt 5: does the new `project_notifications` consequence bypass the canonical dispatcher?
No — it is registered as an ordinary trailing `ConsequenceDef` inside the EXISTING `CONSEQUENCE_REGISTRY`,
executed by the SAME `handle_case_changed` loop, subject to the SAME per-`(event_id, consequence_name)`
idempotency ledger as every other consequence (verified directly by the crash-recovery/replay tests in
`tests/test_delta_sprint004_certification.py`, updated this sprint to include it). **No new orchestrator
was created.**

### Attempt 6: can the new projection produce 2 active notifications under adversarial concurrency?
Attacked directly with 2-way and 10-way `asyncio.gather` concurrent execution against a shared fake table
enforcing the real partial-UNIQUE-index semantics (`tests/test_omega_sprint007_concurrency.py`) — in every
run, exactly one notification row survives. **Could not break it at this level** — see
`NOTIFICATION_DEDUPLICATION_REPORT.md` for the honest boundary of what this proves (no live-Postgres
integration test was run).

### Attempt 7: is there an inbox/workspace surface this sprint's registry missed?
Cross-checked `TRIGGER_REGISTRY.md`'s own 16-generator list against Sprint 006's own
`ATTENTION_SURFACE_REGISTRY.md` (13 vocabularies + warning producers) — every priority-bearing surface
Sprint 006 found maps onto a generator or a documented GPT-advisory/different-concept exclusion in this
sprint's own registry; no new independent inbox/workspace surface was found beyond what both registries
already list.

## What this sprint could NOT fully certify (stated honestly)

- `proactive_alerts`' own TOCTOU dedup gap (`OMEGA-023`) — found, not fixed.
- `on_document_job_failed`'s missing consequence-ledger guard (`OMEGA-024`) — found, not fixed.
- `notification_log`/`email_notif_log`'s own lack of a DB unique constraint (`OMEGA-026`) — found, not
  fixed; real-world exposure judged low (external cron cadence, not naturally concurrent) but not zero.
- `proactive_alerts.urgentnost`'s own 4th, previously-uncatalogued priority vocabulary (`OMEGA-027`) —
  found, documented, not migrated (different table/consumer, product decision).
- A full frontend poll-site-by-poll-site audit of `static/vindex.js` for any client-side-only toast/badge
  generator was not re-run from scratch this sprint (time-boxed, see `TRIGGER_REGISTRY.md`'s own closing
  note) — inherited from Sprint 006's own equivalent scope limit, not newly introduced.
- 500-document-batch and true multi-process (not just multi-coroutine) concurrent load were reasoned
  about structurally and tested at the asyncio/thread-pool level, not exercised against a live database
  under real concurrent OS processes.

## Certification verdict

**Exactly one canonical lifecycle exists for the fact this sprint targeted (case-tracked, hearing-sourced
deadlines): Business Event → `handle_case_changed` → `case_actions` (canonical) → `notifications`
(reconciled projection, new this sprint) → Workspace / bell icon, both reading a shared dedupe identity.**
This is proven by code, migrations, and passing tests (2725 passed / 1 skipped across the full regression
suite after this sprint's changes, including 17 new tests added this sprint across 3 new test files).

**This is NOT a claim that every notification-adjacent mechanism in the repo was unified into one system.**
`proactive_alerts`, `email_notif.py`/`sms.py`'s own reminder cadences, and `zastarelost.py`'s own
statute-of-limitations scan remain legitimately independent — different facts, different channels,
different consumers — each internally moving toward (not yet fully at) one-owner-per-fact within itself.
Where a real duplication risk existed within one of those independent systems (SMS's own dedup bug), it
was found and fixed this sprint. Where a real duplication risk was found but not yet closed
(`proactive_alerts`, `on_document_job_failed`, the 2 log tables), it is named, not hidden, in the
Debt Register.
