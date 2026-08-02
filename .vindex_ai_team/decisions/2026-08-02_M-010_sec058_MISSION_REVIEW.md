# Mission Review — M-010: Security Findings (SEC-058, narrowly scoped)

**Mission Board entry:** `MISSION_BOARD.md`, M-010, priority 10.
**Executed by:** Autonomous Night Shift (founder's Master Prompt v1.0), 2026-08-02.
**Status:** DONE.

---

## Architecture Decision
`shared/deps.py:229` and `api.py:216` — two independent copies of `_verify_token` — each logged
the full Supabase `auth.get_user()` response, including the authenticated user's email, at **INFO**
level on **every single successful authentication**. Already identified in the 2026-08-02 forensic
audit's Gap Register and fully specified in the (currently parked) forensic-remediation plan's Epic
A. Fix scope kept identical to that prior analysis — remove exactly the two `logger.info` lines,
nothing else.

**Deliberately not touched, and stated so rather than silently swept past**: a `logger.warning`
fallback a few lines below in each file also formats the raw response object, but only fires on the
already-anomalous empty-user path (not every request) — out of SEC-058's originally scoped fix, and
out of this mission's scope. Found while writing the regression test (below); disclosed rather than
either silently expanded or silently ignored.

## Implementation
`shared/deps.py`, `api.py` — one line removed from each, identical in both.

## QA Report
- **Negative control performed before trusting the test**: verified the new source-level regression
  test actually catches the original vulnerable line, by running it against the old code's text
  directly (not just the fixed version) — it failed as expected, confirming the test is a real guard,
  not a vacuous one.
- **Why a source-level check, not only a behavioral one**: on the success path, no log call fires at
  all any more (the line was removed, not redacted) — so a purely behavioral `caplog` assertion would
  pass vacuously (empty record list) even if a future edit reintroduced the leak in a slightly
  different form. Both are included; the source check is the one that actually matters.
- 5 new tests, all passing (2 behavioral, 2 source-level negative-control-verified, 1 fallback-path
  sanity check). 31 tests across the broader auth/deps regression sweep, zero regressions.

## Rollback strategy
Pure application code, 1 line removed per file, no schema/migration. Revert to restore (undesirable)
prior behavior.

## Founder Summary
Removed a PII-in-logs finding (SEC-058) already fully specified by the earlier forensic audit —
every authenticated request was logging the user's email at INFO level, in two independent copies of
the same function. Fix scope matched exactly what was previously analyzed and approved; a related,
lower-risk, out-of-scope line (same pattern, but only on the failure path) was found and explicitly
flagged rather than silently touched or silently ignored. 5 new tests, one of which was verified
against a negative control before being trusted. Zero regressions. Local commit only, not pushed.
