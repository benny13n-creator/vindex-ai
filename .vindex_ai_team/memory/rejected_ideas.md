# Rejected Ideas — Institutional Record

The point of this file: prevent this organization from re-proposing something already considered
and rejected for a stated reason, and prevent a future reviewer from re-litigating a settled
question without a genuinely new argument.

## Rejected: renaming "Program 1" to "AI Trust Kernel"
**Proposed:** 2026-08-02, founder review of Program 1 Revision 4-6 — the name undersells what the
AI Governance Layer might become if it eventually routes every AI capability in the product.
**Rejected (for now), reasoning preserved:** "Trust Layer" and "Core Consolidation" both earned
their names in this project through *shipped, verified* work, not at Stage 4 with zero lines of
code written. Renaming now would be exactly the kind of claim-ahead-of-evidence the Blueprint's own
Principle 10 exists to prevent.
**Trigger to revisit:** when a second capability (not just Program 1 itself) is actually routing
through the Decision Engine in production — Stage 8/9 territory, not Stage 4.

## Rejected: thread-safe event-loop bridge for the sync/async chokepoint gap (Program 1, Red Team Item 2)
**Proposed:** as the obvious fix once the sync/async gap was found — `asyncio.run_coroutine_threadsafe`.
**Rejected, reasoning preserved:** real deadlock exposure (waits on a possibly-busy loop from a
worker thread), manual cross-thread timeout handling, fails outright with no event loop present.
**Chosen instead:** exposing the sync/async service-pair split this codebase already uses
(`log_action`/`log_action_sync`) across every Governance service — simpler, already-proven,
zero new failure mode.
**Generalizable lesson:** when a "simpler alternative" is proposed to a genuinely proven fix, check
whether an even simpler option already exists in the codebase before adopting the proposed one.

## Rejected: health-check or local-durable-spool for the "is Audit available" question (Program 1, Red Team Item 2, first attempt)
**Proposed:** either check Audit's availability before proceeding, or write locally if the primary
DB is down.
**Rejected, reasoning preserved:** a health check can pass and the very next insert can still fail
(check-then-act race); a local spool proves increased probability of persistence, not durable
persistence (the machine holding it can still fail before syncing).
**Chosen instead:** replace "is Audit available" with "did this specific write receive a durable
acknowledgment" — await the real write, check its actual return value.
**Generalizable lesson:** "is X available" and "did this specific operation succeed" are different
questions; a control gating on the wrong one looks like an availability check but is actually a
race condition.

## Rejected: option (b), an internal `LLMProvider` abstraction, for making "any LLM is a provider" true
**Proposed:** to genuinely decouple every AI call site from `openai.*` directly.
**Rejected (for now), reasoning preserved:** requires touching every one of the ~130+ existing call
sites — the exact opposite of what made the SEC-003 chokepoint monkeypatch safe to ship
(zero-call-site-change guarantee).
**Chosen instead:** per-vendor chokepoint replication (patch each new provider's SDK the same way).
**Trigger to revisit:** when a second real provider is actually being integrated and N
vendor-specific chokepoints becomes genuinely unwieldy — a concrete trigger, not decided
speculatively now.

## Template for new entries
```
## Rejected: [idea]
**Proposed:** [date, context]
**Rejected, reasoning preserved:** [why]
**Chosen instead (if applicable):** [what]
**Trigger to revisit (if applicable):** [concrete condition, not "later"]
```
