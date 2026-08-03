# Review Pipeline — Mission Olympus Governance Board

**What this adds that `OPERATING_PROTOCOL.md` doesn't**: that file governs a *new feature request* moving
from Phase 0 (Founder Request) through Phase 7 (Release Governance) — everything happens **before**
implementation exists, except Phases 5-7. This file governs the review of a **completed change** — a
diff, a finished autonomous mission's output, a migration — **after** it exists, **before** it merges.
Same underlying principle (`OPERATING_PROTOCOL.md`'s "a phase's artifact is the only proof that phase
happened"), applied to a different object.

---

## Phase G0 — Change Intake

**Role:** Enterprise AI Director (Agent 16).

Classifies the change: is it "major" per `AI_GOVERNANCE_ARCHITECTURE.md`'s threshold (any autonomous
mission; any change touching >1 router/service file; any new migration; any change to a canonical shared
module)? If not major, this pipeline does not apply — the change follows whatever lighter process already
governs it (a copy fix needs no board, per `README.md`'s existing proportionality principle).

If major: the Director selects every board the change requires, per the routing table in
`AI_GOVERNANCE_ARCHITECTURE.md` (minimum 4: Architecture, Reliability & Chaos, one relevant AI Excellence
Board agent, one Product Board agent — plus any path-pattern-triggered boards).

**Output:** a routing decision — which of Agents 05, 14, 17–34 are invoked for this specific change, and
why (cite the specific file/pattern that triggered each). Filed as
`decisions/..._GOVERNANCE_ROUTING.md`.

## Phase G1 — Parallel Board Review

**Roles:** every agent selected in Phase G0, invoked **fresh** (never a fork — see
`AI_GOVERNANCE_ARCHITECTURE.md` rule 1), in parallel where boards don't depend on each other's output.

Each agent receives: the change itself (diff, file list, or mission report), the original problem
statement/mission charter it claims to address, and the scope boundary for its own review (per
`AGENT_COMMUNICATION_PROTOCOL.md`'s standard prompt structure). Each produces one report in the
mandatory 7-field format (`AGENT_COMMUNICATION_PROTOCOL.md`).

Some boards genuinely depend on another's output and cannot run in parallel with it (e.g., Regulatory
Compliance Verification (27) is Consulted by Security (05) per the RACI matrix — Security's review
should exist before Compliance finalizes its own). Where a dependency exists, it is stated in
`AGENT_RESPONSIBILITY_MATRIX.md`'s Consulted column; everything else runs in parallel by default, matching
this engagement's own proven fork-parallelism pattern (Sentinel/Phoenix/Keystone's 4-7 simultaneous
investigation forks).

**Output:** one report per invoked agent, filed under `decisions/`, named per
`AGENT_COMMUNICATION_PROTOCOL.md`'s convention.

## Phase G2 — Aggregation

**Role:** Enterprise AI Director (16).

Collects every report from Phase G1. Checks, mechanically, per `QUALITY_GATES.md`'s state table:
- Does every invoked agent have a filed report? (A missing report is treated as BLOCKED, same rule as
  `REVIEW_GATES.md`'s existing rule #4, extended here.)
- Does any report carry a Critical finding?
- Does any report carry a blocking gate-state (see `QUALITY_GATES.md`)?

**Output:** `decisions/..._GOVERNANCE_AGGREGATION.md` — a single table, one row per invoked agent, with
its gate-state and headline finding (if any).

## Phase G3 — Escalation (only if triggered)

**Role:** whichever veto-holding agent raised the Critical/blocking finding, escalating per
`DECISION_ESCALATION_POLICY.md`. Same absolute rule as the existing organization's
`ESCALATION_RULES.md`: no agent — not the Enterprise AI Director, not Release Governance — overrides a
veto except the founder, in writing.

**Output:** either the finding is resolved and the fix re-enters Phase G1 for the specific board(s) it
touches (narrowing-scope re-check, per `ESCALATION_RULES.md`'s existing "narrowing pass" discipline —
not a full re-audit), or the founder records an explicit written risk acceptance.

## Phase G4 — Final Merge Recommendation

**Role:** Enterprise AI Director (16). **Accountable: the founder** (per
`AGENT_RESPONSIBILITY_MATRIX.md`'s last row — the Director aggregates, it does not have independent
authority to approve a merge the founder hasn't sanctioned).

Binary at the top, same discipline as Red Team's `FREEZE READY`/`BLOCKING` split: **RECOMMEND MERGE** or
**DO NOT RECOMMEND MERGE**, with every board's status listed. A single unresolved Critical from any board
makes this negative — no averaging, no "mostly fine," matching the mission's own explicit rule
("Ako bilo koji agent označi Critical rizik: merge preporuka mora biti negativna").

**Output:** `decisions/..._GOVERNANCE_FINAL_RECOMMENDATION.md`.

---

## Relationship to the existing 7-phase protocol

If the change under governance review is itself a *new feature* that already went through
`OPERATING_PROTOCOL.md`'s Phases 0–7, this pipeline does not re-run those phases — it reviews the
*outcome* (what was actually built) independently of what was *approved* in Phase 2/3/4, which is exactly
why Architecture Review (17) is a distinct agent from AI CTO (01): approval-before-the-fact and
verification-after-the-fact are structurally different checks, and conflating them (the same agent
approving its own prior approval) would violate the "no agent reviews its own work" rule.
