# Mission Review — BL-001: Fix cross-tenant task-data leak (`zadaci_za_predmet`)

**Mission Board entry:** `MISSION_BOARD.md`, BL-001.
**Executed by:** Operation Beta Lockdown (BETA-005), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### The finding
`GET /api/zadaci/predmet/{predmet_id}` (`routers/zadaci.py:380-402`) took `predmet_id` directly from
the URL and queried `zadaci` filtered only by that ID — no `.eq("user_id", ...)`, no
`.eq("kancelarija_id", ...)`, and critically no prior check that the calling user has any relationship
to that case at all. Any authenticated user who obtained another firm's `predmet_id` — through a leaked
URL, a screenshot, a support ticket, or simple ID enumeration attempts — could retrieve that firm's
complete task list: names, descriptions, deadlines, assignees. This is a live, exploitable IDOR
(Insecure Direct Object Reference), found by this mission's own tenant-isolation sweep, not reported
externally.

### Why this is an isolated omission, not a systemic gap
Every comparable `{predmet_id}`-scoped endpoint in the SAME file already implements this check —
`ai_analiziraj_predmet` (`:493-503`, ~90 lines below) does `predmeti.eq("id", predmet_id).eq("user_id",
uid)` before touching anything else. This project's own SEC-001 fix (2026-07-23, `docs/security/
SECURITY_GAP_REGISTER.md`) swept all `{predmet_id}`-scoped *mutation* endpoints and found this exact
missing-ownership-check pattern in only 2 places, fixed both, and confirmed no other mutation endpoint
had the gap. `zadaci_za_predmet` is a *read* (GET) endpoint — outside that prior sweep's stated scope —
and turns out to have the identical defect shape SEC-001 was written to prevent. Worth noting for any
future security sweep: SEC-001's methodology should be re-applied to read endpoints, not only mutations.

### The fix
Added the identical `predmeti.eq("id", predmet_id).eq("user_id", uid).maybe_single()` check before the
`zadaci` query, raising `404, "Predmet nije pronađen."` on failure — matching `ai_analiziraj_predmet`'s
exact wording and status code, so a non-owned case looks identical to a non-existent one (no
existence-vs-ownership oracle for an attacker to exploit).

---

## Implementation
`routers/zadaci.py` — `zadaci_za_predmet` gains an ownership check before its existing query.

---

## QA Report

### User Scenario Test
```
Scenario: an attacker (or a lawyer who mistakenly received a link to
another firm's case) requests that case's task list.
Before: 200 OK, full task data for a firm they have no relationship to.
After: 404, identical to requesting a case ID that doesn't exist at all.

PASS -- tests/test_beta_lockdown_zadaci_predmet_idor.py, 4/4:
- the legitimate owner can still read their own case's tasks (no
  false-positive lockout)
- a non-owner requesting another firm's real case ID gets 404, never
  the data
- a nonexistent case ID gets the IDENTICAL 404 (no oracle)
- direct proof the zadaci table is never even queried when the
  ownership check fails (not just a response-shape check)
```

### Negative control
Per this project's own established discipline (SEC-058's precedent), the fix was temporarily reverted
via `git stash` and the test suite re-run against the pre-fix code: 3 of 4 new tests failed exactly as
expected (`DID NOT RAISE HTTPException`), confirming the tests genuinely catch this specific bug rather
than passing vacuously. Fix restored via `git stash pop`, all 4 tests confirmed passing again.

### Regression suite
4 new tests, all passing (negative-control-verified). Full suite: 2315 passed, 1 skipped, 0 failed (was
2311 before this mission's fix, following Lawyer Day's earlier photo-upload fix the same night).

### Rollback strategy
Pure application code, additive check, no schema/migration. Revert restores the pre-fix (vulnerable)
behavior exactly — not recommended given the finding's severity.

---

## Lessons Learned
A prior, well-executed security sweep (SEC-001) can still leave a gap if its stated scope was narrower
than the actual attack surface — SEC-001 correctly and thoroughly swept every *mutation* endpoint, but
a *read* endpoint with the identical missing-check shape sat unexamined for two weeks until a
differently-scoped investigation (this mission's tenant-isolation sweep, not a security-specific one)
happened to check it. Worth a standing reminder: "we already swept for this bug class" claims should
specify exactly what was swept, since the same defect shape can hide outside a previous sweep's
declared boundary.

## Founder Summary
Found and fixed a live, exploitable bug where any authenticated user could read another law firm's
complete task list by knowing or guessing their case ID — a real cross-tenant data leak, not a
theoretical one. Fixed with the same pattern already used elsewhere in the same file, verified with 4
tests including a negative control proving the tests actually catch the bug. Zero regressions.
