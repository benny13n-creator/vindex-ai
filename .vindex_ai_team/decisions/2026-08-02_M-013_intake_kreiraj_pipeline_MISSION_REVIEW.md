# Mission Review — M-013: Wire `intake_kreiraj` into the Case Pipeline / Event Bus

**Mission Board entry:** `MISSION_BOARD.md`, M-013, priority 3.5 (added by M-002's investigation).
**Executed by:** Autonomous Night Shift (founder's Master Prompt v1.0), 2026-08-02.
**Status:** DONE.

---

## Architecture Decision

### Root cause
M-002's investigation confirmed `POST /api/intake/kreiraj` — the primary AI-assisted case-creation
endpoint per this session's Bojan Workflow Gap Analysis — was the one major case-creation path with
no Case Pipeline trigger, while `post_from_template` (`routers/intake.py:775-783`) and the plain
`/api/predmeti` route (`api.py:3242-3268`) both already had one.

### Alternatives considered
- **Emit `EventType.PREDMET_KREIRAN` through the event bus**, matching `api.py:3265`'s pattern.
  Considered — would also make this creation path visible to any future event-bus consumer.
- **Call `run_case_pipeline` directly**, matching `post_from_template`'s pattern. **Chosen** — this
  mission's own scope (per the Mission Board's completion criteria) explicitly allows either
  convention; the direct-call pattern was chosen because `intake_kreiraj` and `post_from_template`
  are the same conceptual operation (AI-assisted case creation) already living in the same file,
  so matching the nearer, more-similar existing call site keeps the two consistent with each other
  specifically, which matters more here than consistency with the event-bus path used by the
  differently-shaped plain-CRUD `/api/predmeti` route.
- **Do nothing, defer to a later mission.** Rejected — Small complexity, no new design, a direct
  copy of an already-working, already-tested pattern; deferring a fix this cheap and this clearly
  scoped would not serve the mission board's own stated priority ordering.

### Security / dependency / workflow review
No new dependency, no schema change, no new attack surface — this adds exactly the same
fire-and-forget background call `post_from_template` already makes, to one more call site. The
Case Pipeline itself (`services/case_pipeline.py`) is unchanged.

---

## Implementation
`routers/intake.py::intake_kreiraj` — added a `_run_pipeline()` local async function (identical
shape to `post_from_template`'s own, same file), dispatched via `asyncio.create_task` right before
the endpoint's final log line and return, so it does not block or affect the HTTP response.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer creates a case via the primary AI-assisted flow.
1. POST /api/intake/kreiraj with a client id + case description.
2. Case is created, response returned normally (unchanged).
3. In the background, the 9-step Case Pipeline now runs against the new
   case (previously: nothing ran).
4. If the pipeline fails for any reason, the response the lawyer already
   received is unaffected -- failure is caught and logged, not surfaced
   as an error on a request that already succeeded.

PASS -- tests/test_intake.py::test_intake_kreiraj_triggers_case_pipeline
       (captures the asyncio.create_task call, awaits it, confirms
       run_case_pipeline(predmet_id, user_id) is actually invoked)
       tests/test_intake.py::test_intake_kreiraj_pipeline_failure_does_not_break_response
       (confirms a pipeline exception is swallowed, response still succeeds)
```

### Regression suite
180 tests across `tests/*intake*` and `tests/test_case_pipeline.py` — all passing (178 pre-existing
+ 2 new). Zero regressions.

### Rollback strategy
Pure application code, no schema/migration. Revert the diff; the endpoint returns to not triggering
the pipeline (today's status quo), which is the known, pre-existing (if suboptimal) behavior.

---

## Lessons Learned
This is the cleanest kind of mission this Night Shift ran: a gap identified with hard evidence
(M-002), a fix that is a verbatim copy of an already-working, already-proven pattern in the same
file, with no new design risk. Confirms the Mission Board's own stated value of splitting
investigation (M-002) from implementation (M-013) as separate missions — the investigation
produced a precisely-scoped, low-risk follow-on rather than a vague "improve Genome wiring" mandate
that would have needed its own scoping pass before being safely actionable.

## Founder Summary
The primary AI-assisted case-creation endpoint now triggers the same 9-step Case Pipeline analysis
that case creation via a template or the plain form already gets — closing the one real gap M-002's
investigation found. Copied an existing, working, already-tested pattern verbatim; no new design.
180 tests green, 2 new, zero regressions. Local commit only, not pushed.
