# Mission Review — LZ-001: Fix `vaznost` vocabulary mismatch (automatic reminders)

**Mission Board entry:** `MISSION_BOARD.md`, LZ-001, priority 1.
**Executed by:** Operation Lawyer Zero (founder's Master Prompt, BETA-001), 2026-08-03.
**Status:** DONE — **scope narrowed deliberately during implementation, for safety.**

---

## Architecture Decision

### Root cause — bigger and messier than the Phase 1 inspection's summary
The Phase 1 inspection correctly found the core problem: `email_notif.py::posalji_podsetnike`
(a real, already-scheduled daily cron) filters `.eq("vaznost", "kritičan")` exactly, while AI
extraction paths write different strings. Investigating further before implementing (per this
project's own standing discipline) found the actual vocabulary landscape is considerably more
fragmented than "2-3 spellings":

- `predmet_hronologija.vaznost` has a DB `CHECK` constraint (`supabase_setup.sql:397`) allowing only
  `'kritičan'`, `'važan'`, `'informativan'`.
- `routers/intake.py:216` (the **primary** AI-assisted case-creation path) writes `"bitan"` — not in
  the constraint's allowed list.
- `routers/rokovi_lanac.py`'s internal `_VAZNOST_HRON` mapping writes `"kljucan"`/`"normalan"`/`"info"`
  — also not in the constraint's allowed list.
- **Critically**: `api.py` already has its own urgency-ordering logic (`_VAZNOST_ORDER`, `:5114`) and
  an existing filter (`:5449`, `.in_("vaznost", ["kritičan","bitan"])`) that **already treat `"bitan"`
  as a real, expected value** — strong evidence this value is genuinely present in production data,
  not merely an aspirational write silently failing against the DB constraint (consistent with this
  project's repeated finding that `supabase_setup.sql` often describes an aspirational schema state
  that doesn't match live reality — see SEC-034, the `uploaded_documents`/migration-057 history).

### Alternatives considered, and why the scope was narrowed
- **Normalize every writer to the 3 canonical DB-constraint values.** Considered, then rejected for
  tonight specifically because `_VAZNOST_ORDER` and `api.py:5449` already depend on `"bitan"`
  existing — changing `intake.py`'s writer to `"važan"` would silently remove those rows from
  `_VAZNOST_ORDER`'s known buckets (it has no `"važan"` entry, only `"bitan"`), causing newly-created
  deadlines to sort as lowest-priority in whatever view uses that ordering. Fixing this properly
  requires a full audit of every reader of `vaznost`, which this mission does not have safe time
  budget for tonight — flagged as a real, separate, larger follow-on (see below), not silently
  dropped.
- **Fix only the exact 2 values the Phase 1 inspection named (`"važan"`, `"bitan"`).** Rejected as
  incomplete once `_VAZNOST_HRON`'s output values were found — a lawyer manually generating a
  deadline chain via `rokovi_lanac.py` would have had the same silent-no-reminder problem, and fixing
  only the 2 originally-named values would have left that path broken.
- **Chosen: broaden the cron's own read-side filter to include every value any writer actually
  produces today** (`_ACTIONABLE_VAZNOST = ["kritičan", "važan", "bitan", "kljucan", "normalan"]`,
  excluding only the genuinely non-actionable `"informativan"`/`"info"`). This is a `SELECT` filter
  change only — cannot violate a DB constraint, cannot corrupt data, and touches zero writers, so it
  cannot break `_VAZNOST_ORDER` or any other existing reader. Lowest-risk path to the actual goal
  (lawyers get reminders for deadlines that already exist), deferring the deeper vocabulary
  unification to a mission that can budget a full reader audit.

### Security / dependency / workflow review
No schema change, no new dependency. Traced the full path: cron trigger (`api.py`'s daily dispatcher,
confirmed live) → `posalji_podsetnike` → the now-broadened query → existing SMTP send path
(unchanged) → existing dedup log (unchanged). Only the query's `WHERE` clause changed.

---

## Implementation
`routers/email_notif.py` — added `_ACTIONABLE_VAZNOST` module constant with inline documentation of
the vocabulary fragmentation found; changed `posalji_podsetnike`'s filter from
`.eq("vaznost", "kritičan")` to `.in_("vaznost", _ACTIONABLE_VAZNOST)`.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer's client has a deadline extracted automatically by Smart
Intake from an uploaded document (vaznost="važan").
1. The deadline is written to predmet_hronologija (unchanged, already worked).
2. 7 days before the deadline, the daily cron runs (already scheduled, unchanged).
3. Before this fix: the cron's query never matched "važan" -- no email ever sent.
4. After this fix: the cron finds the deadline and sends the reminder email,
   exactly as it already does for the one value that worked before.

PASS -- tests/test_lz001_reminder_vocabulary.py, 3 of 5 tests cover this
exact scenario for "važan", "bitan", and the original "kritičan" (regression
check that the fix is additive, not a replacement).
```

### Regression suite
5 new tests, all passing. 23/23 across the broader `email_notif`/cron regression sweep, zero
regressions.

### Rollback strategy
Pure application code, one filter changed, no schema/migration. Revert to restore (broken) prior
behavior.

---

## Lessons Learned
**A "Small" complexity estimate was wrong once investigated** — not because the fix itself grew (it
stayed a one-line filter change), but because the true shape of the underlying vocabulary
fragmentation was much larger than the triggering inspection found. The right response was to
*narrow* the mission's actual change to what could be done safely (read-side only), not to expand it
to match the full scope of the problem discovered — the same discipline `M-005`'s blocker report
used the night before, applied in the opposite direction (there: stop entirely; here: do the safe
subset, defer the rest explicitly).

**Flagged, not fixed, as a real follow-on**: a full `vaznost` vocabulary unification across every
writer (`intake.py`, `smart_intake.py`, `rokovi_lanac.py`) and every reader (`_VAZNOST_ORDER`,
`api.py:5449`, `api.py:3389`, `:3948`, `:4946`, `:5392`, `:5480`) — this needs its own scoping pass
(a new mission, not attempted tonight) with a full reader audit before any writer is changed.

## Founder Summary
Fixed the reminder system so it actually fires for AI-extracted deadlines — but the underlying
vocabulary problem turned out to be more widespread than initially described (at least 6 distinct
spellings across 3 writers and multiple readers, not 2-3). Rather than attempt a full normalization
blind, tonight's fix is deliberately narrow and safe: broadened only the cron's own read filter,
touching zero writers, so it can't break the other code that already depends on today's inconsistent
values. A full vocabulary unification is flagged as a real, separate, future mission requiring its
own reader audit. 5 new tests, zero regressions.
