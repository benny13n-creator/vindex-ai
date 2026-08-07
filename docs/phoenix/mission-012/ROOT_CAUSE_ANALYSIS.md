# Mission 012 — Root Cause Analysis

## Common root cause

All 4 fixed items share the same shape this whole engagement keeps finding: a check and its
corresponding write were separated in time (by a network round-trip, by an early return, by a
downstream function call) with no atomic mechanism spanning both — a window where a concurrent
actor (another request, another coroutine) can observe the same "not yet claimed" state and also
proceed.

## `-012` — cooldown TOCTOU

`_seconds_since_last_call` reads `feature_usage_log` (a pure audit table, append-only, no
uniqueness constraint suited to "claim" semantics), while the corresponding write
(`_increment_usage`) happens much later against a DIFFERENT table (`feature_usage`) that DOES
have a `UNIQUE(user_id, feature_key, dan)` constraint — but that constraint was never used for
the cooldown check itself, only for the daily-aggregate row. The fix reuses that already-present
constraint for the cooldown claim instead, closing the gap without needing new schema.

## `-021` — chronology bulk-insert atomicity

The bulk `.insert(rows)` call was written assuming Postgres treats the whole Python list as
independent rows — it doesn't; a single `INSERT ... VALUES (...), (...), (...)` statement is one
atomic operation, rejected in its entirety if any one row's value fails type coercion (e.g. an
invalid date). The code's own outer `try/except` (present for legitimate reasons — GPT can return
malformed JSON entirely) additionally swallowed this DB-level rejection with the same generic
handler, so a data-shape problem in ONE event silently cost the whole batch.

## `-045` — coalescing guard's return-timing gap

The coalescing guard's own docstring already stated its design goal precisely ("running it once
per predmet_id at a time and re-running once more if a new trigger arrived meanwhile") — the
mechanism for AVOIDING redundant work was correct. What was missing was a way for the CALLERS
who triggered that avoidance to know when the work they were counting on had actually finished.
`_consequence_genome_refresh`'s own before/after verification (built independently by the Zero-
Touch Case investigation team, unaware of the exact coalescing internals) assumed "my await
returned, so the work is done" — true for the FIRST caller, false for every coalesced one.

## `-046` — /run's missing claim

`/daily` and `/run` share the same underlying `cio_dnevni_izvestaj` row and the same charge
semantics, but `/run` was added later as "the force button" without inheriting `/daily`'s own
concurrency hardening (`LAMBDA008`-era work, added specifically to `/daily`). The 2 endpoints
drifted apart in robustness despite representing the same conceptual write target — exactly the
kind of gap Program Phoenix's "group by architecture, not debt number" instruction exists to
catch.

## Why these are safe, bounded fixes (not new algorithms)

- `-012` and `-046` both reuse an EXISTING unique constraint + the retry-on-conflict idiom
  already proven in `billing.py` (`LAMBDA008-CONC-003`) and `smart_intake.py` (Mission 011) — no
  new mechanism, no migration.
- `-021` reuses `_popuni_sablon`-style "fail safe, never fabricate" philosophy already applied
  elsewhere (e.g. Mission 010's critique pass) — validate, drop the bad piece, keep the good one.
- `-045` reuses `asyncio.Event`, the standard-library primitive for exactly this "wait for another
  coroutine's in-flight work" pattern — no custom synchronization logic invented.
