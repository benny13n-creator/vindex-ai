# Night Shift Summary — 2026-08-02

**Protocol:** Founder's "Autonomous Night Shift v1.0" Master Prompt, executed against
`.vindex_ai_team/MISSION_BOARD.md`.
**Mode:** all commits local only, per explicit instruction — nothing pushed. 7 commits made
tonight, on top of the branch as it stood when the session began.
**Final state:** full test suite — **2278 passed, 1 skipped, 0 failed** (241s runtime).

---

## Completed missions

| # | Mission | Outcome |
|---|---|---|
| M-001 | Image Upload Support | **DONE.** `.jpg`/`.jpeg`/`.png` now flow through Smart Intake end to end (upload → suffix validation → worker → OCR → classification). Required 3 coordinated fixes, not 1 — verified before implementing that fixing only the extractor would have shipped no observable improvement (the worker's suffix-guesser would still route images to the PDF parser). 18 new tests. |
| M-002 | Case Genome Wiring Verification | **DONE** (investigation, no code changed). Re-checked a 2026-07-21 finding against current code. Better than assumed: the Case Pipeline already auto-fires on 2 of 3 major case-creation paths; Genome's refresh trigger is live on both upload paths; the promised AI-analysis output fields are genuinely reachable via two real consumers. One real gap found and handed off as M-013 (below). |
| M-003 | Search Table Mismatch | **DONE.** Global document search was silently querying a table (`uploaded_documents`) that the codebase's own migration history had already confirmed has zero writers anywhere — worse than the triggering document assumed. Repointed to the real table (`predmet_dokumenti`). 3 new tests. |
| M-013 | Wire `intake_kreiraj` into the Case Pipeline | **DONE** (proposed by M-002, executed same night — small, verbatim copy of an existing working pattern). The primary AI-assisted case-creation endpoint now gets the same background 9-step analysis every other creation path already had. 2 new tests. |
| M-010 | Security: SEC-058 (PII in logs) | **DONE.** Two independent copies of `_verify_token` were logging the full auth response, including the user's email, on every successful authentication. Fix scope matched exactly what the (separately parked) forensic remediation plan already specified — no scope creep into the still-blocked Epic B/Security Governance Framework chain. 5 new tests, one verified against a negative control before being trusted. |
| M-012 | Technical debt: `copilot.py`'s `predmet_klijenti` bugs | **DONE** — grew from 1 bug to 2. The known `.select("id")` issue was fixed; a second, more serious bug (the insert two lines below also sent `user_id`, Mission 001's exact bug, at a 6th call site that mission's sweep missed) was found and fixed in the same pass, since it's the same user-facing action. 2 new tests. |

**Blocked, correctly (not guessed):**

| # | Mission | Outcome |
|---|---|---|
| M-005 | Deadline Chain Integration | **BLOCKED, re-scoped to `NEEDS_SCOPING`.** Investigated before implementing: the deadline-extraction pipeline's output is too coarse to safely pick the right one of 14 procedure-specific legal deadline chains (civil/criminal/labor/administrative/enforcement) — auto-firing blind risks citing the wrong law to a lawyer, which is worse than no automation. Full blocker report filed with two real options for a future founder decision. No code changed. |

**Not attempted, per the board's own honest scoping (not silently skipped):** M-004 (large,
needs its own scoping pass before it's a safe TODO), M-006 (blocked on M-004), M-007/M-008/M-011
(no measured evidence exists yet to scope against — the board explicitly refuses to guess at
"improve X" without a baseline), M-009 (not reached — see below).

---

## Repository changes

7 local commits, each scoped to exactly one mission's files (no commit mixes two missions' changes):

1. `feat(intake): image upload support (Night Shift M-001)`
2. `docs(genome): Case Genome wiring verification (Night Shift M-002)`
3. `fix(search): document search reaches real content (Night Shift M-003)`
4. `feat(intake): trigger Case Pipeline from intake_kreiraj (Night Shift M-013)`
5. `docs(rokovi): M-005 blocked -- deadline chain needs a design decision`
6. `fix(security): remove PII-in-logs on every auth (SEC-058, Night Shift M-010)`
7. `fix(copilot): predmet_klijenti bugs in link-client command (Night Shift M-012)`

**Files touched (production code):** `uploaded_doc/extractor.py`, `shared/intake_worker.py`,
`routers/smart_intake.py`, `routers/search.py`, `routers/intake.py`, `shared/deps.py`, `api.py`,
`routers/copilot.py`. No schema/migration changes. No new third-party dependencies.

## Tests executed

- 30 new test files/additions across the night's missions (18+3+2+5+2 = 30 individually new test
  functions, not counting the pre-existing tests they run alongside).
- Every mission's regression sweep run and green before moving to the next mission — never batched
  or deferred to the end.
- **Final full-suite run: 2278 passed, 1 skipped, 0 failed.**

## Failures fixed
None of tonight's fixes were responding to a previously-failing test — every one was closing a gap
between what the code claimed to do and what it actually did, caught by investigation before
implementation, not by a red CI run.

## Architecture improvements
- **M-002 → M-013** is the cleanest example of this Night Shift's own discipline working as
  designed: an investigation mission produced a precisely-scoped, low-risk follow-on rather than a
  vague mandate, and that follow-on was small enough to execute the same night with high confidence.
- **M-005's blocker report** is the other side of the same discipline: recognizing that a mission's
  original scoping was wrong once investigated, and stopping rather than forcing an automation that
  could silently cite the wrong law to a lawyer — a correctness/trust failure worse than the
  missing feature itself.
- **M-012 found a 6th instance of Mission 001's bug class** the original sweep missed — direct,
  live evidence for that mission's own recommendation (a mechanical Schema Contract Check) rather
  than an abstract argument for it.

## Security improvements
SEC-058 closed (PII — user email — logged on every single authenticated request, in two independent
code paths). Scope deliberately did not expand into the larger, still-founder-blocked Security
Governance Framework / Epic B chain, per the Master Prompt's own stop condition.

## Open blockers
1. **M-005** — needs a founder-level product/risk decision (silent auto-apply with a new
   classification signal, vs. propose-then-confirm matching this codebase's existing pattern for
   uncertain AI output) before it can be safely re-scoped as a TODO. See
   `decisions/2026-08-02_M-005_deadline_chain_BLOCKER_REPORT.md`.
2. **M-007, M-008, M-011** remain `NEEDS_SCOPING` — no measured baseline exists yet to scope a real
   fix against ("OCR accuracy," "AI extraction," "performance" are not actionable without evidence
   first, and inventing a fix without it risks solving the wrong problem).
3. Nothing touched the Security Governance Framework / rate-limiting chain — that remains exactly
   where the founder parked it (Revision 2, ACTIVE BLOCKER), untouched tonight by design.

## Recommended first mission tomorrow
**M-009 (Workflow Regression Tests)** — next highest-priority eligible TODO on the board, not yet
started tonight. Recommend starting there specifically because tonight's missions (M-001/M-003/
M-013 in particular) each touched a piece of the Beta Critical Path's 9 named scenarios — a good
moment to check which of those 9 now have real end-to-end coverage versus which still don't, before
scope drifts further.

**Second priority**: bring the M-005 blocker report to the founder for the actual product decision
it's waiting on — this is the one open item that specifically needs a human call, not more
engineering investigation.

## Estimated beta readiness change
Net positive, concentrated on reliability rather than new capability — consistent with this Night
Shift's own primary objective. Concretely, against `docs/product/BETA_CRITICAL_PATH_2026-08-02.md`'s
9 scenarios: **#3 (upload PDF or photo)** moved from partially-blocked to working; **#8 (find a
case)** moved from silently-broken-for-everyone to working; **#2 (create a case)** gained the
Case Pipeline analysis it was missing on its primary path. No scenario regressed. The one scenario
this Night Shift touched and chose *not* to advance (**#7, deadlines**) was correctly left alone
rather than shipped in a state that could produce a wrong legal citation — a smaller, safer step
tonight was the right call over a larger, riskier one.
