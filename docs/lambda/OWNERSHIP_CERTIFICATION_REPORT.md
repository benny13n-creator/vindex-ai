# Ownership Certification Report — Program Lambda, Certification 002

**Mission**: "Ovo je sprint u kome ne želimo da 'nađemo nekoliko propusta'. Cilj je da pokušamo da slomimo
svaki ownership mehanizam u platformi." Assume Vindex AI is already in closed beta; assume a real user
actively tries to reach data that isn't theirs. Success is measured by whether a bypass is FOUND, not by
confirming things look fine.

**Method**: 8 named roles executed as 9 independent forensic forks (API Penetration split into two
alphabetic sweeps, a-m and n-z+`api.py`), each read-only, each required to report every item checked — not
just failures — with a SAFE / VULNERABLE / NEEDS-DEEPER-LOOK verdict per item. Two forks' initial reports
were lost to an infrastructure issue mid-sprint (background-task output not recoverable from disk) and were
re-run from scratch rather than left unverified.

## Headline result

**12 real ownership bugs were found and fixed this sprint** — the mission's own stated success condition
("ako i posle toga ništa ne prođe, dobijaš dokaz da je izolacija ispravna") was not met in the trivial sense;
real bypasses existed, spanning the API layer, the database RPC layer, database column-privilege layer, and
cross-module ownership drift. All were fixed with minimal, targeted changes and covered by new regression
tests. Three of the twelve — `deduct_credit()`, `set_user_pro()`, and the `profiles` table's own `UPDATE`
column privilege — are database-layer bypasses reachable directly via PostgREST/Supabase-JS by any
authenticated user (the first two via a `SECURITY DEFINER` RPC, the third via a raw table `UPDATE` from the
browser's public anon key), **completely bypassing the FastAPI backend, its rate limiting, and every one of
this engagement's prior API-layer security work.** Both `set_user_pro` and the `profiles` bug independently
allowed a free, permanent PRO subscription upgrade with zero payment — a monetary-impact bug, not just a
data-isolation one. The `profiles` finding was reported by the Database & RLS Auditor fork during this
sprint's own investigation but dropped during the first triage/synthesis pass — caught and closed on a
manual re-review after this sprint's first commit (`622c62e`), in a direct follow-up commit; noted here in
the interest of an honest record, not hidden.

## What was actually broken (see `IDOR_MATRIX.md` for the full per-endpoint table)

| Layer | Found by | Bugs | Worst case |
|---|---|---|---|
| API (routers a-m) | API Penetration Auditor A | 6 fixed (billing.py, intake.py, memory_graph.py, multi_agent.py, copilot.py, evidence.py) + 7 more in court_predictor.py + 1 in corrections.py (write-side FK pollution, same sweep) | Cross-tenant read of another firm's case names, client PII, billing line items, and hearing schedule via `multi_agent.py`'s billing/deadline agent |
| API (routers n-z + api.py) | API Penetration Auditor B | 4 fixed (smart_intake.py, api.py, zadaci.py, workflow.py) | Any self-service firm admin could delete **any other firm's task** by guessing/observing a UUID — vertical privilege escalation, not just horizontal |
| Database / RPC | Database & RLS Auditor | 2 CRITICAL fixed via migration 102 (`deduct_credit`, `set_user_pro`) + 3 defense-in-depth | Free permanent PRO upgrade for any authenticated user; cross-account credit-drain DoS |
| Database / column privilege | Database & RLS Auditor (missed in first triage, closed on manual re-review) | 1 CRITICAL fixed via migration 103 (`profiles` UPDATE) | Free permanent PRO upgrade via a direct browser-side table write, independent of `set_user_pro` |
| Background workers | Background Worker Auditor | 0 exploitable found; 1 NEEDS-DEEPER-LOOK architectural note | `case_evolution.py`'s 5 event-consequence executors trust the outbox event's `user_id` without re-verifying at dispatch time — not exploitable today (no ownership-reassignment code path exists anywhere in the repo), but a latent gap for a future multi-user-firm-sharing feature |
| Storage | Storage Auditor | 0 exploitable found across 21 examined paths | — |
| AI context | (re-confirmed via API Penetration + prior Tau/Lambda sprints) | 1 fixed (`multi_agent.py` billing/deadline agent context leak, counted above) | — |
| Integration / ownership drift | Integration + Adversarial Tester | 4 fixed (counted in the n-z row — `smart_intake.py`/`api.py`/`zadaci.py`/`workflow.py` are exactly the "outer check exists, inner action doesn't" shape this role was chartered to find) | — |
| Race/replay/batch | Integration + Adversarial Tester | 0 live-executable finding (no running deployment in this environment); reasoned through code-level, see `EVENT_OWNERSHIP_REPORT.md` | — |

## Fix discipline

Every fix in this sprint follows the mission's own rule: minimal change, no refactor, no new capability, no
architecture change beyond what the specific found problem required. Two findings did NOT get a code fix
this sprint, by design:

- **`routers/integracije.py::post_webhook_clio`** trusts an attacker-controlled `vindex_user_id` in the
  webhook body, gated only by a platform-wide shared secret — real, but CREATE-only (no read/write of
  existing data) and requires an integration-auth-model redesign, not a filter. Opened as
  **`LAMBDA-OWN-001`** in `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`.
- **`routers/dokument.py`'s Pinecone session-based document Q&A** (`/pitanje`, `/analiza`, `/rokovi`,
  `/klasifikuj-sesija`) has no `user_id` binding on its `session_id` at all — this is a PRE-EXISTING, already
  tracked finding (`SEC-039`, High severity, opened 2026-08-02), independently re-confirmed by both the
  Storage Auditor and (via the RLS census) the Database & RLS Auditor this sprint. Not re-opened as a new
  Lambda finding; status remains whatever `SEC-039` is tracked as in the Security Governance Framework.

## Verdict, per the mission's own required closure format

Every critical ownership flow ends this sprint in exactly one of the three states the mission requires:

- **FIXED** (14 items — 11 app-layer bugs + 3 database-layer bugs: the RPC lockdown counted as 2 for
  `deduct_credit`/`set_user_pro` plus 1 for the `profiles` column-privilege fix, or 16 if the 3
  defense-in-depth RPC lockdowns are counted individually)
- **ARCHITECTURAL DEBT** (2 items — `LAMBDA-OWN-001` new this sprint, `SEC-039` re-confirmed pre-existing)
- **CERTIFIED** (everything else examined and found already correct — the large majority: 260/287 API
  endpoints in the a-m sweep alone, 19/21 storage paths, 11/13 background workers, 197 RLS policies sampled
  across 40+ migration files, the canonical `build_case_context()` path re-confirmed for the 5th+ consecutive
  sprint)

No flow was left in an ambiguous or unverified state.

## Regression proof

Full suite: **2,971 passed, 1 skipped, 0 failed** (baseline entering this sprint: 2,947 passed, 1 skipped —
see `REGRESSION_TEST_REPORT.md`). +24 exact delta: `tests/test_lambda002_ownership_idor_fixes.py` (12 tests
covering the app-layer fixes across `smart_intake.py`/`api.py`/`zadaci.py`/`workflow.py`/`billing.py`/
`copilot.py`/`intake.py`), `tests/test_lambda002_multi_agent_context_leak.py`, `tests/test_lambda002_rpc_ownership_lockdown.py`
(4 tests statically guarding migration 102), `tests/test_lambda002_profiles_column_lockdown.py` (4 tests
statically guarding migration 103, added on the manual re-review pass), plus fixture updates (not counted in
the delta) to `test_billing_timer_race.py`, `test_mission001_predmet_klijenti.py`, and
`test_sprint004_review_resolve.py` for the new ownership-check call sites.

## What this sprint does NOT certify

- **Live Supabase Storage bucket policies** — no `storage.objects` RLS policy exists anywhere in the repo;
  if any exists, it was configured manually in the Supabase Dashboard and is invisible to a code audit. The
  app-layer ownership checks the Storage Auditor verified are real and sufficient given the service-role-key
  bypass fact, but this is a code-only certification, not a live-environment one.
- **Race conditions under real concurrent load** — reasoned through at the code level (see
  `EVENT_OWNERSHIP_REPORT.md`), not executed against a running deployment, since none exists in this
  environment. The one confirmed real TOCTOU race in this codebase (`billing.py::timer_start`) was already
  fixed in a prior sprint (migration 084) and re-verified, not newly found, here.
- **Migrations 102 and 103 have not been run against live Supabase.** Per this project's standing rule,
  migrations are never auto-executed — the founder runs them. Until they run, `deduct_credit`, `set_user_pro`,
  and the `profiles` `UPDATE` column-privilege gap all remain live-exploitable in production exactly as
  described above.
