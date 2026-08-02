# Mission 001 — Prepare Vindex AI for Bojan Beta Workflow: P0 Intake Integrity

**Started:** 2026-08-02
**Current phase:** 6 (QA) — **implementation complete, all tests pass**
**Status:** COMPLETE

## Mission (Phase 0 — Founder Request, verbatim/translated)
"Mission 001: Prepare Vindex AI for Bojan Beta Workflow. Do not create new systems. First eliminate
existing reliability gaps. Start with P0: `predmet_klijenti.user_id` ownership integrity. Provide
migration plan, affected files, tests, rollback strategy. **No implementation until architecture
review.**"

Context: this mission follows a full mode switch (2026-08-02) away from the Security Governance
Framework (parked at Revision 2 / ACTIVE BLOCKER, not abandoned — see
`EXECUTION_STATE/2026-08-02_forensic-audit-remediation.md`) toward the shortest real path to a
lawyer-usable "Advokatski Operating System MVP," triggered by beta-user (Bojan) feedback and grounded
by `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`, which found the intake system already
built and wired end-to-end, with reliability/convergence gaps rather than missing features.

## Phase log
- Phase 0 (Founder Request): received 2026-08-02.
- Phase 1 (Product Discovery): folded into Phase 2 — the problem statement is already fully
  established by the gap analysis; no separate product-discovery pass needed for a P0 data-integrity
  fix.
- Phase 2 (Architecture Review): **done** — see
  `decisions/2026-08-02_mission001_predmet_klijenti_ARCHITECTURE_DECISION.md`. Root cause found to be
  different, and simpler to fix, than originally assumed: `predmet_klijenti` was **deliberately
  designed without a `user_id` column** (`supabase_setup.sql:610-615` — a pure join table, composite
  PK, ownership derived transitively via `predmet_id → predmeti.user_id`), not a column that was
  accidentally dropped. The bug is entirely in application code sending a field the schema never
  had. Recommended fix: **strip `user_id` from the 5 broken insert call sites — no migration, no
  backfill, no schema change.** Scope also expanded during review: found **5** broken call sites, not
  the 3 originally reported (`routers/intake.py` ×3, `api.py:5253`, `routers/onboarding.py:234`), plus
  one adjacent, differently-shaped bug (`routers/copilot.py:610` selects a nonexistent `id` column on
  the same table — a broken duplicate-link check, not a `user_id` issue).
- Phase 3 (Mandatory Opposition): founder chose a narrow verification pass instead of a full Red
  Team cycle, given the low risk class (no schema touched, subtraction not addition, trivial
  rollback). Run directly (no subagent — confirmed a "few minutes" job as anticipated): zero
  `.update()`/`.delete()` calls on `predmet_klijenti` exist anywhere; all 7 insert call sites
  accounted for; found one real stacked-bug at `api.py:5245` (same `.select("id")` nonexistent-
  column class previously found only at `copilot.py:610`) sitting directly in front of the insert
  already being fixed at that site.
- **Founder direction on the stacked-bug finding:** `api.py:5245` folds into Mission 001 (not a
  separate ticket, unlike `copilot.py:610`) — reasoning is now a standing organizational rule, see
  `OPERATING_PROTOCOL.md`'s new "Ticket/Mission scope boundary rule": the test is "same user-facing
  functionality," not "same bug class." Also adopted, more broadly: a **Definition of Done** rule
  (`agents/11_qa_engineering.md`, `templates/QA_REPORT.md`) — done means the user can complete the
  scenario, not that unit tests pass; every QA report now requires an end-to-end User Scenario Test.
- Phase 2 (Architecture Review): **Revision 3 — APPROVED.** Final scope: remove `user_id` from 5
  insert sites; fix `api.py:5245`'s `.select("id")`; bulk-import compensating delete (P0); regression
  tests; a User Scenario Test for the full "link client to case" flow (drafted in the decision doc,
  to be run for real at QA time). Out of scope, confirmed: `copilot.py:610` (separate ticket, same
  bug class, different feature), Schema Contract Check (separate, non-blocking follow-on).
- Phase 4 (Security Gate): N/A — no security-relevant change.
- Phase 5 (Implementation): **done.** All 5 `user_id` removals (`routers/intake.py` ×3, `api.py`,
  `routers/onboarding.py`), the `api.py:5245` `.select("id")` → `.select("predmet_id")` fix, and the
  bulk-import compensating delete (`routers/intake.py`) implemented exactly per Revision 3's approved
  scope.
- Phase 6 (QA): **done.** `tests/test_mission001_predmet_klijenti.py` — 6 tests, all passing:
  user_id-absence at all 5 sites, the bulk-import compensating-delete behavior (verified by injecting
  a failure and asserting the orphaned `predmeti` row is actually deleted, not just that a delete
  function was called), and the required **User Scenario Test** (link a client to a case, then
  attempt the same link again — confirms the duplicate check actually finds the existing row via a
  real column instead of erroring on the nonexistent `id` column, and that no second row is
  inserted) — run against the real `predmet_confirm_links` endpoint function, not inferred from
  source inspection. Full existing suite re-run for regressions: 174 intake/onboarding/predmet/
  klijenti/bulk/confirm-related tests, all passing, zero regressions.
- Phase 7 (Release Governance): not formally invoked as a separate role pass — given this mission's
  own Revision-3 risk calibration (no schema touched, subtraction not addition, trivial rollback),
  the founder's own approved gate was the architecture decision + the narrow verification pass, both
  complete, plus now a fully green test suite. Flagging this rather than silently skipping it: if the
  founder wants a formal Release Governance sign-off before this is considered production-ready,
  that's a distinct, cheap next step, not assumed done here.

## Current blocker
None. Mission complete pending founder's own review of the diff/commit.

## Next action
Resume the Bojan Beta Workflow mission's next P0/P1 items per
`docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`'s recommendation order (image upload next).
`copilot.py:610` and the Schema Contract Check remain tracked separately, not blocking this mission's
completion, per the founder's own scope ruling.
