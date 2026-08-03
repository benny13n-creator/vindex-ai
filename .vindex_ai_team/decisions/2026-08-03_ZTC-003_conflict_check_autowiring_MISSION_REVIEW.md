# Mission Review — ZTC-003: Automatic conflict-of-interest check on document-first case creation (Scenario 5)

**Mission Board entry:** `MISSION_BOARD.md`, ZTC-003.
**Executed by:** Operation Autonomous Law Office (BETA-002), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### The gap
`POST /api/intake/conflict-check` (`routers/intake.py`) is a real, working conflict-of-interest check
(three scenarios: opposing party is already a client — blocking; new client is already an opposing
party — blocking; duplicate client name — warning). It belongs entirely to the older, **name-first**
CRM Intake Wizard, where a lawyer types a client/opposing-party name before any case exists.

Smart Intake (the **document-first** flow) never called it, anywhere — structurally, there was no
natural moment for it to run: party names aren't known until AI extraction completes, and
`finalize_intake_job` never invoked the check even though it already has extracted
`plaintiff`/`defendant` values in `value_map` at exactly the point a case gets created. A case could
be — and every time, silently was — created via Smart Intake with no conflict check ever having run.

### Fix, in two parts

**1. Extraction, not duplication.** `routers/intake.py::intake_conflict_check`'s entire matching body
was moved into a new plain async function, `_run_conflict_check(uid, novi_klijent_ime,
novi_klijent_firma, protivna_strana, pib)` — no `Request`, no rate-limiter, no pydantic body required.
The original HTTP endpoint is now a 3-line wrapper delegating to it. This was the Rule-Zero-correct
move: the alternative (duplicating the matching logic inside `smart_intake.py`) is exactly the kind of
duplicate-logic the mission's Step 9 sweep is looking to prevent, and this project's own architecture
avoids it consistently elsewhere. Behavior is byte-for-byte identical for the existing endpoint —
confirmed by the pre-existing `tests/test_intake_conflict_check.py` suite passing unchanged.

**2. Non-blocking auto-trigger.** `finalize_intake_job` now calls `_run_conflict_check` as a
fire-and-forget background task (same pattern as LZ-002's Evidence Vault auto-classification),
deriving the new client name and opposing party from `value_map`'s already-extracted
`plaintiff`/`defendant` based on `body.klijent_strana`. If a conflict is found, it's surfaced via the
existing `proactive_alerts` mechanism (the same table Case Genome already uses for its own alerts) —
not a new notification system.

### The deliberate, safety-motivated design choice: never block
The existing endpoint's own semantics treat some conflicts as "BLOKIRAJUCI" (blocking). Auto-wiring
this into finalize does **not** carry that blocking behavior over — finalize always succeeds and the
case is always created; a detected conflict becomes a prominent alert inside the newly-created case,
not a failed API call. This was a deliberate choice, not an oversight: Smart Intake's entire promise is
"upload a document, the case is created" — a name-matching false positive (the matcher is substring-
based, per `_name_match`) silently blocking a real case's creation would be a worse failure mode than
surfacing a warning the lawyer can act on. The actual "should I decline this client" judgment remains
the lawyer's, exactly as the existing endpoint's own `preporuka` text already frames it — this fix
adds visibility, not a new automated legal judgment.

### Alternatives considered
- **Blocking finalize on a detected `BLOKIRAJUCI` conflict.** Rejected — see above. Would also require
  a UI to resolve/override the block, which doesn't exist for this flow (another argument this belongs
  behind the frontend-wiring decision, not decided blind tonight).
- **A new dedicated alert type/table for conflicts.** Rejected — `proactive_alerts` already exists,
  already has the right shape (`naslov`/`opis`/`tip`/`urgentnost`/`procitana`), and Genome already
  writes to it for its own delta alerts. Reusing it is the Rule Zero-correct choice.

---

## Implementation
`routers/intake.py` — extracted `_run_conflict_check`; `intake_conflict_check` now delegates to it.
`routers/smart_intake.py` — `finalize_intake_job` schedules a background conflict-check task after
client linking, using `value_map`'s extracted party names; surfaces any finding via `proactive_alerts`.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer uploads a lawsuit naming a defendant who is already
represented as a client in another active case.
Before: the case is created via Smart Intake with no conflict check ever
run -- the lawyer has no way to discover this except noticing manually.
After: the case is still created (finalize never blocks), and a "BLOKIRAJUĆI
sukob interesa" alert appears in proactive_alerts, scoped to the new case,
immediately.

PASS -- tests/test_ztc_conflict_check_autowiring.py, 5/5:
- _run_conflict_check callable directly (the extraction's whole point)
- no false alert when names are unrelated
- finalize surfaces a proactive_alerts row when a conflict is found, with
  the correct urgency and predmet_id
- finalize creates NO alert when the check is clean
- a conflict-check failure (exception) does not break case creation
  (fire-and-forget, same discipline as LZ-002)
```

### Regression suite
5 new tests, all passing. The pre-existing `tests/test_intake_conflict_check.py` (6 tests covering the
HTTP endpoint's 3 real scenarios) passes unchanged, confirming the extraction preserved behavior
exactly. Full suite: 2306 passed, 1 skipped, 0 failed.

### Rollback strategy
Pure application code, no schema change. The extraction is a pure refactor (revertible independently
of the auto-trigger); the auto-trigger is a fire-and-forget background task addition (revertible by
removing the `asyncio.create_task` call and the now-unused import).

---

## Lessons Learned
This is the first fix this session where the "correct" wiring required *not* carrying over part of the
existing component's behavior (the blocking semantics) — a reminder that "connect existing" doesn't
always mean "connect it exactly as-is everywhere it's reused." The safety property that matters
(never block an automatic case-creation promise on a heuristic name match) took priority over
behavioral consistency with the manual flow.

## Founder Summary
A conflict of interest is now checked automatically the moment a case is created from an uploaded
document, using the exact same detection logic the manual CRM wizard already uses — surfaced as an
alert inside the new case, never blocking its creation. 5 new tests, zero regressions to the existing
conflict-check test suite or anything else.
