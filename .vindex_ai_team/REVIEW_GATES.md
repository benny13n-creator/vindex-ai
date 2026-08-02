# Review Gates — Canonical State Table

Every gate-holding role in this organization emits one of a small, fixed set of states — never
free-form prose as the *only* record of its verdict. This file is the single place all of them are
defined, so a `RELEASE_APPROVAL.md` checklist can be verified mechanically against this table
instead of each reviewer inventing its own vocabulary each time.

| Role | States | Blocking states | Where defined |
|---|---|---|---|
| Red Team / Devil's Advocate | `FREEZE READY`, `BLOCKING` | `BLOCKING` (if it contains a CRITICAL or HIGH finding) | `agents/04_red_team_devils_advocate.md`, `templates/RED_TEAM_REPORT.md` |
| Security & Privacy Architect | `APPROVED`, `CONDITIONAL`, `BLOCKED` | `BLOCKED`; `CONDITIONAL` blocks Release Governance until its named condition is met | `agents/05_security_privacy_architect.md`, `templates/SECURITY_REVIEW.md` |
| Database Architect | `APPROVED`, `APPROVED WITH CONDITIONS`, `BLOCKED` | `BLOCKED` (destructive migration veto) | `agents/08_database_architect.md`, `templates/DATABASE_REVIEW.md` |
| AI System Architect | `APPROVED`, `APPROVED WITH CONDITIONS`, `BLOCKED` | `BLOCKED` | `agents/06_ai_system_architect.md`, `templates/AI_DESIGN_REVIEW.md` |
| QA Engineering | `PASS`, `BLOCKED` | `BLOCKED` (release-blocking) | `agents/11_qa_engineering.md`, `templates/QA_REPORT.md` |
| Release Governance | `APPROVED FOR RELEASE`, `BLOCKED` | `BLOCKED` (final, absolute) | `agents/12_release_governance.md`, `templates/RELEASE_APPROVAL.md` |
| AI CTO / Chief Architect | (no fixed enum — produces a written recommendation, not a gate state) | N/A — the CTO recommends, it does not itself block the way the veto roles do, per `ORG_CHART.md`'s authority table | `agents/01_ai_cto_chief_architect.md` |

## Rules that apply across every row above

1. **A `CONDITIONAL`/`APPROVED WITH CONDITIONS` state is not a pass.** It is a pass *contingent on*
   a named, checkable condition. Release Governance must verify the condition was actually met, not
   just that the reviewing role said "conditional" and considered its job done.
2. **A blocking state from ANY role in this table halts the workflow at the phase it was raised in
   — it does not wait for a later phase to notice.** If Security blocks during Phase 4, the mission
   does not proceed to Phase 5 hoping QA will catch it later.
3. **Only the founder can convert a blocking state into a proceed decision**, and only by an
   explicit, written override recorded in the relevant decision artifact (never a verbal aside,
   never assumed from silence) — see `ESCALATION_RULES.md`.
4. **A missing gate is treated as a blocking state.** If a migration exists with no
   `DATABASE_REVIEW.md`, that is functionally `BLOCKED`, not `APPROVED-by-omission`.
