# Mission Review — ZTC-001: Multi-document-to-one-case attach (Scenario B)

**Mission Board entry:** `MISSION_BOARD.md`, ZTC-001.
**Executed by:** Operation Autonomous Law Office (BETA-002), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### The bug
`POST /api/smart-intake/jobs/{id}/finalize` always inserted a new `predmeti` row (Rule: one document
in, one case out — no exceptions). `FinalizeReq` had no way to say "attach this document's job to a
case that already exists." Given the batch-upload contract already returns one `job_id` per file
(`routers/smart_intake.py:99`), a lawyer uploading 10 pages of one client's matter — exactly the kind
of upload the founder's Zero-Touch Case journey describes — would get **10 separate cases**, not one
organized case, with no merge/consolidation feature anywhere in the repo to recover afterward.
Confirmed the single most consequential finding against BETA-002's stated success criterion.

### The fix
Added `predmet_id: Optional[str]` to `FinalizeReq`. When present, `finalize_intake_job` verifies the
target case exists and belongs to the caller (`.eq("id", body.predmet_id).eq("user_id", uid)` —
tenant-scoped, same discipline as every other lookup in this file), then attaches the document to it
instead of creating a new `predmeti` row. Omitting the field preserves the exact prior behavior
(new case every time) — this is additive, not a breaking change to the existing single-document flow.

### A second bug found while implementing the first
`predmet_dokumenti`'s insert hardcoded `redni_broj: 1` for every document. Harmless while every case
had exactly one document; the moment two documents can share a case (the whole point of this fix),
every subsequent document would collide on `redni_broj=1`, making Case Genome's
`.order("redni_broj")` sort meaningless. Fixed by querying the target case's current max `redni_broj`
and incrementing — same fix location, same user-facing scenario, per this project's own ticket-
scoping rule ("same user-facing functionality = same ticket, not same bug class").

### Alternatives considered
- **A dedicated `POST /jobs/batch-finalize` endpoint** taking a list of job_ids + one shared naziv.
  Rejected for tonight: bigger API surface change, and the per-job `predmet_id` attach approach lets
  the *first* finalize call create the case (so the lawyer still names/reviews it normally) and every
  subsequent call simply attach — no new endpoint, no new contract shape, smaller diff.
- **A case-merge/consolidation endpoint** to fix already-created duplicate cases after the fact.
  Real, and named in the investigation as a gap (no `spoji_predmet`/`merge_predmet` exists) — but
  that's a recovery tool for a bug this fix prevents going forward, not part of preventing the bug
  itself. Left as a smaller, separate future item, not attempted tonight.

---

## Implementation
`routers/smart_intake.py` — `FinalizeReq` gains `predmet_id`; `finalize_intake_job` branches on
whether it was provided (attach vs. create); `redni_broj` computed from the target case's existing
documents instead of hardcoded.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer uploads 3 pages of one client's lawsuit as 3 separate
files (Scenario B). The first finalize call (no predmet_id) creates the
case. The lawyer's UI (once wired -- see the frontend Blocker Report) would
call finalize on the remaining 2 jobs WITH the returned predmet_id.

Before this fix: 3 finalize calls -> 3 separate predmeti rows. The lawyer
now has to notice and manually consolidate 3 "cases" that are really one.
After this fix: 3 finalize calls, first creates, next two attach -> 1 case,
3 documents, correctly numbered redni_broj 1/2/3.

PASS -- tests/test_ztc_scenario_b_attach.py, 5/5:
- attaches to existing predmet_id instead of creating new
- 404 when the target predmet_id doesn't exist or isn't owned by the caller
- omitting predmet_id still creates a new case (backward compatibility)
- second document attached gets redni_broj=2, not a collision on 1
- first document in a brand-new case still gets redni_broj=1
```

### Regression suite
5 new tests, all passing. Full suite: 2306 passed, 1 skipped, 0 failed (was 2289/1/0 before tonight's
session) — zero regressions.

### Rollback strategy
Pure application code, additive field (`Optional`, defaults to `None` = prior behavior). No schema
change. Revert restores prior "always create new case" behavior exactly.

---

## Lessons Learned
The mission's own Rule Zero ("connect existing, don't rebuild") almost caused this fix to be
mis-scoped as "add a merge feature" — the actual highest-leverage fix was smaller: give finalize a
way to *not* create a new case in the first place, which needs zero new tables, zero new endpoints,
and directly prevents the problem rather than cleaning it up after the fact.

## Founder Summary
A lawyer uploading multiple documents for one client will now get one organized case instead of one
per document — this was previously impossible to avoid via the API at all. Also fixed a related
document-numbering bug this change would otherwise have exposed. 5 new tests, zero regressions. Not
yet reachable by a lawyer using the actual app — see the separate frontend-wiring Blocker Report.
