# ADR-0009: Event sourcing applies to Knowledge State, not Configuration State

- Status: Accepted
- Date: 2026-07-15

## Context

An early proposal for this subsystem was a platform-wide principle: "no
module owns truth, the only source of truth is events." Taken literally,
that implies Feature Registry, Tier Config, Business Groups, and the
Permission Matrix — all built this session, all working correctly as
directly-editable rows with an append-only audit log — should eventually be
rewritten as projections replayed from an event log. That's a real,
multi-year architectural commitment (snapshotting, replay performance for
old history, eventual-consistency UX) this design review never scoped and
had no basis to justify.

## Decision

Vindex data splits into two kinds, and only one of them is event-sourced:

- **Configuration State** — Feature Registry, Tier Config, Subscription
  Plan, Pricing, Business Groups, Permission Matrix. These are
  human-authored settings, not consequences of events. They stay as
  directly-updatable rows (`UPDATE feature_registry SET ...`) with an
  append-only audit log — the pattern already proven this session.
- **Knowledge State** — Case Health, Risk, Confidence, Evidence Strength,
  Strategy, Completeness, Client Twin. These are *already* computed/derived
  values, recalculated on trigger rather than directly edited. They are
  event-sourced: the only source of truth is the append-only
  `case_dimension_history` log (ADR-0010); any current-value column is a
  rebuilt projection, not the truth itself.

## Alternatives Considered

- **Events as the sole source of truth, platform-wide.** Rejected — see
  Context. Would discard a pattern already working for configuration data,
  for no benefit that data actually needs.
- **No event sourcing anywhere; keep everything as mutable rows.** Rejected
  for Knowledge State specifically — it discards exactly what makes Case
  Evolution (ADR-0013) and the State Diff Engine (ADR-0012) possible at low
  cost. Case Health going from 61 to 91 over six weeks is only visible as a
  trend if the intermediate values were ever recorded.

## Consequences

- A new module's data model is a design decision, not a blanket policy
  lookup: is this a human-authored setting (Configuration State) or a
  computed/derived signal that benefits from trend visibility and
  point-in-time replay (Knowledge State)? That test, not a rule applied in
  advance, decides which pattern it gets.
- This ADR is the one place in the design review where a proposed platform
  principle was narrowed rather than adopted as stated, and it's recorded
  here specifically so that narrowing is visible and intentional, not a
  silent downgrade.
