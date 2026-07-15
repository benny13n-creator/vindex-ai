# ADR-0013: Case Evolution reads `case_dimension_history` directly

- Status: Accepted
- Date: 2026-07-15

## Context

Case Evolution — a trend view per dimension (Health 41 → 62 → 79 → 91 over
six weeks) — needs a time series to render. The obvious-seeming path is a
purpose-built analytics/reporting table, aggregated and optimized for
charting, fed by the same events.

## Decision

No separate analytics table. Case Evolution queries `case_dimension_history`
(ADR-0009's Knowledge State event log) directly — it's already the correct
shape (predmet_id, dimension, value, timestamp) for a time-series chart,
because it was designed as an event log in the first place, not
after-the-fact repurposed into one.

## Alternatives Considered

- **Dedicated `case_evolution_snapshots` table, pre-aggregated.** Rejected
  — at Vindex's per-case data volume (dozens to low hundreds of dimension
  changes per case over its lifetime, not millions), a direct query against
  the event log is not a performance problem, and a second table would be a
  second thing to keep in sync with the first.

## Consequences

- Case Evolution is close to free once ADR-0009/0010 are implemented — it's
  a UI reading existing history, not a new backend subsystem.
- If per-case dimension-change volume ever grows enough that direct queries
  become slow (unlikely at current scale), a materialized view or
  read-replica projection is the natural next step — deferred until that's
  an observed problem, not a hypothetical one.
- Must handle the sparse case explicitly: a new case with one document has
  one data point, not a trend. The UI needs an honest "not enough history
  yet" state rather than rendering a misleading flat line or an unexplained
  empty chart.
