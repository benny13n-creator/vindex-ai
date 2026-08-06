# Reliability Audit — Program Lambda, Master Sprint 001

Code-level failure-mode review for OpenAI/Pinecone/Supabase/Redis/Worker/process-restart — no live
deployment access, so every claim is a direct code read, not a live chaos test, flagged as such throughout.

## Findings

| # | Dependency | Behavior | Status | Severity |
|---|---|---|---|---|
| 1 | OpenAI, `routers/strategy_simulator.py` | The one GPT-calling file in the whole repo (93 others checked) with no `@llm_retry` — a transient hiccup every other AI endpoint silently absorbs failed this one outright | **FIXED this sprint** — added the decorator, proven via a transient-error-then-success test | Medium → Closed |
| 2 | Pinecone, `app/services/retrieve.py` | Graceful degradation — try/except, Sentry capture, `security_events` telemetry, returns `[]` on failure | Confirmed already correct | — |
| 3 | Supabase, all endpoints | No explicit client timeout — inherits the library's own 120-second default, unexamined, platform-wide | Named as `LAMBDA-001`, not fixed (no production traffic data to safely choose a replacement value) | Medium-High |
| 4 | Redis, `shared/rate.py` | Fail-open, already proven (`SEC-005`, `tests/test_sec005_failopen_limiter.py`) | Re-confirmed present, not re-audited | — |
| 5 | Background worker, `shared/intake_worker.py` | Mature — idempotent retry, dead-lettering, a periodic stale-job reaper for jobs orphaned by a dead worker process | Confirmed already correct | — |
| 6 | Process restart / module-level state | `shared/case_context.py`'s own no-cache determinism guarantee spot-checked elsewhere — zero `_cache = {}` module-level pattern found in a targeted grep | Spot-checked, not exhaustive | — |

## Verdict

One real, live, cheap-to-fix reliability gap was found and closed this sprint (#1). One genuinely
consequential, platform-wide gap (#3) was found and deliberately NOT fixed — guessing a timeout value
without real traffic data risks trading a rare "frozen page" failure mode for a more common "legitimate
slow operation now fails" one, the same category of risk this program has repeatedly refused to guess at
elsewhere (e.g. the SEC-003 prompt-guard threshold). Every other dependency checked was already
appropriately hardened by prior work — not re-litigated, re-confirmed.
