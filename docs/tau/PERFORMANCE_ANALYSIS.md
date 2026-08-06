# Performance Analysis — Program Tau, Master Sprint 008, Phase 7

Measures, not guesses, the SQL query / GPT token / cost / latency impact of migrating `routers/cio.py` onto
`build_case_context()`.

## GPT tokens — measured via real `tiktoken` encoding, essentially flat

Built a representative 10-case portfolio, ran it through both the pre-migration `_kompaktan_predmet`
(loaded standalone via `git show HEAD`) and the post-migration version, and encoded the resulting compact-
portfolio JSON with `tiktoken.encoding_for_model("gpt-4o")`:

| | Before | After |
|---|---|---|
| Compact-portfolio JSON tokens (10 cases) | 1,932 | 1,892 |
| **Delta** | | **-40 tokens (-2.1%)** |

The decrease comes from dropping `genome_verzija` (never part of GPT's own required output schema — pure
extra context, its absence changes nothing observable). Every other field's own truncation budget
(`[:80]`, `[:70]`, `[:100]`, etc.) is unchanged, so per-case size is effectively identical — token cost is
flat, not meaningfully reduced or increased. `max_tokens=2500` (the JSON response cap) is unchanged, so
output cost is unaffected. **Cost delta: ≈$0**, not estimated — the actual prompt text was measured.

## Database queries — a real, substantial increase, named plainly

| | Before | After |
|---|---|---|
| Base queries (`predmeti`, `firm_dna`, `lessons_learned`, `case_patterns`) | 4, constant | 4, constant |
| Per-case canonical fetch | 0 | 6 queries × N cases with a working Genome model (N ≤ 40, the pre-existing `predmeti` fetch cap, unchanged) |
| **Total, worst case (N=40)** | **4** | **4 + 240 = 244** |

**This is a real cost increase in a LIVE feature — named honestly, not minimized.** Unlike
`case_commander.py`'s own portfolio digest (Tau 007, confirmed dead in the live frontend), `cio.py` IS live
(`_cioLoad()` wired into `dash_load()`, confirmed by direct `grep` on `static/vindex.js`), so this query
increase has real, present-day cost — not a hypothetical ceiling for a future reconnection.

**Mitigating factors, all pre-existing and unchanged by this migration**: `GET /api/cio/daily` caches its
own result for 6 hours per user (`cio_dnevni_izvestaj` table, checked before any regeneration); `POST
/api/cio/run` (force-regenerate) is rate-limited to 10/minute. The 244-query cost is paid at most a
handful of times per user per day, not per page load — the SAME cache/rate-limit shape that already bounded
the OLD 4-query cost, now bounding the NEW 244-query cost identically. No new caching or rate-limiting was
added or needed; the existing mechanism already covers the new cost shape.

**Why the increase is justified, not just accepted**: the old 4-query approach could never have closed
`docs/tau/CIO_FORENSIC_REPORT.md`'s own findings (a 3rd, GPT-extracted deadline source disconnected from
`rocista`; raw Genome contradiction/gap counts bypassing `gap_engine.py`'s own normalization; a
`kriticnih_rizika` definition disagreeing with every other executive surface's own definition of
"critical") without per-case canonical computation — the same structural reasoning `case_commander.py`'s
own portfolio digest migration (Tau 007) already established for the identical tradeoff shape.

## CPU / memory

No new CPU-bound computation of comparable weight to the query increase — `_kompaktan_predmet`'s own logic
is the same shape of dict extraction/filtering as before, just reading from a different (canonical) source
dict. Memory: `build_case_context()`'s own lightweight-mode output per case (no document excerpts) is
small; holding up to 40 of them concurrently during the `asyncio.gather` is bounded and comparable in class
to what `case_commander.py`'s own portfolio digest (Tau 007) already holds for up to 20 cases.

## Latency

Not independently measured (no live DB access from this environment) — flagged as an assumption, consistent
with every prior Tau sprint's own disclosure. Structurally: all N `build_case_context()` calls run
concurrently (`asyncio.gather`), not sequentially, and each one's own internal 6-query fetch is itself a
parallel gather — so wall-clock addition is bounded by the slowest single case's own fetch, not the sum of
all 40. Given the 6-hour cache and 10/minute rate limit, the actual latency users experience during
generation (not the cached fast path) is not the platform's own primary UX concern for this endpoint the way
a synchronous request-path endpoint's latency would be.

## A real latency bug found and fixed during this same phase

The initial Phase 3 implementation bundled `predmeti`/`firm_dna`/`lessons_learned`/`case_patterns` into one
`asyncio.gather`, then started the canonical `build_case_context()` loop only after ALL 4 completed — even
though 3 of those 4 (`firm_dna`/`lessons_learned`/`case_patterns`) have no dependency on the canonical loop
at all. Found while writing this same performance report, fixed immediately (Phase 8): `predmeti` is now
awaited alone (the canonical loop's own real dependency), then the 3 unrelated queries run CONCURRENTLY with
the canonical loop via 2 parallel `asyncio.gather` calls, not sequentially before it. Implemented as 2
separate gathers (not 1 combined one) specifically so `firm_dna`/`lessons_learned`/`case_patterns` keep
their own original error-propagation behavior (an exception there still raises, as before) while the
canonical loop keeps its own fail-soft-per-case behavior (`return_exceptions=True`) — combining them into
one gather would have silently changed the first 3 queries' own failure behavior too, a regression avoided
during design, not caught after the fact by a test.

## Optimization considered and rejected

Limiting the canonical loop to fewer than the existing 40-case `predmeti` cap (e.g., only the 10 most
recently updated) was considered and rejected — it would change observable behavior (which cases the CIO
report can name), and Phase 7's own explicit instruction is "predloži optimizacije samo ako ne menjaju
ponašanje" (propose optimizations ONLY if they don't change behavior). No optimization was found that
reduces the query count without also reducing which cases get real, grounded signals — the tradeoff is
inherent to closing the correctness gap this sprint's own migration exists to close, not something to
optimize away in the same sprint.

## Verdict

Token/GPT cost: flat, measured not estimated. Query cost: a real, substantial, honestly-reported increase
in a live feature, fully absorbed by pre-existing cache/rate-limit infrastructure that required no changes,
and justified by closing 3 concrete correctness gaps a cheaper approach could not have closed.
