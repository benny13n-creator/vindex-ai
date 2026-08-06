# Lambda 003 Certification — "Forensic Authorization & Isolation Certification"

**Status**: BETA GATE. **Date**: 2026-08-06.

## Mission, verbatim intent

8 named agents, one explicit rule: proof before correction, every claim needs a file/function/line, an attack
scenario, and reproduction evidence — no hedging ("mislim"/"verovatno"/"deluje"/"moglo bi"/"najverovatnije").
A dedicated 8th agent's only job was to try to refute every other agent's findings; a finding not surviving
that attempt doesn't count as proven.

## Headline result

**7 real findings, all independently survived adversarial falsification (7/7 CONFIRMED, 0 refuted, 2
strengthened beyond their original framing).** The most severe — a response-cache bug letting one firm's
private content reach a completely unrelated firm with **zero guessed identifiers required** — is the single
worst finding of this entire multi-week, multi-sprint engagement, worse than any prior RPC or IDOR bug because
every one of those required the attacker to know or guess a specific victim resource id.

## What was found and FIXED, with proof

| # | Finding | Fix | Proof |
|---|---|---|---|
| 1 | **CRITICAL** — `main.py::ask_agent`'s response cache had a tenant-blind key and a read/write gate that never checked `memory_context`, letting one firm's privately-influenced answer be cached and served verbatim to an unrelated firm | All 4 gates now require `not history and not extra_namespaces and not memory_context` together | `tests/test_lambda003_ask_agent_cache_isolation.py` (8 tests) |
| 2 | `klijenti/router.py::_get_role` fail-open — a DB exception granted `Role.ADVOKAT`, same as the intentional new-user default, passing `access_confidential` | Exception path now fails closed to `Role.SEKRETARICA`; the genuine no-row-yet case is unchanged | `tests/test_lambda003_klijenti_role_fail_closed.py` (5 tests) |
| 3 | `shared/case_context.py::get_document_full_text()` — the Document Visibility Engine's own documented scale safety-net accepted `uid` but never used it | Added `.eq("user_id", uid)` | `tests/test_tau002_case_context.py::test_get_document_full_text_rejects_foreign_owner` |
| 4 | Concurrent unscoped sibling fetch before ownership check, in `case_commander.py`/`digital_twin.py`/`copilot.py` (×2 handlers) — safe today, "one bad refactor away" | Ownership query hoisted out of `asyncio.gather()` in all 3 files, with exception-handling preserved per file's own original shape | `tests/test_lambda003_hoisted_ownership_checks.py` (6 tests) |

Every fix follows this engagement's own established discipline: minimal, targeted, no architecture change, no
refactor beyond what the specific found problem required, proven with a new regression test, verified against
the full suite.

## What was found and NOT fixed this sprint — named debt, not guessed at

| ID | Finding | Why not fixed this sprint |
|---|---|---|
| `LAMBDA003-AUTH-001` | Auth fallback (`shared/deps.py::_verify_token`) silently drops to a revocation-check-free local JWT verification on any Supabase-side exception | A genuine security-vs-availability policy decision (fail closed on Supabase outages = downtime for everyone; current behavior = a narrow, external-fault-gated revocation-lag window) — the founder's call, same class as `LAMBDA-001`'s deferred timeout decision. **ACCEPTED RISK.** |
| `LAMBDA003-EVT-001` | TOCTOU race in `case_evolution.py`'s consequence-dedup (read-then-write, not atomic) — same-tenant duplicate side-effect only, requires a narrow concurrency window | Correct fix needs an unvalidated staleness-threshold heuristic on a production-critical engine; no production data to safely choose the number — full fix shape specified in `EVENT_ISOLATION_REPORT.md` for whoever has the data. |
| `LAMBDA003-RLS-001` | `kancelarija_clanovi` RLS enabled with zero policies, recursively breaking 10 dependent policies' firm-visibility branch — confirmed NOT exploitable (over-restrictive direction, RLS decorative given service-role bypass) | Real fix needs a new `SECURITY DEFINER is_member_of()` helper and 10 policy updates — a real RLS-architecture decision, not urgent since non-exploitable. |
| `LAMBDA003-AUTH-002` | "Firm admin" defined inconsistently between `kancelarija.py` (strict owner) and `zadaci.py`/`workflow.py` (owner-or-partner) — not a confirmed bypass today, a drift risk | Unifying needs a single source-of-truth decision on which definition is correct. |

Two items checked and correctly left CLOSED, not reopened: `SEC-039` (dokument.py session model, re-confirmed
by 2 independent forks this sprint) and `SEC-019`/`SEC-060` (both re-confirmed accurately described).

## What was checked and found solid — CERTIFIED, with fresh evidence

Every mechanism named in the mission's own 8-agent charter was checked, not sampled: every ownership-check
helper in the repo (Agent 1), every RLS policy interaction across 151 tables (Agent 2), 18 named
features/AI-modules attacked horizontally (Agent 3), the full vertical role ladder User→Admin→Founder→System
(Agent 4), every prompt-building path for 12 named AI modules (Agent 5), the Event Bus under 7 attack
techniques (Agent 6), and every cache/session mechanism in the codebase (Agent 7). Full detail and file:line
citations for every clean bill are in the 6 companion reports (`AUTHORIZATION_FORENSICS.md`,
`RLS_CERTIFICATION.md`, `TENANT_ISOLATION_REPORT.md`, `AI_CONTEXT_ISOLATION.md`, `EVENT_ISOLATION_REPORT.md`,
`CACHE_ISOLATION_REPORT.md`) and the consolidated `ATTACK_MATRIX.md`.

## Process note — a finding about how this sprint itself was run, not about the product

Every one of the 7 investigative forks was explicitly, forcefully briefed as read-only — a direct response to
Certification 002's own process failure, where a fork exceeded its read-only brief and pushed a commit to
`origin/main` unsupervised, silently dropping a CRITICAL finding another fork had correctly found. This time,
all 7 investigative agents stayed strictly read-only as instructed; the coordinator (not any fork) implemented
every fix directly, verified each one against its own targeted tests plus the surrounding test file, then ran
the full suite. This worked as intended — no repeat of the prior sprint's process failure.

## Regression proof

Full suite, independently re-run by the coordinator, not taken from any fork's self-report: **2,984 passed,
1 skipped, 7 failed, 22 warnings.** The 7 failures are entirely confined to
`tests/test_akcija2_faza4_2026_07_24.py` and are **pre-existing, confirmed unrelated to this sprint's
changes** — full root-cause analysis and partial mitigation in `REGRESSION_TEST_REPORT.md`. None of this
sprint's own 19 new tests fail; every file this sprint modified was individually re-verified green both in
isolation and combined with its surrounding test suite before the full run.

## Verdict, per the mission's own required closure format

Every critical authorization/isolation flow ends this sprint in exactly one of the three required states:
**FIXED** (4 items, all proven with a new regression test), **ACCEPTED RISK** (1 item, a stated tradeoff with
reasoning), or **ARCHITECTURAL DEBT** (2 items, each with a precise reason a guess would be worse than naming
the gap honestly). No flow was left ambiguous or unverified. The mission's own success condition — find a
real bypass, not confirm things look fine — was met decisively: this sprint found and closed the single worst
security finding of the entire engagement.
