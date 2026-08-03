# Decision Escalation Policy — Mission Olympus Extension

**What this adds to `ESCALATION_RULES.md`**: that file is the canonical escalation reference for the
pre-existing 15-role organization. This file extends it for Mission Olympus's 19 new roles. **The core
principle is identical and not restated in full here** — read `ESCALATION_RULES.md` first. This file adds
only what's new: which of the 19 new roles hold veto weight, and the escalation paths specific to
cross-board disagreements this new roster introduces.

## Veto-holding roles among Agents 16–34

Per `QUALITY_GATES.md`'s blocking-state column: **17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 31,
32, 33** hold veto weight (a blocking state halts the pipeline exactly like `ESCALATION_RULES.md`'s
existing veto roles). **16 (Enterprise AI Director), 29 (Beta Experience), 34 (Technical Debt Curator)**
do not — they aggregate, simulate, or advise, respectively, matching the same non-veto pattern
`ESCALATION_RULES.md` already applies to the Standup Reporter (13) and Compliance/Enterprise Readiness
(14).

**Same absolute rule as the existing organization**: no agent — including the Enterprise AI Director —
overrides a veto except the founder, in writing. The Director's aggregation authority is procedural
(ensuring every required board ran, collecting results) — it is explicitly not a superseding authority
over any individual board's blocking verdict.

## New escalation paths this roster introduces

| Situation | Escalates to | Resolution mechanism |
|---|---|---|
| Regulatory Compliance Verification (27) returns `BLOCKED` | Founder | Same as Security & Privacy Architect's existing path — a regulatory violation on real client data (e.g., Keystone's K-1 GDPR finding) is not merely advisory, it is founder-decision-required in writing, same weight as a Security block |
| AI Grounding (23) and AI Explainability (22) disagree (a conclusion is well-reasoned but the reasoning itself isn't evidenced, or vice versa) | Both findings stand independently — this is not a genuine disagreement to arbitrate, it is two orthogonal checks correctly returning different verdicts on different questions (see `AI_GOVERNANCE_ARCHITECTURE.md`'s explicit boundary between the two) |
| Product Consistency (28) and Workflow Integrity (30) both flag the same underlying gap from their two different lenses (expectation vs. connectivity) | Not a disagreement — file both findings, the Director notes the shared root cause in the aggregation table rather than treating it as duplicate/conflicting input |
| Architecture Review (17) finds the completed change diverges from what AI CTO (01) originally approved | AI CTO (01) — same as `ESCALATION_RULES.md`'s existing rule for CTO/Solution Architect disagreements: the factual question ("does the diff match the approved design") is checked against the actual approved artifact before being treated as a judgment call |
| Metrics Guardian (31) finds a metric published in a mission report used an inconsistent methodology vs. a prior mission's figure for the same metric (the exact Keystone ICS/CIC shape) | The mission/report's author corrects the report — Metrics Guardian's finding is evidence-grounded and not itself negotiable, but does not require founder escalation unless the inconsistency changes a prior Beta Gate or release decision's validity |
| Performance & Scalability (32) flags a regression with no prior baseline to compare against | Founder — per `AI_GOVERNANCE_ARCHITECTURE.md`'s own honest note that this agent has zero historical precedent; its first several findings should be treated as establishing baselines, not as blocking regressions, until a real baseline exists |
| Any new-roster agent disagrees with a prior *closed* finding from Agents 01–15 | Do not silently re-litigate — same rule as `ESCALATION_RULES.md`'s existing "CLOSED findings are locked" principle, extended: a new agent re-opening an old CLOSED finding must state explicitly why (code/architecture changed), not just "a different agent looked at it" |

## CLOSED findings lock rule — extended to the new roster

`ESCALATION_RULES.md`'s existing rule ("CLOSED findings are locked... reopens only if the underlying code
or architecture it was verified against changes") applies identically to every Agent 16–34 finding marked
CLOSED after a genuine falsification attempt. A later governance pass (by any agent, old or new roster)
does not reopen it "just to be sure."

## What "in writing" means — unchanged

Identical to `ESCALATION_RULES.md`'s existing definition: a dated entry in `decisions/*.md` or
`memory/*.md`, never a chat message alone.
