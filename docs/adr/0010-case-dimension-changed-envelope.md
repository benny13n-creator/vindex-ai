# ADR-0010: One generic `CaseDimensionChanged` event, not one event type per dimension

- Status: Accepted
- Date: 2026-07-15

## Context

Under ADR-0009, every Knowledge State recalculation (Health Index, Risk,
Strategy, Evidence Strength, Confidence, Completeness, Profitability) needs
to publish its result as an event. The naive design is one bespoke event
type per dimension — `HealthChanged`, `RiskChanged`, `StrategyChanged`,
and so on, each with its own payload shape.

## Decision

A single generic envelope, `CaseDimensionChanged`, carries `predmet_id`,
`dimension` (an identifier — see ADR-0011), `previous_value`, `new_value`,
`reason`, `source_document_id` (nullable), `triggered_by`, `at`. Every
recalculating module publishes this same shape.

## Alternatives Considered

- **One bespoke event type per dimension.** Rejected — a new dimension
  (the design review's examples: settlement probability, negotiation
  readiness, jurisdiction complexity) would require a new event type, new
  handler registration, and updates everywhere the event enum is consumed.
  With a generic envelope, a new dimension needs a new `case_dimension_type`
  row (ADR-0011) and one subscriber — no new event type at all.
- **A single `CaseStateChanged` event carrying all dimensions at once,
  fired after every module in the fan-out finishes.** Rejected — requires
  a distributed join/barrier waiting on N independently-async workers to
  all complete, which is fragile (what's the timeout? what if one module's
  recalculation genuinely takes longer?). A per-dimension event with a
  debounced *reader* (ADR-0012) gets the same "what changed" narrative
  without that synchronization hazard.

## Consequences

- `case_dimension_history` (the event log) has one row shape to reason
  about regardless of how many dimensions Vindex eventually tracks.
- Any consumer of these events (State Diff Engine, Case Evolution, future
  analytics) depends on one stable envelope shape — which raises the cost
  of ever changing that shape, since every dimension-producing module and
  every downstream reader depends on it. Schema stability on this event is
  a cross-cutting concern from day one, not a detail to defer.
