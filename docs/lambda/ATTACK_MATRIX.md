# Attack Matrix — Program Lambda, Certification 003

Every attack technique the mission's own 8-agent charter required, with outcome. Per-endpoint coverage for
IDOR/ownership already lives in Certification 002's `IDOR_MATRIX.md` (not reproduced here) — this matrix
covers the NEW attack surfaces this sprint added: enforcement-mechanism bypass, policy interaction, feature-
level horizontal/vertical escalation, prompt-level AI isolation, event-bus manipulation, and cache poisoning.

| # | Attack | Target | Attempted by | Outcome | Status |
|---|---|---|---|---|---|
| 1 | Fail-open on auth-helper DB exception | Every `require_*`/ownership-check helper repo-wide | Agent 1 | `klijenti/router.py::_get_role` granted `Role.ADVOKAT` on any DB exception, same as intentional no-row default | **FIXED** |
| 2 | Implicit trust / fetch-then-check-later | `case_commander.py`, `digital_twin.py`, `copilot.py` | Agent 3 | Sibling data fetched concurrently with ownership check; discarded correctly today, but "one bad refactor away" | **FIXED** |
| 3 | Fallback/bypass in `require_case_owner()`/`require_firm_owner()` | Repo-wide grep | Agent 1 | Neither function exists — ownership enforced via ~300+ inline filters (already swept in Certification 002) | CERTIFIED (N/A) |
| 4 | Policy overlap (2 policies, same op, one weak) | Every multi-policy table | Agent 2 | None found — all multi-policy cases are idempotent duplication or intentional non-overlapping ORs | CERTIFIED |
| 5 | Policy shadowing (later migration silently neutralizes earlier) | `workflow_instances`/`workflow_steps` | Agent 2 | Correct `DROP`+`CREATE` supersede, not shadowing | CERTIFIED |
| 6 | Forgotten table (RLS-scoped data, no policy at all) | All 151 tables | Agent 2 | 6 tables found (incl. `kancelarija_clanovi`) — all default-deny direction, none frontend-reachable | CERTIFIED (safe direction) |
| 7 | Recursive policy loophole | Every cross-table RLS policy | Agent 2 | `kancelarija_clanovi` zero-policy recursively breaks 10 dependent policies — over-restrictive only, not exploitable | ARCHITECTURAL DEBT (`LAMBDA003-RLS-001`) |
| 8 | Ownership-inheritance NULL-FK bypass | Every JOIN/EXISTS-based policy | Agent 2 | Every FK column involved is `NOT NULL` — structurally impossible | CERTIFIED |
| 9 | Horizontal — User A vs. User B across every named feature/AI module | 18 named features | Agent 3 | 0 confirmed vulnerable; 1 hardening finding (#2 above) | CERTIFIED |
| 10 | Vertical — hidden admin path | Every `is_admin`/`_is_founder` branch | Agent 4 | 0 confirmed; `zadaci.py`'s prior fix (Certification 002) re-verified still correct, template applied everywhere else | CERTIFIED |
| 11 | Vertical — stale JWT claims trusted | Token verification chain | Agent 4/8 | No role/permission ever read from a JWT claim; always re-queried from Postgres per request | CERTIFIED |
| 12 | Vertical — cached permissions surviving revocation | Repo-wide cache grep | Agent 4 | Zero permission/role caching anywhere (only the JWKS public-key cache, not user state) | CERTIFIED |
| 13 | Vertical — delayed revocation on firm-membership removal | `kancelarija_clanovi.status` check | Agent 4 | Queried live every request, no delay window | CERTIFIED |
| 14 | Vertical — auth fallback trusts a revoked-but-unexpired token during a Supabase outage | `shared/deps.py::_verify_token` | Agent 4/8 | Confirmed real, not attacker-triggerable on demand — availability-vs-security tradeoff | ACCEPTED RISK (`LAMBDA003-AUTH-001`) |
| 15 | AI — cross-case leakage in a portfolio loop | CIO, Commander, Morning Briefing | Agent 5 | None found — every loop iteration correctly per-case-scoped | CERTIFIED |
| 16 | AI — cross-user leakage via bespoke context builder | 12 named prompt builders | Agent 5 | 0 in live paths; 1 dormant gap in the Document Visibility Engine's own scale safety-net | **FIXED** (`get_document_full_text`) |
| 17 | AI — cross-firm leakage in a firm-wide feature | Memory Graph, Commander's `opponent_intel`, Predictor's `case_patterns` | Agent 5 | All genuinely firm-scoped, derived from caller's own membership only | CERTIFIED |
| 18 | AI — stale/foreign context cache serving a wrong prompt | Every daily/portfolio cache | Agent 5/7 | All keyed `(user_id, date)` — no bare-resource-id cache key found in the context-building layer | CERTIFIED |
| 19 | Event Bus — replay | 7 wired event types + `PREDMET_KREIRAN` | Agent 6 | Idempotent by design; 4 non-durable-critical types would duplicate a same-owner row (pre-existing, tracked risk) | CERTIFIED |
| 20 | Event Bus — forged event via unauthenticated input | Every webhook handler | Agent 6 | Zero write-to-`events` path from unvalidated external input | CERTIFIED |
| 21 | Event Bus — orphan event (deleted predmet/user) | Consequence executors | Agent 6 | Fails safely into retry/dead-letter, never misattributes | CERTIFIED |
| 22 | Event Bus — cross-tenant race via shared state | Concurrent dispatch | Agent 6/8 | No shared mutable state between handler executions of different events | CERTIFIED |
| 23 | Event Bus — TOCTOU double-execution (same tenant) | `case_evolution.py` consequence dedup | Agent 6/8 | Real, reproducible under narrow conditions, same-owner only | ARCHITECTURAL DEBT (`LAMBDA003-EVT-001`) |
| 24 | Cache — poisoning via error/partial state | Every cache write site | Agent 7 | None found — writes only follow a fully-successful result | CERTIFIED |
| 25 | Cache — cross-tenant bleed via a tenant-blind key | `main.py::ask_agent` response cache | Agent 7/8 | **CONFIRMED, CRITICAL** — required zero guessed identifiers, the most severe finding of the whole engagement | **FIXED** |
| 26 | Cache — stale/foreign daily cache (CIO, Commander, Briefing) | Module-level & DB-backed caches | Agent 7 | All correctly `(user_id, date)`-keyed | CERTIFIED |
| 27 | Session — bearer-capability token with no owner binding | `routers/dokument.py` ephemeral Q&A | Agent 7 | Pre-existing, already tracked (`SEC-039`) — re-confirmed, not re-opened | (pre-existing) |
| 28 | Session — `conversations` chat history, anon-key + `session_id` only | `static/vindex.js` | Agent 2/7 | RLS policy cited as the sole guard is unverifiable from source (no `CREATE TABLE`/policy in the repo) | NEEDS LIVE VERIFICATION |

## Adversarial re-verification coverage

Every row marked CONFIRMED above (rows 1, 2, 14, 23, 25 as findings; all CERTIFIED rows as clean bills) was
independently re-traced by Agent 8 with its own file:line evidence, not by repeating the originating agent's
citations. 7 of 7 substantive findings survived; zero were refuted; 2 (row 14, row 25) were found to be more
severe/precise than originally stated.
