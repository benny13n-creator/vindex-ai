# Architecture Decision Record — [Title]

**Author (role):** AI CTO / Chief Architect
**Date:**
**Status:** Draft / Under Red Team Review / Approved / Rejected / Superseded by [link]
**Finding Lifecycle stage (if applicable):** per `docs/security/FINDING_LIFECYCLE.md`

## Problem
What is actually wrong, missing, or needed? State it as observed, not as the solution already
assumed. Cite evidence (file:line) if this is about existing-code behavior, not a hypothetical.

## Proposed Solution
The recommended approach, in enough detail that Solution Architecture can proceed from it.

## Affected Systems
Name specifically — which routers, tables, existing capabilities (Case Genome / Legal Reasoning
Engine / AI Governance Layer / entitlement system / audit system) this touches or depends on.
Check against `docs/architecture/VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md` and
`docs/architecture/VINDEX_CORE_CONSOLIDATION.md` — does this duplicate an existing owner of this
concept?

## Risks
Named explicitly, each with a severity. Do not omit a risk because the proposed solution seems to
mitigate it — state the risk, then state the mitigation, so a reader can judge whether the
mitigation is actually sufficient.

## Alternatives Considered
Every alternative that was seriously considered, and the specific reason it was rejected — not "we
went with X" alone. (Precedent: Program 1 §1.1's chokepoint options table, §1.4's rejected
event-loop bridge — both state the alternative, why it was tempting, and why it failed.)

## Final Recommendation
The decision, stated unambiguously, plus what would need to change for this decision to be revisited
(a trigger condition, not "if we feel like it later" — precedent: Program 1 §1.1's "revisit option
(b) only if/when a second real provider is actually being integrated").

## Sign-off
- [ ] Red Team reviewed (link to `RED_TEAM_REPORT.md`, verdict: ______)
- [ ] Security & Privacy Architect reviewed (link to `SECURITY_REVIEW.md`, if applicable)
- [ ] Founder sign-off (required for architecture-level changes — see `workflows/architecture_change_workflow.md`)
