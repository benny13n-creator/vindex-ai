# Lambda 004 Handover — Next Recommended Actions

## Immediate, no action needed from the founder

Unlike Certification 002/003, this sprint required **zero new migrations** — every fix reused an existing
column, constraint, or precedent already present in the schema (`predmeti.updated_at`'s existing trigger,
`case_evolution_consequences`'s existing `UNIQUE(event_id, consequence_name)` constraint,
`reap_stale_jobs`'s existing 300s threshold). Nothing is waiting on the founder to run SQL.

## Named architectural debt, ranked by leverage

1. **Zero explicit OpenAI timeout across ~63 call sites** (highest leverage). Current worst case: an SDK
   default of ~10 minutes per attempt, compounding under the SDK's own internal 2 retries sitting beneath
   `llm_retry`'s own 3 application-level attempts — a materially longer and less predictable tail latency
   than the retry decorator's own docstring implies. Recommended next step: instrument (not guess) — add
   latency logging/metrics around the highest-traffic call sites for a short period, then set timeouts from
   real p99 data, likely via a small number of tiers (fast classification calls vs. large synthesis calls)
   rather than one blanket value. This is the single most likely "found nothing until it's in production
   under load" gap this whole certification surfaced.

2. **`notifications` polling system (`_generate_notifications`) lacks `proactive_alerts`'s own durability
   guarantees.** Two parallel notification systems exist with different reliability guarantees — this is
   itself worth a product decision: should `_generate_notifications` be retrofitted with the same
   retry+durable-failure-audit pattern `create_proactive_alert` already has, or should the two systems be
   consolidated onto one path? Consolidation is a larger, "no redesign this sprint" question — recommend a
   dedicated sprint if this is judged worth prioritizing, given no confirmed production incident from this
   gap yet, only a structural asymmetry found by this sprint's own audit.

3. **`content_sha256` document dedup is application-level only** (a SELECT-then-INSERT check, not a DB
   constraint). Narrow, unconfirmed exploitable (requires identical document content + genuinely concurrent
   finalize timing for the same user). If ever worth closing fully: a real `UNIQUE` index on
   `(user_id, content_sha256)` scoped appropriately, following the same precedent already proven for
   `timer_sessions`'s own partial unique index.

4. **Event Bus dead-letter has no active alerting.** The mechanism is durable and provable (queryable,
   logged at CRITICAL) but nothing pages a human. This is a genuinely NEW capability (an integration with
   whatever paging/alerting tool the team uses), correctly out of THIS sprint's "no new capabilities"
   charter — recommend scoping it explicitly as its own small, well-bounded feature request when ready, not
   folding it into a future certification sprint's own reactive-fix budget.

5. **Genome background refresh doesn't coalesce across gunicorn worker processes** (only within one process).
   Self-documented, pre-existing, no confirmed incident. Worth revisiting only if/when the platform's own
   worker-process count or Genome-refresh trigger frequency changes enough to make the cross-process race
   window practically relevant — not urgent today.

## What this sprint deliberately did NOT touch

Per the mission's own explicit charter ("no speculative engineering... no redesign... no architecture
replacement"): no new abstractions were introduced, no existing architecture was replaced, and every fix
reused an already-proven pattern from elsewhere in this codebase (the atomic-claim RPC pattern, the
`return_exceptions=True` gather pattern, the opt-in-optimistic-concurrency pattern, the recent-duplicate-check
pattern) rather than inventing something new. This is intentional and should be the template for how future
certification sprints in this program continue to operate.

## Process note for future sprints

This is the **third** consecutive sprint (following Certification 002's addendum and Certification 003A)
where an adversarial second pass — either a dedicated fork or the coordinator's own regression tests — caught
a real flaw in a first implementation attempt before it shipped. In this sprint specifically, 2 of the 7
fixes were self-corrected by the coordinator's own tests during implementation (before Phase 6 even ran), and
Phase 6 itself caught a 3rd. The pattern is holding up as a genuinely load-bearing practice, not a one-off:
**write the adversarial test before trusting the fix, and if a dedicated forensic-review fork is available,
use it even after your own tests pass — it found something your own tests didn't for `update_predmet`'s own
404-vs-409 conflation.**
