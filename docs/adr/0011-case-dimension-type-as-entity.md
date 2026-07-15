# ADR-0011: Dimensions are a lookup table, not a CHECK-constrained string

- Status: Accepted
- Date: 2026-07-15

## Context

The first draft of `case_dimension_history.dimension` was a CHECK-constrained
string enum (`health|risk|strategy|evidence_strength|confidence|
completeness|profitability`) — consistent with how `feature_type`, `status`,
and `priority` are handled elsewhere in the schema. The objection: a
free-text-shaped column, even constrained, invites drift (`risk` vs `Risk`
vs `RISK` vs `legal_risk` vs `risk_score` becoming five different
dimensions over time by accident), and a CHECK constraint doesn't carry a
display name, a unit, or a description the way a real row can.

## Decision

`dimension` becomes a foreign key into `case_dimension_type` — a lookup
table (`id`, `code`, `display_name`, `unit`, `description`, `display_order`)
following the same pattern already adopted for `business_groups` this
session: a small, admin-manageable table instead of a hardcoded enum,
specifically so a new dimension is one `INSERT`, not a migration touching a
CHECK constraint.

**Scoped deliberately smaller than proposed.** The original proposal
included `aggregation_strategy` and `projection_handler` columns, implying a
pluggable handler-dispatch system. Not included here — there is exactly one
aggregation strategy in use today (numeric before/after with a text reason),
and building a dispatch mechanism for a second strategy that doesn't exist
yet is speculative complexity ahead of need. Add those columns when a
second, genuinely different dimension type actually requires one.

## Alternatives Considered

- **Keep the CHECK-constrained string.** Rejected — the drift risk is real,
  and the codebase already has a working precedent (`business_groups`) for
  solving exactly this with a lookup table instead.
- **Full entity with pluggable aggregation/projection handlers, as
  proposed.** Rejected for now — no second aggregation strategy exists to
  justify the abstraction. Revisit when one does.

## Consequences

- New dimensions (the design review's examples: settlement probability,
  MiCA exposure, jurisdiction complexity) are added via Admin Console,
  mirroring the Feature Registry / Business Groups pattern — zero frontend
  code changes to introduce one, consistent with the "one INSERT" principle
  already established for those two.
- `case_dimension_history.dimension` is now a real foreign key with
  referential integrity, not a string that happens to be constrained.
