# Technical Design — [Feature Name]

**Author (role):** Solution Architect
**Date:**
**Product Specification:** [link]

## Existing-Functionality Check
Can Case Genome, the Legal Reasoning Engine, the AI Governance Layer (in progress), the entitlement
system, or an existing router already solve most of this? State explicitly what was checked and
why it doesn't already cover this — do not skip this section even when the answer is obviously "no
existing system does this."

## Design
Services, modules, APIs, database changes, event flows, integrations — the concrete shape.

## Patterns Reused
Which existing, proven patterns does this design reuse (ownership-check pattern, chokepoint
monkeypatch technique, sync/async service-pair split, `PermissionService`/`UsageService`
separation, etc.)? A design that reinvents something an existing pattern already does correctly
needs an explicit justification in "Alternatives Considered" below.

## Database Impact
Any new tables, columns, migrations? If yes — flag for Database Architect review, and state
explicitly: owner/creator column type + FK plan, `ON DELETE` behavior, RLS policy (understanding
that RLS is defense-in-depth, not the enforcement mechanism, per SEC-004).

## Security-Relevant Surface
Any new authentication, authorization, PII handling, AI-provider data flow, or secret? Flag for
Security & Privacy Architect review — do not assume "this is simple, security review can be light"
without the Security Architect making that call itself.

## Alternatives Considered
What else was considered, and why it was rejected.

## Open Questions
Anything this design doesn't resolve yet, requiring the AI CTO, Security Architect, or founder's
input before implementation can start.
