# STRESS_TEST_REPORT — Operation Black Swan, Mission 001

Per the mission's own rule: "Ne procenjuj. Meri." (Don't estimate. Measure.) No live staging/Supabase/
OpenAI/GPU environment exists in this engagement — a standing, previously-disclosed constraint carried over
from every prior Lambda certification. Team 13's measurements below are ACTUALLY EXECUTED Python
measurements (real `time.perf_counter()`/`tracemalloc`, real `tiktoken` counts, real `tenacity` retry
timing) against real application code with mocked I/O counting — not estimates presented as measurements.

## Measured, not estimated

| Measurement | Method | Result |
|---|---|---|
| Dashboard SQL query count at N=10/100/1000 cases | Counting mock, real `predmeti_dashboard` | **O(1)** — 4 `.table()` calls always, properly batched via `.in_()` |
| Genome refresh token cost, realistic document sizes | Real `tiktoken` on realistic 6000-char excerpts | `_GENOME_MAX_DOCS=25` never actually binds — the char-budget cap saturates FIRST at 14 of 25 docs (56%); ~26,268 input tokens/refresh ≈$0.11/call (assumed GPT-4o rate, stated explicitly), fires on every upload, not per-case |
| `ai_cache`/health_index cache hit ratio, realistic hot/long-tail access | Real cache dict, 100 req/trial × 5 trials | 61-73% |
| `llm_retry`'s real backoff timing, 2 induced failures | Real `tenacity` decorator, real timing | 1.52-2.90s first delay, 2.33-4.00s second — jitter confirmed present and working as designed |
| Document chunker CPU/memory at 50KB/500KB/2MB | Real `time.perf_counter()`/`tracemalloc` | Roughly **linear** growth (5.8x CPU for 10x input, no quadratic blowup) |

**Verdict: nothing catastrophic measured.** The one number worth carrying forward: Genome refresh's real
per-upload token cost (~$0.11) is non-obvious from the 25-document cap alone, since the character budget is
the actual binding constraint at realistic document sizes — not a bug, but a cost-awareness item for
capacity planning (`DEBT` note, not a numbered debt item — informational).

## Concurrency stress — real reproduction, not measurement

These are pass/fail reproductions (does the failure mode occur), not throughput numbers, but are included
here because they're this mission's closest analog to genuine load testing without live infrastructure:

- **500 concurrent lawyers, healthy backend**: `_get_supa()`'s singleton race reproducibly created 50
  Supabase clients instead of 1 under a real 50-thread concurrent burst. **FIXED.**
- **500 concurrent lawyers + degraded OpenAI (combined stressor, Team 14)**: 415/500 (83%) failure rate
  purely from AI-semaphore queue-timeout — see `SYSTEM_SURVIVABILITY_REPORT.md`'s cross-subsystem section
  for full detail. This is the mission's closest approximation to a real load-test failure curve, and it
  shows a cliff, not a graceful degradation: below semaphore capacity, 0 failures in either baseline; past
  it, an 83% failure rate under combined load.
- **20 firms × 1000 documents**: simulated the real `claim_intake_job` selection query against 20,000
  synthetic rows across 4 workers — confirmed pure global FIFO with zero tenant fairness, firm #20's first
  document not claimed until 19,000 others drain.
- **5,000-event Event Bus backlog under sustained overload**: arrival above the 4-worker drain capacity
  (~16.7 events/sec) produces genuinely unbounded backlog growth (13,134 and still rising after 20 simulated
  minutes) — a real capacity-mismatch finding, not a retry-logic bug (retries are correctly capped).

## What this report does NOT claim

No real network latency, no real Postgres query planner behavior under load, no real OpenAI rate-limit
behavior, no real memory pressure under actual concurrent OS processes — all of the above are structural/
algorithmic measurements and controlled reproductions against mocked I/O, consistent with this program's
standing, repeatedly-disclosed limitation. A genuine load-testing environment (seed data generator + a
disposable Supabase project + k6/locust against the highest-traffic endpoints) remains a distinct, unstarted
future mission — named here explicitly rather than quietly assumed complete.
