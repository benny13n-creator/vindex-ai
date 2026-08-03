# Night Shift Metrics

**Purpose:** the founder's own framing — *"Posle 30 dana imaćeš vrlo jasnu sliku koliko organizacija
zaista doprinosi razvoju."* This file tracks measurable output per Night Shift run, so the internal
AI organization's value is judged by a trend line, not by how polished any single night's summary
document reads.

**North Star (added 2026-08-02, binding for all future mission selection):** the founder's explicit
instruction — *"Smanjite broj beta blokera. Sve misije neka se biraju isključivo prema tome."*
No new agent roles, no organizational complexity added in response to this — see
`MISSION_BOARD.md`'s own new "North Star" section for how this constrains mission selection going
forward. This file exists to make that goal measurable, not to replace it with a vanity metric
("missions completed" alone says nothing if the missions don't reduce beta blockers).

---

## Methodology (fixed, so numbers stay comparable across nights — don't redefine per run)

| Metric | Counts as... |
|---|---|
| **Missions completed** | A Mission Board row moved to `DONE` this run, with a filed Mission Review. |
| **Bugs fixed** | A user-facing workflow that should have worked and didn't, now works — counted once per *workflow*, not once per code change (e.g. Mission 001's night-shift analogue, M-001, needed 3 coordinated code fixes for one user-facing bug — "images can't be uploaded" — and counts as 1). |
| **New bugs discovered** | A defect found *while working a different mission*, outside that mission's original scope — whether or not it was also fixed this run (an out-of-scope find that's deliberately left open, per this project's own scope-boundary rule, still counts as discovered). |
| **Blockers correctly escalated** | A mission where implementation was *stopped* and a Blocker Report filed instead of guessing, per the Master Prompt's Stop Conditions — this is counted as a **success** of the process, not a failure to complete a mission. |
| **Regressions introduced** | Any previously-passing test that failed after this run's changes. Measured by a full-suite run at the end of the night, not just each mission's own scoped regression sweep. |
| **Test pass rate** | `passed / (passed + failed + skipped)` from the final full-suite run of the night. |
| **Beta blockers removed** | A `docs/product/BETA_CRITICAL_PATH_2026-08-02.md` scenario that moved from blocked/partial to working, or a newly-found gap in one of those scenarios that was closed — counted per scenario, not per mission (one mission can close more than one scenario's gap, or zero). |
| **Security findings resolved** | A named SEC-XXX Gap Register item closed. |
| **Founder decisions required** | A Blocker Report or open question filed that specifically needs the founder's judgment (product risk, legal risk, architecture direction) rather than more engineering investigation. |

---

## 2026-08-02 (first run)

| Metric | Value |
|---|---|
| Missions completed | 6 (M-001, M-002, M-003, M-013, M-010, M-012) |
| Bugs fixed | 6 — M-001 (1 user-facing bug, 3 coordinated code fixes), M-003 (1), M-013 (1), M-010 (1), M-012 (2) |
| New bugs discovered | 2 — M-012's insert-`user_id` bug (found while fixing an unrelated known bug in the same function, then fixed); the adjacent `logger.warning(...resp)` line found during M-010 (found, deliberately left open — out of that fix's approved scope) |
| Blockers correctly escalated | 1 — M-005 (deadline chain auto-fire; needs a founder product/risk decision, not more engineering) |
| Regressions introduced | 0 — confirmed by a full-suite run at the end of the night (2278 passed, 1 skipped, 0 failed), not just per-mission sweeps |
| Test pass rate | 2278/2279 (99.96%) |
| Beta blockers removed | 3 scenarios — #2 "create a case" (gained the Case Pipeline analysis it was missing on its primary path), #3 "upload PDF or photo" (photo upload now works end to end), #8 "find a case" (search was silently broken for every document, for everyone, confirmed via the codebase's own migration history) |
| Security findings resolved | 1 — SEC-058 |
| Founder decisions required | 1 — M-005's blocker report |

**Notable pattern, worth watching in future nights:** 1 of 2 "new bugs discovered" came from re-examining code a *previous* mission (Mission 001, earlier the same session) had already swept — direct evidence for that mission's own recommendation (a mechanical Schema Contract Check) rather than an argument for more manual sweeps.
