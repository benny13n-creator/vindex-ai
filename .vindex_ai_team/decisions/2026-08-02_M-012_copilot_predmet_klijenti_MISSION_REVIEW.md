# Mission Review — M-012: Technical Debt (`copilot.py`'s `predmet_klijenti` bugs)

**Mission Board entry:** `MISSION_BOARD.md`, M-012, priority 12.
**Executed by:** Autonomous Night Shift (founder's Master Prompt v1.0), 2026-08-02.
**Status:** DONE — **scope grew from 1 known bug to 2, found while fixing the first.**

---

## Architecture Decision

### Root cause — the known bug, plus a second one Mission 001's sweep missed
This mission was scoped to fix one already-diagnosed issue: `routers/copilot.py:610`'s
`.select("id")` duplicate-link check against `predmet_klijenti`, which has no `id` column (composite
primary key: `predmet_id`, `klijent_id` — see `supabase_setup.sql:610-615`). This is the same bug
class found and fixed at `api.py:5245` during Mission 001, deliberately kept as a separate ticket at
the time (different feature/workflow).

**While fixing it, a second, more severe bug was found two lines below**: the `predmet_klijenti`
insert at what is now line ~616-619 also sent `"user_id": user_id"` — the *exact* Mission 001 bug
(the table has no `user_id` column either; ownership is derived transitively via
`predmet_id → predmeti.user_id`) — a **6th call site**, missed during that mission's original sweep
because that sweep checked this file's `SELECT` for the column-name issue but not this file's
`INSERT` for the `user_id` issue specifically.

**Per this project's own scoping discipline** (Mission 001, Revision 3 — "same user-facing
functionality = same ticket"): both bugs live in the same function
(`_handle_akcija_povezi_klijenta`), touching the same table, for the same user action ("link a
client to a case via the AI copilot"). Fixing only the originally-scoped one would have left the
insert silently failing exactly as it did before Mission 001 existed — so both are fixed together
here, not split across two more tickets.

### Alternatives considered
None — this is the same, already-validated fix (remove `user_id` from the insert; select a real
column for the duplicate check) applied at a newly-found 6th site. No new design.

---

## Implementation
`routers/copilot.py::_handle_akcija_povezi_klijenta` — `.select("id")` → `.select("predmet_id")`;
removed `"user_id": user_id` from the `predmet_klijenti` insert payload.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer asks the AI copilot to link a client to the current case
by name (e.g. "poveži Anu Jović sa ovim predmetom").
1. Copilot extracts the client name via GPT, finds the client record.
2. Duplicate-check: is this client already linked to this case? (must not
   error on a nonexistent `id` column.)
3. If not linked: insert the link (must not send `user_id` -- no such column.)
4. Lawyer sees "Ana Jović je povezana sa predmetom."

PASS -- tests/test_copilot_povezi_klijenta.py, both scenarios (new link,
already-linked duplicate detection).
```

### Regression suite
2 new tests, both passing. 30/30 across the broader `copilot` test sweep. Zero regressions.

### Rollback strategy
Pure application code, no schema/migration. Revert the diff to restore (broken) prior behavior.

---

## Lessons Learned
**This is exactly the kind of thing a mechanical Schema Contract Check (proposed in Mission 001's
architecture decision as a non-blocking follow-on) would have caught automatically, at every call
site, the first time — rather than depending on a human or agent noticing it a second time while
looking at adjacent code for an unrelated reason.** This mission is itself a small piece of evidence
in favor of building that check eventually: two real bugs on the same table, of the same class,
survived one dedicated sweep (Mission 001) and were only caught in a second, unrelated pass.

## Founder Summary
Fixed both bugs in the AI copilot's "link client to case" command: the already-known duplicate-check
bug, plus a second, more serious one found while fixing it — the insert itself also had Mission 001's
`user_id` bug, at a 6th call site that mission's sweep missed. Both fixed together, since they're the
same user-facing action. 2 new tests, 30/30 in the broader copilot suite, zero regressions. Local
commit only, not pushed.
