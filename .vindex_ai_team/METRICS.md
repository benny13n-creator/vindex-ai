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

---

## 2026-08-03 (Operation Lawyer Zero, BETA-001)

| Metric | Value |
|---|---|
| Missions completed | 3 (LZ-001, LZ-002, LZ-003) |
| Bugs fixed | 2 — LZ-001 (reminder cron blind to AI-extracted deadline vocabulary), LZ-002 (missing-document detector blind to Smart-Intake-ingested documents, wrong classifier vocabulary written to the field it reads) |
| New bugs discovered | 1 — a possible DB `CHECK`-constraint violation on `predmet_hronologija.vaznost` for values already being written in production (`"bitan"`, `rokovi_lanac.py`'s mapped values) — found, not fixed, deliberately deferred as `LZ-005` pending a full reader audit |
| Blockers correctly escalated | 1 — the full `vaznost` vocabulary unification (`LZ-005`), same discipline as the prior night's `M-005`: investigated, found real risk in changing writers blind (would silently break `api.py`'s existing `_VAZNOST_ORDER`), narrowed to the safe read-side fix instead of guessing at the larger one |
| Regressions introduced | 0 — confirmed by a full-suite run at the end (2289 passed, 1 skipped, 0 failed) |
| Test pass rate | 2289/2290 (99.96%) |
| Beta blockers removed | 3 sub-capability gaps closed within already-tracked Beta Critical Path scenarios (not full scenario state-flips, reported precisely rather than inflated): automatic reminders now actually fire for AI-extracted deadlines (scenario #7-adjacent); the platform's sole deterministic missing-document detector now has a real signal for Smart-Intake-ingested documents (scenario #5/#10-adjacent); global search now covers tasks and evidence type (scenario #8, extending M-003's prior-night fix) |
| Security findings resolved | 0 new SEC-XXX items — this run was product/automation-focused, not a security-finding sweep. Worth recording separately: 1 real tenant-isolation risk was *avoided*, not resolved (it never shipped) — `LZ-003`'s task-search implementation found `zadaci` has no `user_id` column and deliberately scoped to a safe subset rather than copy the wrong pattern from the other 6 search branches |
| Founder decisions required | 1 — `LZ-004` (auto-create tasks from AI findings) needs a founder call on auto-apply vs. propose-then-confirm, the same class of question `M-005` raised the prior night |

**Notable pattern, second occurrence:** twice tonight (`LZ-001`, `LZ-002`), a "wire up a disconnected
system" mission turned out on inspection to be "a field is already being populated automatically —
with the wrong value" rather than "nothing runs at all." Worth treating as a standing hypothesis to
check first in any future mission of this shape, not just this one: before assuming a downstream
consumer has *no* signal, check whether it has the *wrong* signal.

---

## 2026-08-03 (Operation Autonomous Law Office, BETA-002)

| Metric | Value |
|---|---|
| Missions completed | 3 (ZTC-001, ZTC-002, ZTC-003) |
| Bugs fixed | 3 — ZTC-001 (batch upload created N cases instead of 1, plus a `redni_broj` collision bug found while fixing it), ZTC-002 (Genome silently dropped documents past #25, ordered by upload date not recency, and its own "documents skipped" counter always read ~0 for exactly the cases where it mattered), ZTC-003 (conflict-of-interest check never ran anywhere in the document-first case-creation flow) |
| New bugs discovered | 2 — the `redni_broj` hardcode (found while implementing ZTC-001, same user-facing fix, folded into the same mission per this project's own ticket-scoping rule); the Genome concurrent-refresh race condition (found while investigating Scenario G, fixed alongside it since ZTC-001 makes it materially more frequent) |
| Blockers correctly escalated | 1 — **the single largest finding of this run**: Smart Intake (the entire pipeline this session and last improved) has zero frontend entry point — no lawyer can reach it through the app today. Not a wiring fix; a founder-level product/design decision. Full report: `decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md` |
| Regressions introduced | 0 — confirmed by a full-suite run at the end (2306 passed, 1 skipped, 0 failed; was 2289/1/0 before tonight) |
| Test pass rate | 2306/2307 (99.96%) |
| Beta blockers removed | 3 sub-capability gaps closed, all directly against the founder's own Zero-Touch Case success criterion (not yet reachable by a lawyer pending ZTC-000, but real once it ships): batch document uploads now produce one case instead of N; Case Genome no longer silently loses a large case's most recent documents; conflict-of-interest checking now runs automatically for document-first case creation |
| Security findings resolved | 0 new SEC-XXX items — this run was product/workflow-focused. Note: the conflict-check auto-wiring (ZTC-003) is arguably closer to a compliance/ethical-duty fix than a security one — recorded here for completeness, not counted as a SEC-XXX closure since none was opened for it |
| Founder decisions required | 1 — ZTC-000 (which of three frontend-wiring options to pursue; the report explicitly recommends this be brought to the founder before any UI is built) |

**Notable pattern, third occurrence:** the "wrong value being reported, not no value at all" pattern
from Operation Lawyer Zero (`LZ-001`, `LZ-002`) appeared again in `ZTC-002`: Case Genome's own
"documents skipped" counter looked like a working truncation-visibility feature, but was computed
from data the caller had already silently pre-truncated — so it read ~0 for exactly the cases where
truncation was real. Three occurrences across two nights makes this worth treating as close to a
standing law for this codebase: any "here's what we excluded/skipped/couldn't process" counter should
be checked against the *true* upstream total, not an already-filtered intermediate, before being
trusted.

**New pattern, first occurrence this run:** the largest, most consequential finding of the night was
not a bug in existing logic at all — it was the *absence* of any way to reach the logic in the first
place. Two full nights of wiring fixes (LZ-001/002, ZTC-001/002/003) improved a pipeline's output
quality without ever checking whether the pipeline's *input* (the upload button) was reachable from
the product. Worth a standing check in any future mission of this shape: before deep-wiring a
backend pipeline's internals, confirm the frontend actually calls it.

---

## 2026-08-03 (Operation Invisible Features, BETA-003)

| Metric | Value |
|---|---|
| Missions completed | 2 (IF-001 GDPR self-service account deletion, IF-002 per-case AI Briefing) |
| Bugs fixed | 0 — this run's charter was reachability, not correctness; nothing was broken, it was unreachable |
| New bugs discovered | 0 code bugs. 1 tooling defect: the repo's own `scripts/audit_routers.py` has a `/health`-substring false negative (masked Smart Intake from the prior mission) and dynamic-path false positives (`oblasti`, `ugovor_zastupanja` wrongly flagged dead) — documented, not fixed (out of this mission's scope) |
| New bugs discovered (product) | 2 real duplicate-feature pairs found: client CSV import (safer flow is the dead one), WhatsApp notifications (dedicated system is the dead one, simpler flag-based one is live) — both escalated as founder decisions, not resolved unilaterally |
| Blockers correctly escalated | 3 — `IF-003` (which CSV import flow should be live), `IF-004` (retire vs. reconnect WhatsApp subscriptions), `IF-005` (Memory Graph has no automatic way to populate itself — shipping a query UI alone would show a permanently empty result) |
| Regressions introduced | 0 — no backend code changed this run; full suite re-run anyway per this mission's own Phase 7 requirement: 2306 passed, 1 skipped, 0 failed (unchanged) |
| Test pass rate | 2306/2307 (99.96%), unchanged — frontend-only changes have no automated test harness in this repo (verified via `node --check` for syntax validity only) |
| Beta blockers removed | 0 scenario state-flips — this run's value is orthogonal to the Beta Critical Path scenarios (self-service compliance rights, case-level AI recommendation), not double-counted against them |
| Security findings resolved | 0 new SEC-XXX items. Adjacent finding: `IF-001` closes a public-facing compliance gap (a whitepaper promise with no button) — recorded here for completeness, not filed as a SEC-XXX since none was open |
| Founder decisions required | 3 (`IF-003`, `IF-004`, `IF-005`) |

**Notable pattern, first occurrence this run:** unlike every prior mission this multi-night engagement,
this run's two completed missions required **zero backend changes** — both were cases of already-
correct, already-tested backend code with genuinely no frontend caller at all. The actual engineering
work was verification (is this really unreachable, is the "obvious" fix actually a duplicate of
something already live) rather than implementation — the GDPR export check and the CIO/case-
intelligence distinction both would have produced a shipped duplicate if skipped. Worth treating
"verify it's not secretly already covered" as a mandatory step before wiring anything flagged by a
census, not an optional nicety.

---

## 2026-08-03 (Operation Lawyer Day, BETA-004)

| Metric | Value |
|---|---|
| Missions completed | 1 (LD-001 — photo upload fix on the reachable path) |
| Bugs fixed | 1 — but a significant one: a previously-*claimed*-fixed Beta Critical Path blocker (Night Shift M-001's "photo upload works end to end") was found to still be broken for real users, because the fix landed on an unreachable endpoint |
| New bugs discovered | 1 (the above, counted once as a workflow, not per line changed) + 6 smaller P2/P3 gaps found and deliberately NOT fixed per this mission's own "only implement P0/P1" instruction (no true batch upload / no dedup on the reachable path / no hearing-prep export bundle / no audit-log viewer / archiving not reachable from case-detail / team comments missing from search) |
| Blockers correctly escalated | 1 — Smart Intake's missing frontend entry point, re-confirmed as still the dominant open item, not re-litigated as a new finding |
| Regressions introduced | 0 — full suite re-run: 2311 passed, 1 skipped, 0 failed (was 2306 before this mission) |
| Test pass rate | 2311/2312 (99.96%) |
| Beta blockers removed | 1 scenario **corrected**, not newly removed — Beta Critical Path scenario #3 ("upload PDF or photo") was marked closed 2026-08-02 but wasn't true for the reachable path; it is now |
| Security findings resolved | 0 |
| Founder decisions required | 0 new this run — LD-002 through LD-006 are P2/P3 backlog items needing no founder judgment call, just future prioritization |

**Notable pattern, most consequential of this whole engagement**: this is the first mission to run a
full end-to-end simulation rather than investigate a single subsystem — and it found that a previous
mission's own "fixed" claim was wrong in practice, not in principle. The lesson generalizes past this
specific bug: **verifying a fix requires tracing which endpoint the frontend actually calls for that
scenario, not just confirming the code that was changed is correct.** Every subsystem-level
investigation this engagement has run (Night Shift, Lawyer Zero, Autonomous Law Office, Invisible
Features) was individually careful — this mission's value came specifically from simulating the
connected, cross-subsystem path a real user follows, which no single-subsystem investigation could have
caught.

---

## 2026-08-03 (Operation Beta Lockdown, BETA-005)

| Metric | Value |
|---|---|
| Missions completed | 1 (BL-001 — cross-tenant task-leak fix) |
| Bugs fixed | 1 — but the most severe security finding of this entire multi-night engagement: a live, exploitable cross-tenant data leak, not a workflow gap |
| New bugs discovered | 1 (the above) + 1 new hidden-feature finding sharing Smart Intake's exact shape (draft staging/approval pipeline, zero frontend callers) + confirmed ~80% of the defined audit-action taxonomy never fires in production |
| Blockers correctly escalated | 5 — Smart Intake frontend (reconfirmed, not new), draft staging/approval frontend (new), client CSV import fragmentation (reconfirmed), WhatsApp fragmentation (reconfirmed), Memory Graph population strategy (reconfirmed) |
| Regressions introduced | 0 — full suite run twice this mission (immediately after the fix, and as this mission's own final gate): 2315 passed, 1 skipped, 0 failed both times |
| Test pass rate | 2315/2316 (99.96%) |
| Beta blockers removed | 1 critical security finding — arguably the highest-severity single item removed in this entire engagement, since an undetected cross-tenant leak would have been disqualifying for Beta regardless of how complete every other feature was |
| Security findings resolved | 1 — the `zadaci_za_predmet` IDOR, found and fixed same night, verified via negative control |
| Founder decisions required | 0 new — the 5 escalated blockers were already identified by prior missions tonight; this mission reconfirmed rather than discovered them (except BL-002, newly found) |

**Notable pattern, this run**: the most severe finding of the entire 6-operation engagement was found
not by a security-focused mission, but by a *tenant-isolation spot-check* performed as one dimension of
a broader completion audit. Worth generalizing: routine "does this look right" sweeps across
high-traffic endpoints — not only dedicated security missions — are a legitimate and apparently
necessary way to catch this bug class. Also worth noting: this exact defect shape (missing ownership
check) was the subject of a prior, well-executed, *specifically security-focused* sweep (`SEC-001`,
2026-07-23) that correctly and thoroughly covered every mutation endpoint — but declared its scope as
mutations only, leaving an identically-shaped read-endpoint gap unexamined for two weeks. A scoped
sweep's own stated boundary is exactly where the next instance of the same bug class tends to hide.

---

## 2026-08-03 (Operation Beta Closure, BETA-006)

| Metric | Value |
|---|---|
| Missions completed | 2 (BC-001 Smart Intake UI, BC-002 draft staging/approval UI) |
| Bugs fixed | 0 — this run built new frontend surface for existing, correct backend logic; nothing was broken |
| New bugs discovered | 0 — one clarifying correction made instead: this engagement's own prior claim about draft approval ("promotes into predmet_dokumenti") was verified precisely and found to be conditional (only when confidence_score >= 0.85), not unconditional as the prose implied — the new UI surfaces this honestly rather than overclaiming |
| Blockers correctly escalated | 0 new — the 3 remaining blockers (CSV import, WhatsApp, Memory Graph) are unchanged founder decisions from Beta Lockdown, not re-investigated this run |
| Regressions introduced | 0 — no backend code changed; full suite re-run as this mission's own final gate: 2315 passed, 1 skipped, 0 failed, identical to before this mission |
| Test pass rate | 2315/2316 (99.96%), unchanged |
| Beta blockers removed | **2** — the two Level-3 ("backend complete, frontend absent") findings from Operation Beta Lockdown's Feature Completion Matrix, the dominant completion gap identified across all six prior operations tonight |
| Security findings resolved | 0 new — inherited tenant isolation from unchanged backend endpoints; no new attack surface introduced |
| Founder decisions required | 0 new — this mission's own Master Prompt pre-authorized the one product decision (build Smart Intake's UI) every prior mission had correctly escalated instead of guessing at |

**Notable pattern, this run**: this is the first mission all engagement where the founder's own
instructions directly resolved a standing blocker rather than asking the organization to investigate or
guess at one. Five prior missions independently arrived at "Smart Intake needs a founder decision on
which UI approach to take" — when that decision arrived explicitly in this mission's Master Prompt
("reuse existing backend/APIs/AI pipeline"), the actual build was straightforward specifically because
five separate investigations had already fully characterized the exact API contract, the exact
workflow shape, and the exact risk (multi-document-to-one-case batching, rate-limit-aware polling) in
advance. Worth the lesson: correctly escalating a decision instead of guessing doesn't just avoid a
wrong guess — it means the eventual authorized implementation has zero remaining unknowns to discover
mid-build.

---

## 2026-08-03 (Operation Wow Factor, BETA-007)

| Metric | Value |
|---|---|
| Missions completed | 2 (WOW-001 Winning Strategy Brief, WOW-002 post-upload recap) |
| Bugs fixed | 0 — pure composition of already-correct capabilities |
| New bugs discovered | 0 code bugs. 1 real gap found (WOW-003): Smart Intake extracts judge/opponent entities but never writes them onto the case row, so two Litigation Intelligence features can't be auto-populated for free — flagged, not fixed (real backend change, outside this mission's compose-only scope) |
| Blockers correctly escalated | 1 — WOW-003, a genuine small backend change correctly deferred rather than squeezed into a "composition-only" mission |
| Regressions introduced | 0 — no backend code changed; full suite re-run as final gate: 2315 passed, 1 skipped, 0 failed, unchanged |
| Test pass rate | 2315/2316 (99.96%), unchanged |
| Beta blockers removed | 0 in the formal sense (no Beta Critical Path scenario was blocked before this mission) — this run's value is "perceived value"/UX quality, the mission's own explicit target, not blocker removal |
| Security findings resolved | 0 — no new attack surface; every composed call runs through the existing routing layer so authorization/billing/tier-gating for each endpoint is unchanged |
| Founder decisions required | 0 new |

**Notable pattern, this run**: unlike every mission before it tonight, this run's starting point was
not a bug, a gap, or a missing UI — it was two already-correct, already-shipped features (this
engagement's own prior work, from 2 and 5 missions ago) that had simply never been introduced to each
other. The highest-value "compound value" opportunity wasn't found by looking for what's broken; it
was found by asking which of tonight's OWN already-completed missions solve adjacent parts of the same
question. Worth carrying forward: after a long engagement of individually-correct fixes, a dedicated
composition pass over what's already been built is itself a distinct, valuable kind of audit — not
redundant with the bug-finding sweeps that came before it.

---

## 2026-08-03 (Project Synapse, BETA-008)

| Metric | Value |
|---|---|
| Missions completed | 4 (SYN-001 date-bug fix, SYN-002 Event Bus wiring, SYN-003 Copilot→Genome, SYN-004 Firm Brain→Genome) |
| Bugs fixed | 1 — a real, pre-existing, silent date-comparison bug (naive vs. aware datetime) that made critical-hearing detection always return empty for any hearing stored as a plain date, the realistic shape for a production DATE column |
| New bugs discovered | 1 (the above — found while wiring an unrelated Event Bus connection, not while looking for bugs specifically) |
| Blockers correctly escalated | 3 — `SYN-005` (needs new handler logic, outside orchestration-only scope), `SYN-007` (`knowledge_profiles` needs a founder decision), `SYN-008` (reconfirmed from last mission's `WOW-003`, still not attempted) |
| Regressions introduced | 0 — full suite re-run as final gate: 2329 passed, 1 skipped, 0 failed (was 2315 before this mission) |
| Test pass rate | 2329/2330 (99.96%) |
| Beta blockers removed | 0 in the formal sense — this mission's charter was architectural coherence ("one intelligence"), not blocker removal; value is measured in reduced duplicated reasoning and 2 newly-functional proactive alerts |
| Security findings resolved | 0 — no new attack surface; every change reuses existing auth/billing/tenant-scoping exactly as it already worked |
| Founder decisions required | 2 new-ish (`SYN-007`, whether to build real `knowledge_profiles` extraction or retire it as a Briefing input) — `SYN-008` is a reconfirmation of an already-known item, not new |

**Notable pattern, this run — the same lesson recurring a third time this engagement**: connecting
`ROK_KRITICAN` (Event Bus wiring) required first fixing a silent bug in the exact signal that event
needed to carry. This is the same shape as Beta Lockdown's IDOR (found via an isolation sweep, not a
security-specific one) and Lawyer Day's photo-upload correction (found via a full-workflow simulation,
not a targeted bug hunt) — **the most valuable bugs this entire engagement has found were discovered
as a side effect of connecting or verifying something else, not by looking for bugs directly.** Worth
treating "trying to wire X" as itself a productive bug-finding method, not just an orchestration task.

---

## 2026-08-03 (Project Nexus, BETA-009)

| Metric | Value |
|---|---|
| Missions completed | 3 (NEX-001 CCC dedup, NEX-002 zadaci.py AI grounding, NEX-003 Genome-refresh toast fix) |
| Bugs fixed | 3 — `ccc.py`'s missing `tip_dokaza` column (a live bug making "missing documents" always show everything as missing, regardless of reality), `ccc.py`'s independently-duplicated copy of the naive/aware datetime bug (eliminated by removing the duplicate formula entirely), the Genome-refresh false-success-toast |
| New bugs discovered | Same 2 as "bugs fixed" above — found while verifying a fork's Phase-5 duplication finding, not while hunting bugs directly (4th occurrence of this engagement's recurring pattern) |
| Blockers correctly escalated | 4 — `NEX-004` (Event Bus durability, needs idempotency verification first), `NEX-005` (new handler logic needed), `NEX-006` (founder decision on AI provenance strategy), `NEX-007`/`NEX-008` (well-precedented future work, not attempted this mission) |
| Regressions introduced | 0 — full suite re-run as final gate: 2334 passed, 1 skipped, 0 failed (was 2329 before this mission) |
| Test pass rate | 2334/2335 (99.96%) |
| Beta blockers removed | 0 in the formal Beta Critical Path sense — this mission's value is architectural integrity (eliminating 2 real "two sources of truth" violations), measured via the new Intelligence Connectivity Score, not scenario completion |
| Security findings resolved | 0 new — no new attack surface; this mission's fixes reuse existing auth/tenant-scoping unchanged |
| Founder decisions required | 2 pure (`NEX-006` provenance strategy, plus the 2 unchanged duplicate-feature pairs from earlier missions), 1 needing investigation-then-decide (`NEX-004`) |

**New this run**: a formal Intelligence Connectivity Score (ICS) — 20 of 32 verified required
connections, **62.5%**, against the founder's own >90% pre-beta target. See
`docs/architecture/NEXUS_ICS_SCORE.md` for the full connection ledger and methodology. This is the
first numeric, trend-trackable measure of architectural fragmentation this engagement has produced —
future missions touching these modules should recompute it the same way (same connection list, same
exclusion criteria for deliberately-sealed modules) rather than redefining the methodology.

**Notable pattern, this run — the 4th occurrence**: yet again, the two real bugs found and fixed this
mission (a live, silently-wrong "missing documents" bug in `ccc.py`, and an independently-duplicated
copy of a datetime bug already fixed once this engagement in a different file) were found while
verifying a fork's duplication-audit finding, not while looking for bugs. This is now confirmed across
4 consecutive missions (Beta Lockdown, Lawyer Day, Project Synapse, Project Nexus) — strong enough to
treat as a standing operating principle for this codebase specifically: any "connect/verify/eliminate a
duplicate" task should be treated as an implicit bug-hunting task too, not a pure refactor.
