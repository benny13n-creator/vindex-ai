# Canonical Consequence Engine Specification — Program Delta, Sprint 001 (2026-08-05)

## What this is

`services/case_evolution.py` — the ONE mechanism in Vindex AI that decides and executes what automatically
follows a case-changing event. Built entirely on top of the already-existing, already-durable, already-atomic
Event Bus (`services/event_bus.py`) — this specification defines the ONE new layer added on top of it, not a
replacement for it.

## The contract

### `ConsequenceDef`

```python
@dataclass(frozen=True)
class ConsequenceDef:
    name: str
    executor: Callable[[Event], Awaitable[Optional[str]]]
```

An executor takes the triggering `Event` and returns an opaque `result_ref` string — a VERIFIED reference to
what the consequence actually produced (a Genome version number, a Timeline row id), never the wrapped
function's own self-reported "it worked." An executor that cannot verify its own effect must re-derive proof
independently (see `_consequence_genome_refresh`'s own re-read-before-and-after pattern) or raise.

### `CONSEQUENCE_REGISTRY: dict[EventType, list[ConsequenceDef]]`

One entry per event type with real, wired consequences. An event type with no entry (or an empty list) has
consequences that are either not yet needed (documented in `CASE_EVOLUTION_REGISTRY.md`) or not yet migrated
from an existing direct call site (also documented there) — never silently invented.

### `handle_case_changed(event: Event) -> None`

The one dispatcher. Registered as the Event Bus handler for every event type with a populated registry entry.
Implements exactly the 6-stage flow the mission's own charter names:

1. **Case Changed** — the `event` argument itself, already durably logged by the caller before this function
   ever runs (this function does not decide whether an event happened, only what follows one that already
   did).
2. **Determine Consequences** — `CONSEQUENCE_REGISTRY.get(event.type, [])`.
3. **Execute** — for each consequence not already `completed` for this exact `event.event_id`, run its
   executor.
4. **Verify** — the executor's own return value IS the verification (see `ConsequenceDef`'s contract above) —
   this function trusts a returned `result_ref` and treats a raised exception as failure; it never assumes
   "no exception" from a call INSIDE the executor is itself sufficient proof (that discipline lives inside
   each executor, most concretely in `_consequence_genome_refresh`).
5. **Audit** — `log_action("case_evolution_consequence_completed", ...)`, carrying `event.correlation_id`,
   after each consequence completes.
6. **Complete** — implicit: once every consequence in the registry list has been iterated without an
   unhandled exception, the function returns and the case is left in a fully consistent state.

## The idempotency mechanism (migration 096)

`case_evolution_consequences(event_id, consequence_name, status, result_ref, error, ...)`, `UNIQUE(event_id,
consequence_name)`. Keyed off the DURABLE outbox row's own id (`events.id`, propagated into `Event.event_id`
by `dispatch_pending_events`), never `correlation_id` — correlation_id is designed to span multiple distinct
operations sharing one logical request/job (Mission Ledger, 2026-08-03), so it is NOT a safe per-event
idempotency key; `event_id` is 1:1 with exactly one durable event row, by construction.

A consequence already marked `completed` is skipped unconditionally on any subsequent invocation of
`handle_case_changed` for the same event — whether that invocation is a genuine crash-retry (Event Bus's own
`dispatch_pending_events` re-processing an errored row) or an accidental replay (the same event dispatched
twice for any other reason). This single check is what makes Scenarios 2, 3, and 5 (crash-after-Genome,
crash-after-Timeline, replay) all true by construction.

## Why no new retry/dead-letter machinery was built

The Event Bus's own `dispatch_pending_events()` already has a proven, tested atomic claim
(`claim_pending_events`, migration 091), bounded retry (`MAX_DISPATCH_ATTEMPTS=5`), and dead-letter marking.
`handle_case_changed` deliberately re-raises a failed consequence's exception rather than swallowing it,
specifically so that EXISTING mechanism handles the retry — Program Delta's own contribution is making the
retry safe (no duplicate execution), not building a second retry system alongside the first.

## Concurrency

Two DIFFERENT events (different `event_id`) for the same `predmet_id`, dispatched concurrently, do not
corrupt each other's state — each event's consequence rows are keyed by its own `event_id`, fully independent
(proven by `tests/test_case_evolution.py::test_scenario4_two_parallel_events_no_cross_contamination`). Two
attempts to process the SAME event concurrently are already prevented one layer down, by
`claim_pending_events`'s own `SELECT ... FOR UPDATE SKIP LOCKED` (migration 091, unchanged) — only one dispatch
worker can ever hold a given event row's claim at a time, so `handle_case_changed` is never invoked twice
concurrently for the identical event by the Event Bus's own dispatch loop.

## What this specification deliberately does NOT cover

Rollback. No consequence in this sprint's registry needs one — each is independently idempotent and safe to
leave partially applied (see `CASE_EVOLUTION_REGISTRY.md`'s own "Rollback ponašanje" field for
`DOCUMENT_ACCEPTED`). A future event whose consequences are NOT safely independent (e.g. two consequences that
must both succeed or neither should appear to) would need a genuinely new mechanism — not built here, because
no such case exists yet in this platform.
