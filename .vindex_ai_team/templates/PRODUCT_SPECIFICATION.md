# Product Specification — [Feature Name]

**Author (role):** Product Strategist
**Date:**

## User Problem
The specific lawyer workflow, pain point, or explicit request this responds to. Not "this would be
useful" — trace to an observation: a pilot session, a support ticket, an Evidence Matrix finding
(per `docs/architecture/VINDEX_AI_PILOT_SUCCESS_FRAMEWORK_v1.0.md`), or an explicit founder
directive with its own stated reasoning.

## User Story
As a [solo lawyer / small firm lawyer / firm partner / firm associate], I want to [ ], so that [ ].

## Who Benefits, and Who Doesn't Yet
Name the customer segment explicitly. Cross-check
`docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md` §15 — some capabilities are not yet
appropriate for some segments (e.g., anything implying shared AI context across matters requires
SEC-054's ethical-wall gap closed first for firm-size segments).

## Why Now, Not Later
Is this MVP-relevant, or would deferring it cost nothing? State explicitly what happens if this is
NOT built this cycle.

## Acceptance Criteria
Concrete, testable conditions — what QA Engineering will actually check.

## Priority
P0 / P1 / P2 / P3, with reasoning (per `docs/security/SECURITY_ROADMAP.md`'s own P0-P3 sequencing
discipline: ROI, risk/value reduction, complexity — judgment calls stated as judgment calls, not
disguised as formulas).

## Success Metrics
How will we know this actually landed with real users, not just shipped? Prefer a Rule A/B/C-style
evidence plan over a vanity metric.

## Explicitly Out of Scope
What this feature deliberately does NOT do — prevents scope creep during design and implementation.
