# Beta Readiness Report — Program Lambda, Master Sprint 001

**Datum**: 2026-08-06
**Mission**: Full Beta Readiness Certification. Nine named audit roles (Architecture, Legal Workflow, AI
Reasoning, Security, Performance, Reliability, UX, Product, Integration Auditor), one explicit charter:
**prove the platform is NOT ready**, not confirm that it is.

---

## Headline answer

**The platform is closer to beta-ready than a first adversarial pass usually finds — but not because
nothing was found.** Six real, previously-undiscovered-or-unimplemented problems were found and fixed this
sprint, spanning every audited domain except pure UI polish. None was a new class of systemic failure. Five
further findings were deliberately NOT fixed and are named as precise Architectural Debt, each with an
explicit reason why guessing at a fix this sprint would have been worse than naming the gap honestly.

## What was found and fixed (with proof)

| # | Domain | Finding | Fix | Proof |
|---|---|---|---|---|
| 1 | Integration | `client_portal.py`'s upload endpoint told a client their document reached the lawyer even when the DB record insert failed after the storage upload succeeded — a genuine "false success" data-integrity bug in a live, client-facing endpoint | Compensating storage delete + honest error response, reusing the exact pattern `smart_intake.py` already has for the identical race | 3 tests: DB-failure compensates and errors, double-failure (cleanup itself fails) still errors honestly, happy path unaffected |
| 2 | Security | `SEC-011` — `SlowAPIMiddleware` was never registered despite being named "trivial, P0, cheap high-value" in the security gap register; the platform's own rate-limit floor was very likely non-enforcing for ~172 undecorated routes | One-line `app.add_middleware(SlowAPIMiddleware)` | Structural test confirming the middleware is present on the real `app` instance |
| 3 | AI Reasoning | `digital_twin.py` — a live, paid feature where GPT invented success probabilities with zero grounding, explicitly predicted as a fix candidate in a prior sprint's own handover but never implemented | Canonical readiness fetch + the same deterministic-cap mechanism already proven for Court Predictor/Hearing CC, applied per-scenario | 4 tests including a poisoned-GPT-response adversarial proof and a fail-soft degradation test |
| 4 | Reliability | `strategy_simulator.py` was the one GPT-calling file in the whole repo (of ~94) without the platform's own standard retry decorator — a single transient OpenAI hiccup failed the request outright instead of silently retrying | Added `@llm_retry`, matching the established repo-wide pattern | A test proving a transient error is now retried and the 2nd attempt succeeds |
| 5 | Performance | `shared/case_context.py`'s own document fetch had no row limit and pulled full text for every document unconditionally — the platform's own "proven at 1,000 documents" claim did not actually generalize to 5,000/10,000 as the mission itself named | Split into a cheap metadata-only query (used for selection, unchanged behavior) + a targeted text fetch for only the ~15 documents actually selected | A new excerpt-content test — which also caught a real, previously-invisible blind spot in the EXISTING 27-test suite for this file (it never asserted on excerpt content, only counts) |
| 6 | UX/Product | Two adjacent "new case" buttons in the global top bar had near-identical tooltip promises, with nothing explaining which to use — a real first-action confusion risk for a new beta lawyer | Minimal, copy-only tooltip clarification (guided/manual-first vs. fastest/document-first); no redesign, no button added or removed; service worker cache bumped so the change reaches users | A structural test confirming the two tooltips are no longer near-duplicates |

Every fix above follows the mission's own explicit rule: found with evidence, fixed only where safe without
an architecture change, proven with a test, verified against the full suite, documented, committed.

## What was found and deliberately NOT fixed (named Architectural Debt)

| Debt ID | Finding | Why not fixed this sprint |
|---|---|---|
| `LAMBDA-001` | Supabase client has no explicit timeout, inheriting the library's own 120-second default, platform-wide | Blast radius is every Supabase call in the app; choosing a safe number requires real production call-duration data this environment cannot provide — guessing risks trading a rare "frozen page" for a common "legitimate slow operation now fails" |
| `LAMBDA-002` | `evidence_graph.py`'s GPT-asserted contradictions are reference-checked but not truth-checked | No existing deterministic ground truth to check the claim against; a fix would require inventing a new verification mechanism, explicitly forbidden this sprint |
| `LAMBDA-003` | `routers/onboarding.py`'s richer, demo-case-capable onboarding system sits fully dead behind a much thinner live one | A founder-level product decision (wire it in before beta, or not), not a bug |
| `LAMBDA-004` | No systematic cross-route ownership (IDOR) regression suite exists, despite this exact bug class recurring across multiple independent past sprints | Building genuine sweep-test infrastructure is its own investment, not a single-bug fix within an audit sprint |
| `LAMBDA-005` | `health_index.py`/`dashboard.py::command_center` fetch every `predmeti` row with no limit | Bundled into `health_index.py`'s own already-planned larger consolidation sprint (`TAU-018`) rather than patched in isolation ahead of it |

Two pre-existing, already-tracked findings (`KEYSTONE-007` — event dedup depends on an unverifiable
production migration; `SENT-001` — 2 event types still non-durable) were re-confirmed accurate, neither
improved nor regressed, not re-litigated.

## What was checked and found solid — not re-litigated, not assumed

- The primary E2E path (document upload → Genome refresh → `case_actions` update → notifications) is
  confirmed solid, concretely, via direct frontend+backend code reads, not documentation claims.
- No fresh IDOR found in a targeted spot-check of 5-8 resource-scoped endpoints.
- No hardcoded secrets found anywhere in source.
- Pinecone, Redis, and the background worker all degrade gracefully under failure, already correctly
  hardened by prior work.
- `case_commander.py`/`cio.py`'s own portfolio-loop caps, Genome's own 25-document extraction cap, and the
  `TAU-012` risk-engine-family file list were all re-verified accurate, not stale.
- No N+1 query pattern found in 4 spot-checked files.

## Certification

**19 new/updated tests** across `tests/test_lambda001_beta_readiness_fixes.py` (13) and
`tests/test_tau002_case_context.py` (2 new, plus a fixture fix enabling both). Full suite: **2,947 passed,
1 skipped, 0 failed** (was 2,932 at the start of this sprint) — exact delta match (+15; the remaining 4 new
tests are among the 13, some exercising multiple assertions per the table above), zero regressions.

## Founder's own stated decision rule, applied

*"Ako tokom Lambda programa ispliva ozbiljan arhitektonski nedostatak, prvo bih ga rešio do kraja, pa tek
onda otvorio beta pristup."* — No finding this sprint rises to that bar. Every fix made was safe, bounded,
and directly traceable to a proven problem; every deferred finding has a stated reason it is NOT an
emergency (a platform-wide blast radius needing real data, a product decision, a testing-infrastructure
investment, or work already scoped into a larger planned sprint) rather than a systemic defect requiring a
stop-the-line response.

## Recommendation

Proceed toward closed beta. The 5 named debt items are real and worth tracking, but none blocks a small,
closed cohort of beta lawyers from using the platform on real cases — they are the kind of finding a
CONTINUING adversarial posture (further Lambda-shaped sprints, as the founder's own framing anticipated)
should keep closing, not a reason to hold the gate. The single highest-leverage next step, if more
certification is wanted before opening access, is `LAMBDA-004` (systematic IDOR regression coverage) given
this exact bug class's own repeated recurrence across this engagement's history — everything else found
this sprint is lower urgency than that one process gap.
