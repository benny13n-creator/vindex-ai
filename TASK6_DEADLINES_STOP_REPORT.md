# TASK 6 — Deadlines / rokovi architecture: LEGITIMATE STOP

Per the mandate's own explicit allowance: Task 6 may stop without implementation if no safe mechanism exists. This is a documented, evidenced STOP, not an omission.

## What exists today (all PROVEN, live-checked or directly read)

1. **No dedicated `rokovi`/`deadlines` table** — confirmed live in Task 0 (`PGRST205` for all three candidate table names against the live schema cache).
2. **`/api/dokument/rokovi`** (`routers/dokument.py:621`) — a read-only **candidate generator**. Parses a document's text for date-like deadline patterns and returns them to the caller. **Persists nothing.** A lawyer must act on the result through some other screen.
3. **Pipeline A (main auto-analyze upload, `api.py::predmet_upload_auto_analyze`)** — confirmed via code read (Task 0 §B): does **not** call any deadline extraction at all. The tuzba PDF used in Task 0's live test explicitly stated a 15-day response deadline; the resulting `case_actions` row had `"rok": null`.
4. **Pipeline C (Smart Intake, `routers/smart_intake.py:1322-1416`)** — the one real, already-hardened write path. Uses `shared/intake_extract.py::extract_deadline`, a **decision function** (not the raw candidate generator) specifically built to fix BLK-1 ("sistem izmišlja rokove" — the system used to fabricate deadlines from any date in a document; now requires actual textual evidence the date IS a deadline, per `_ima_dokaz_o_roku`). Writes only when confidence ≥ `AUTO_ACCEPT_THRESHOLD` or a human confirmed the value, with a dedup check against `predmet_hronologija` (same predmet + same date + same event name) — real defense-in-depth, not a naive insert.
   - **But it only writes to `predmet_hronologija`** (a passive timeline/chronology entry) — never to `rocista` (hearings), never directly to `case_actions`, and **does not emit any event** (no `emit_durable` call anywhere in that code block).
5. **`case_actions.rok`** is populated by exactly one rule (`_compute_target_actions` Rule 1, `case_evolution.py:883-920`) — sourced **only** from `rocista.datum`, deliberately never from a raw extracted date, per that rule's own comment ("never a GPT guess"). Since Smart Intake's extracted deadlines never reach `rocista`, they never reach this rule either.
6. **Reminder delivery infrastructure**: `/api/cron/daily` exists as a route (`api.py:1963`, intended to be triggered by an external Render.com cron per its own docstring). `EMAIL_SMTP_HOST` — **checked live against this session's own `.env`** — is **not set** (empty string). This directly reconfirms the standing `project_blk3_email_reminders` finding: SMTP is not configured at runtime, so even a fully-wired deadline-to-notification pipeline would have no delivery channel today. Whether Render's external cron is actually scheduled is infrastructure state outside this codebase and was not (cannot be) verified from here.

## Why this is a legitimate STOP, not a shortcut

Closing this gap "for real" requires at minimum:
- **A product/legal-risk decision**, not just code: should a Smart-Intake-extracted deadline (high confidence, unconfirmed by a human) ever auto-create a `rociste`/reminder-worthy obligation? BLK-1 was a real, previously-shipped incident of the system fabricating deadlines and is the reason today's `extract_deadline` is this conservative. Loosening that boundary without the founder's explicit sign-off, at the tail of a long sprint, is exactly the kind of unreviewed trust-boundary change the anti-fabrication/engineering-rigor rules governing this whole sprint exist to prevent.
- **A working delivery channel.** SMTP is not configured; wiring a full extraction → `rocista` → `case_actions.rok` → notification chain with no confirmed way to actually deliver the resulting reminder would produce a feature that looks done in the UI (an action with a `rok` shown) but silently fails to alert anyone — arguably worse than todays's honest "not wired" state, and precisely the "false success" failure class this project's own memory (`feedback_ne_trazi_sledeci_bug_trazi_klasu`, N5 false-success closures) has repeatedly flagged as the most dangerous kind of bug.

## What would be safe to do next (not attempted tonight, scoped for a future session)

1. Decide, with the founder, whether a confidence-threshold-based auto-link from Smart Intake's already-computed `predmet_hronologija` deadline entries into `rocista` is acceptable risk (the extraction logic itself is already hardened — this is a wiring decision, not a parser rewrite).
2. Confirm SMTP configuration and Render cron scheduling as separate, purely-infrastructure work (not a code change) before any reminder feature is presented to users as functional.
3. Only then wire `case_actions.rok`/priority into an actual notification, reusing the existing `notifications` table/projection pattern already proven in `services/case_evolution.py` (deadline notification projection code already exists at L1280-1345 for `rocista`-sourced deadlines — it would need extending, not inventing, once 1-2 above are resolved).

## TASK 6 GATE DECISION

**LEGITIMATE STOP — no safe mechanism to implement tonight.** Extraction logic exists and is well-hardened (BLK-1). The gap is a genuine product-risk decision plus missing infrastructure (SMTP), not a coding gap that can be closed by more code alone. Documented per the mandate's own explicit allowance; not attempted, not fabricated as done.

No push. No deploy. No code changed for this task.
