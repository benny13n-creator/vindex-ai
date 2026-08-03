# Mission Review — LZ-003: Extend global search to tasks + evidence fields

**Mission Board entry:** `MISSION_BOARD.md`, LZ-003, priority 3.
**Executed by:** Operation Lawyer Zero (founder's Master Prompt, BETA-001), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### Scope, and a real security consideration found before implementing
The Phase 1 inspection correctly found `routers/search.py` has no coverage of `zadaci` (tasks) or
evidence-specific fields. Investigating `zadaci`'s actual schema before copying the existing 6-type
pattern found a real difference that mattered: **`zadaci` has no `user_id` column at all** — only
`kreirao_uid` (creator), `dodeljen_uid` (assignee), `kancelarija_id` (firm), per
`migrations/045_firm_intelligence.sql`. Every other search branch scopes with a simple
`.eq("user_id", uid)`; naively copying that pattern onto `zadaci` would have been a schema error, not
just a missing-feature gap.

`zadaci`'s own RLS policy (`zadaci_firma_read`) grants visibility to the creator, the assignee, **or**
any active member of the same firm. Replicating the firm-wide tier correctly requires an async
`kancelarija_id` lookup this synchronous search-helper pattern doesn't have. **Deliberately scoped to
the safe subset only**: `kreirao_uid == uid OR dodeljen_uid == uid` — a strict subset of what the RLS
policy already allows a user to see, never a superset. This cannot leak another user's or another
firm's tasks; it can only under-return (a lawyer's own created/assigned tasks are found; firm-wide
task visibility via search is a smaller, separate follow-on, not attempted here).

### Second piece: `tip_dokaza` added to the existing document search
LZ-002 (same session) made `predmet_dokumenti.tip_dokaza` a real, correctly-populated field. Extended
the *existing* `_search_dokumenti` branch's `.or_()` filter to also match it — an in-place addition to
an already-correct branch, not a new search type, since it's the same table and the same tenant scope
already in place.

### Alternatives considered
- **A new `predmet_dokazi`-based "search by key legal facts" branch** (`kljucne_cinjenice`,
  `pravni_elementi`). Considered, deferred — lower urgency than tasks, and would need the same
  `predmet_id`-scoping pattern as `hronologija`/`beleske` (an extra join/lookup), adding real scope for
  marginal value tonight.
- **Full firm-wide task visibility in search** (matching the RLS policy's third tier exactly).
  Rejected for tonight specifically because of the async-lookup complexity noted above — the safe
  subset ships real value now without that risk.

---

## Implementation
`routers/search.py` — added `_search_zadaci` (new), registered in `_VALID_VRSTE`/`_SEARCHERS`;
extended `_search_dokumenti`'s existing `.or_()` filter to include `tip_dokaza`.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer searches globally for a task by name, or for a document
by its evidence type rather than exact wording.
1. GET /api/search?q=odgovor -> a task the lawyer created or was assigned,
   named "Pripremiti odgovor na tužbu", is now findable (was invisible
   before this mission).
2. GET /api/search?q=ugovor -> a document classified tip_dokaza="ugovor"
   is found even if the word "ugovor" doesn't appear verbatim in its
   extracted text.

PASS -- tests/test_lz003_search_extension.py, all 4 tests, including a
dedicated tenant-isolation check (test_search_zadaci_does_not_leak_other_users_filter_shape).
```

### Regression suite
4 new tests, all passing — including one specifically designed to catch a tenant-isolation regression
(asserts the query filter is parameterized per-caller, never hardcoded or shared). 37/37 across the
broader search/zadaci regression sweep, zero regressions.

### Rollback strategy
Pure application code, no schema/migration. Revert to restore (missing-feature, not broken) prior
state.

---

## Lessons Learned
The mission board's own completion criteria said "following the existing 6-type pattern exactly" —
investigating first found that copying the pattern *exactly* would have been wrong for this
particular table, because its schema genuinely differs. Worth restating the general lesson this
whole mission keeps surfacing: "looks like the same shape as 6 other things" is a starting
hypothesis to verify, not a license to copy-paste blind — especially when the copy-paste target is a
security-relevant scope filter.

## Founder Summary
Tasks and evidence-type document search are now live. Found before implementing that `zadaci` has a
genuinely different, firm-based scoping model (not per-user like everything else search already
covers) — scoped the fix to the provably-safe subset (a lawyer's own created/assigned tasks) rather
than risk a tenant-isolation bug by copying the wrong pattern. Firm-wide task search remains a real,
smaller, separate follow-on. 4 new tests including a dedicated isolation check, zero regressions.
