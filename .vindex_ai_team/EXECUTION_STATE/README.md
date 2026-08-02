# EXECUTION_STATE/

Live status tracking for missions currently in flight through `OPERATING_PROTOCOL.md`'s phases —
distinct from `decisions/` (the finished artifacts each phase produces) and
`memory/current_state.md` (the organization's own standing state, updated occasionally). A file
here is a working document, updated as the mission moves, one file per active mission.

**Naming convention:** `YYYY-MM-DD_short-mission-name.md`.

**Template for a new mission's state file:**
```markdown
# [Mission Name]

**Started:** [date]
**Current phase:** [0-7, per OPERATING_PROTOCOL.md]
**Status:** ACTIVE / BLOCKED / PAUSED / COMPLETE

## Phase log
- Phase 0 (Founder Request): [one line, date]
- Phase 1 (Product Discovery): [status, link to artifact once produced]
- Phase 2 (Architecture Review): [status, link]
- Phase 3 (Mandatory Opposition): [status, link, verdict]
- Phase 4 (Security Gate): [status, link, SECURITY_STATUS]
- Phase 5 (Implementation): [status — or "deliberately deferred, see note" if founder said not yet]
- Phase 6 (QA): [status]
- Phase 7 (Release Governance): [status]

## Current blocker (if any)
[What, specifically, is stopping forward progress right now — not a general risk, the literal
next thing that must resolve.]

## Next action
[The single next concrete step, and whose role it is.]
```

**When a mission completes**, its state file should be archived (moved to
`EXECUTION_STATE/completed/` or simply marked `Status: COMPLETE` and left in place — this
project's own preference for not over-engineering a simple thing applies here too; don't build an
archival pipeline for what a status line already communicates).
