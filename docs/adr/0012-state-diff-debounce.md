# ADR-0012: State Diff Engine composes on a debounce window, not per event

- Status: Accepted
- Date: 2026-07-15

## Context

A single `DocumentIngested` event fans out to multiple independently-async
modules (Health Index, Risk, Strategy, Evidence Strength...), each of which
eventually publishes its own `CaseDimensionChanged` (ADR-0010) on its own
schedule. Composing a "what changed" narrative immediately after the first
one arrives produces a fragmented, misleadingly-incomplete summary — e.g.
announcing a health change while the strategy recalculation is still
in flight.

## Decision

The State Diff Engine composes its narrative after a debounce window with
no new `CaseDimensionChanged` row for a given `predmet_id` — a short wait
(on the order of 30–60 seconds), not a fixed per-event trigger. It reuses
the existing document-analysis LLM summary pattern, pointed at recent
`case_dimension_history` rows instead of document text.

## Alternatives Considered

- **Compose immediately on every `CaseDimensionChanged`.** Rejected — see
  Context; produces noisy, incomplete diffs.
- **Wait for an explicit "cascade complete" signal from the fan-out.**
  Rejected — requires every subscribing module to participate in a
  synchronization protocol (effectively the same distributed-barrier
  problem ADR-0010 already rejected for the event shape itself). A
  debounce window gets equivalent behavior without coordination.

## Consequences

- The debounce duration is an explicit, unresolved tuning parameter, not a
  constant to hardcode and forget. It needs to be observable in production
  (how often does a diff fire before a stray late dimension update arrives
  anyway?) and adjustable without a deploy.
- A genuinely slow-to-recalculate module (unlikely, but not impossible)
  could still land just outside the window and be excluded from a diff —
  acceptable, since the underlying `case_dimension_history` row still
  exists and shows up in Case Evolution (ADR-0013) regardless.
