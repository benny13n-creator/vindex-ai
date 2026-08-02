# AI Team Operating Protocol

**What this file adds that `ORG_CHART.md` and `workflows/*.md` don't:** those files define *who*
does *what*. This file defines *how a request actually enters the system and moves through it* —
the literal phase sequence, the exact input/output at each phase boundary, and the one rule that
makes this a protocol rather than a suggestion: **a phase does not start until the previous phase's
artifact exists, and a blocking gate does not get silently stepped around.**

This is the canonical execution sequence. `workflows/new_feature_workflow.md`,
`architecture_change_workflow.md`, and `bugfix_hotfix_workflow.md` are named variants of this same
protocol, scoped to specific situations. When in doubt about phase order, this file wins.

---

## Phase 0 — Founder Request

The founder states, in plain language, what they want. No format is required beyond a clear
statement of intent. Example shape:

```
FEATURE REQUEST:
Želim da Vindex automatski prepoznaje rokove iz sudskih odluka.
```

or, for a remediation/initiative rather than a feature:

```
MISSION:
Remedijacija FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md i priprema Vindex-a za enterprise
security nivo.
```

**Claude Code's first action on receiving this:** create an entry in `EXECUTION_STATE/` (see
`EXECUTION_STATE/README.md`) before doing anything else, so the mission has a place to record its
own progress from the start, not retroactively.

## Ticket/Mission scope boundary rule (founder rule, added 2026-08-02)

When a new finding surfaces mid-mission that resembles something already deliberately scoped out
(a prior decision to keep a related bug/item as "a separate ticket"), the test for whether it now
belongs in the *current* mission is **not** "is this the same class of bug" — it is **"is this the
same user-facing functionality the current mission is already touching."**

The concrete case this rule was written from (Mission 001, `predmet_klijenti` ownership integrity,
2026-08-02): a `.select("id")` duplicate-check bug was found at `copilot.py:610` and correctly kept
as a separate ticket (different feature, different workflow, different tests, different rollout —
folding it in would have added unrelated scope for no shared benefit). Later, the *exact same bug*
was found a second time, at `api.py:5245` — but this time sitting **immediately in front of** an
insert the mission was already fixing at that same call site. The founder's ruling: this one *does*
fold into the current mission, specifically because the mission was already opening that file,
already testing that endpoint, already doing that review — so the marginal cost of the additional
fix was near zero, and *not* fixing it would have meant shipping a change (removing an invalid field
from the insert) with no observable effect, since the preceding bug prevented the insert from ever
being reached at all.

**The rule, stated generally:** don't ask "have I seen this bug shape before, and did I defer it
then." Ask "does fixing this in isolation, without the other thing right next to it, actually let a
user complete the scenario this ticket exists for." If no, it's in scope regardless of whether it
resembles a bug deferred elsewhere. If yes — a different feature, a different workflow, its own
tests and rollout — it stays a separate ticket even if the bug *class* is identical. Same bug ≠ same
ticket. Same user-facing functionality = same ticket. This is the scoping-time analogue of the
Definition of Done rule in `agents/11_qa_engineering.md` — that rule catches this at verification
time if it's missed here at scoping time, but catching it here is cheaper.

## Phase 1 — Product Discovery

**Role:** Product Strategist (`agents/02_product_strategist.md`).

Answers, explicitly, in writing:
- Which problem does this solve?
- Which user/segment?
- How often does this matter (a daily friction, a rare-but-severe risk, a one-time compliance gap)?
- How is this handled today (nothing / a workaround / an existing partial mechanism)?
- What is the value of solving it?

**For a remediation/security-initiative mission** (not a feature), these same questions apply with
"problem" reframed as "risk," and "value" reframed as "risk reduction / doors this opens" — the
Product Strategist's job doesn't disappear for security work, it answers a slightly different
version of the same five questions. Skipping Phase 1 because "this is obviously necessary" is
exactly how unstated assumptions enter a plan unchallenged.

**Output:** `decisions/..._PRODUCT_SPECIFICATION.md`.

## Phase 2 — Architecture Review

**Roles:** AI CTO (`agents/01_...`) + Solution Architect (`agents/03_...`), together.

Checks:
- Does something like this already exist? (Case Genome, the Legal Reasoning Engine, an existing
  router, an existing service — per `VINDEX_CORE_CONSOLIDATION.md`'s single-owner principle.)
- Where does this belong architecturally?
- What changes, concretely — named systems, named files, named tables?
- For a remediation mission specifically: group the individual findings into coherent epics with
  named dependencies, not a flat list — an epic-and-dependency structure is itself the Architecture
  Review's output for this kind of mission, exactly as `TECHNICAL_DESIGN.md` is for a feature.

**Output:** `decisions/..._ARCHITECTURE_DECISION.md`.

## Phase 3 — Mandatory Opposition

**Role:** Red Team / Devil's Advocate (`agents/04_...`). **Always a fresh, non-fork subagent —
no exception, regardless of how confident Phase 2 was.**

This phase is not advisory. Its output is binary at the top: **FREEZE READY** or **BLOCKING**. A
BLOCKING verdict with a CRITICAL or HIGH finding means **Phase 5 (Implementation) does not start** —
not "starts cautiously," not "starts on the non-blocked parts only" unless the Red Team report
itself scopes which parts are clean. This is the phase this project's own history has proven pays
for itself every time it's actually run adversarially (Program 1's two red-team passes, SEC-031's
original peer review).

**Output:** `decisions/..._RED_TEAM_REPORT.md`.

## Phase 4 — Security Gate

**Role:** Security & Privacy Architect (`agents/05_...`).

Produces an explicit status per affected system/epic — not a prose "looks fine":

```
SECURITY_STATUS: APPROVED | CONDITIONAL | BLOCKED
```

- **APPROVED** — no open finding above LOW severity for this specific scope.
- **CONDITIONAL** — proceed, but only with the named condition met before Release Governance's
  final gate (e.g., "founder must confirm SEC-038's live-test result before this ships").
- **BLOCKED** — do not proceed; same veto weight as a Red Team BLOCKING verdict.

**Output:** `decisions/..._SECURITY_REVIEW.md`. See `REVIEW_GATES.md` for the full state table
across all gate-holding roles, not just this one.

## Phase 5 — Implementation

**Roles:** Backend Engineering + Frontend Engineering (`agents/09_...`, `agents/10_...`).

Only starts once Phases 3 and 4 both show a non-blocking status. Produces
`decisions/..._IMPLEMENTATION_PLAN.md`, then the actual diff.

**For a remediation mission where the founder has explicitly said "do not modify production code
yet"**: Phase 5 does not execute. The mission's deliverable stops at an approved, gated
`IMPLEMENTATION_PLAN.md`-shaped remediation plan, explicitly marked as pending a separate go-ahead
before any diff is written — mirroring exactly how Program 1's own specification work stopped at
Stage 4/5 of the Finding Lifecycle without Stage 6 (Implementation) starting.

## Phase 6 — QA

**Role:** QA Engineering (`agents/11_...`). Release-blocking, per its own charter.

## Phase 7 — Release Governance

**Role:** Release Governance (`agents/12_...`). Final, absolute gate. Verifies every artifact above
actually exists and every non-APPROVED/non-FREEZE-READY status was either resolved or explicitly,
individually accepted by the founder in writing.

---

## The one rule underneath all seven phases

**A phase's artifact is the only proof that phase happened.** "I thought about security" is not a
Security Gate. "This seems architecturally fine" is not an Architecture Review. If the artifact
doesn't exist in `decisions/`, the phase didn't happen, no matter how much informal reasoning
preceded it — this is the same discipline this project already applies to its own Finding
Lifecycle ("Verified Fix" requires actual passing tests, not the belief that it would pass) and to
its own security claims (`PUBLIC_SECURITY_CLAIMS.md` requires evidence, not confidence).
