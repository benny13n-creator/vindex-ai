# Security Audit — Program Lambda, Master Sprint 001

Adversarial re-verification of the current security posture against `docs/security/SECURITY_GAP_REGISTER.md`'s
own claims — spot-checked, not trusted. Read-only investigation, findings triaged after.

## Findings

| # | Finding | Status | Severity |
|---|---|---|---|
| 1 | `SEC-011` — `SlowAPIMiddleware` was never registered despite being flagged "trivial, P0, cheap high-value" in the gap register; `default_limits=["60/hour"]` was very likely non-enforcing for any route without an explicit `@limiter.limit()` decorator (SEC-010 found ~172 such routes) | **FIXED this sprint** — one-line `app.add_middleware(SlowAPIMiddleware)`, proven present on the real `app` instance | Medium-High → Closed |
| 2 | 5-8 spot-checked `predmet_id`/`klijent_id`/`dokument_id`-scoped endpoints (including the recently-Tau-modified `hearing_cc.py`) | No fresh IDOR found — ownership checks correctly gate sub-table access | — |
| 3 | `SEC-004`'s own recommendation for a systematic cross-route ownership regression suite | Confirmed never built — only 3 incident-scoped ownership test files exist | Named as `LAMBDA-004`, not fixed (testing-infrastructure investment, not a single bug) |
| 4 | Hardcoded secrets (`sk-`/`AIzaSy`/`xox` patterns) in source | None found — confirms the 2026-08-02 exposed-key finding is genuinely fixed | — |
| 5 | `SEC-005` (fail-open rate limiter), `SEC-036` (XSS sweep), `TAU-015` (prompt-guard threshold) | Read as still accurately described in the register, not independently re-tested against live traffic this pass (time-boxed) | — |

## Verdict

One real, live gap between a documented "cheap, P0" fix and its actual implementation was found and closed
this sprint (#1) — a reminder that a debt-register entry describing a fix as "trivial" does not mean it
self-executes. No fresh IDOR instance found in this pass's own spot-check, though the ABSENCE of systematic
regression coverage (#3) means this remains an open question for the NEXT file someone doesn't think to
check, not a closed one.
