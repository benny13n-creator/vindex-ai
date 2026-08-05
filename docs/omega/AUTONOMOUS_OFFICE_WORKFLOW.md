# Autonomous Office Workflow — Program Omega, Master Sprint 001 (2026-08-06)

Agent 1's own deliverable: the ideal advocate-facing workflow, and how close this sprint brings the platform
to it. Written from the lawyer's own perspective, not the system's.

## The scenario, walked through

**A lawyer receives a new client folder: 500 scanned documents — judgments, complaints, submissions,
contracts, evidence, correspondence, minutes, no organization at all.**

### Before this sprint

1. Lawyer uploads via the dropzone. If the batch is large, the request may simply fail with a connection
   error partway through, with no indication of what succeeded.
2. Once uploaded, the lawyer must open EACH of up to 500 jobs individually, check its status, resolve review
   flags one at a time, and click "finalize" 500 separate times.
3. There is no single view of the outcome — the lawyer must piece together what happened by visiting each
   resulting case individually.

### After this sprint

1. Lawyer uploads the folder in one action. If the batch is large enough to risk a timeout, the system
   returns an honest "processed N so far, continuing with the rest" response instead of failing silently —
   the frontend can automatically resubmit the remainder with zero risk of duplicating already-accepted files.
2. Background processing (OCR, segmentation, classification) proceeds without the lawyer's attention, exactly
   as before this sprint (already automatic, Program Intake's own work).
3. Once ready, ONE call — `POST /jobs/finalize-batch` — finalizes everything and returns ONE summary:
   - How many documents were processed.
   - Which cases they landed in (existing cases correctly re-identified, new cases correctly created —
     Ownership Resolution, unchanged, already reliable).
   - How many need the lawyer's review.
   - How many deadlines were added.
   - A note that deeper case intelligence (contradictions, missing evidence) is finishing up and will be on
     the case page shortly.
4. Genome, Timeline, Evidence classification, and conflict-of-interest alerts all update automatically in the
   background — already true before this sprint (Program Delta), unaffected by Omega.

### What is still NOT automatic, honestly

- **Tasks are not created automatically** from any of this. A lawyer reviewing "7 missing pieces of evidence"
  today has to manually create follow-up tasks — the mission's own Priority 4 ("automatski rokovi i zadaci")
  is only half-true: deadlines that are DIRECTLY EXTRACTED from a document ARE added automatically; tasks
  reacting to what the system NOTICED (missing evidence, contradictions) are not.
- **The exact numbers in the mission's own example** ("2 potencijalno propuštena roka, 7 nedostajućih dokaza,
  4 kontradikcije") are not literally returned in the same response as the batch summary — they require a
  follow-up visit to the case page, once Genome's own async refresh has caught up (typically a few seconds
  per touched case).

## The Omega Principle, checked against what was built

*"Nema novih izolovanih funkcija. Svaka nova sposobnost mora biti uklopljena u postojeći tok."*

Both fixes this sprint are pure orchestration on top of EXISTING, already-hardened mechanisms:

- The upload time-budget change adds zero new business logic — it only changes WHEN the existing per-file
  loop returns a response.
- `finalize-batch` calls the EXACT SAME `_finalize_intake_job_core` logic the single-job endpoint already
  used, per job, unchanged. Nothing about Genome, Timeline, Evidence, or Alerts was touched, extended, or
  duplicated.

Neither fix introduced a new AI capability, a new dashboard panel, a new chatbot function, or anything outside
what the mission explicitly asked for.

## What Agent 1 would flag as the next highest-leverage Omega mission

Given the scenario walked through above, the single biggest remaining gap between "the system organizes
itself" and "the lawyer still does manual work" is **Task creation from noticed problems** (missing evidence,
contradictions, deadline risk) — not a new AI capability (the DETECTION already exists, per
`CASE_INTELLIGENCE_AUTOMATION_REPORT.md`), but a missing CONSEQUENCE wiring: "problem noticed" should become
"a task exists," automatically, the same way "document accepted" already becomes "Genome refreshed." This is
named as the clear next step, not attempted in this sprint (a real design decision — which detected problems
warrant an auto-created task, versus which should stay a passive dashboard signal — deserves its own scoped
mission, not a rushed addition here).
