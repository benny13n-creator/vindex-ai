# CREDIT SYSTEM — FORENSIC AUDIT

**Date:** 2026-08-08 · **Scope:** every path that can move `user_credits.credits_remaining`

## 1. Dependency map

```
request
  └─ PermissionService.require(feature)        entitlement only, no money
  └─ UsageService.consume(uid, email, feature, multiplier=?)      shared/usage.py:253
       ├─ get_policy(feature)                  krediti, credit_multiplier  (60s cache)
       ├─ _is_founder(email) ─────────────────► FOUNDER_BALANCE, never charged
       ├─ _claim_cooldown_atomic()             atomic, UNIQUE(user_id,feature,dan)
       ├─ dnevni_limit / mesecni_limit         reads feature_usage (NOT user_credits)
       ├─ n_credits = int(krediti × multiplier)
       ├─ n_credits > 0:
       │    ├─ _get_credits()                  PRE-CHECK ONLY — racy by design
       │    └─ _deduct_n_credits(uid,email,n)  shared/deps.py:578
       │         └─ rpc deduct_n_credits       ◄── THE atomic guard (migration 107)
       │              >=0 charged │ -1 NOT charged
       │         └─ _increment_monthly_usage() only on success
       └─ n_credits <= 0: no charge, balance read only

  └─ AI operation
       ├─ success ─────────────────────────────► done
       └─ failure ─► UsageService.refund(uid,email,feature, multiplier=?, credits=?)
                       └─ _refund_n_credits()   shared/deps.py:600
                            └─ rpc refund_n_credits   atomic (migration 107)
```

**Direct mutations of `user_credits` outside this path** (exhaustive grep,
non-test):

| Site | Nature | Status |
|---|---|---|
| `shared/deps.py:411`, `api.py:395` | auto-heal `INSERT` of a missing row | safe — insert only, cannot overwrite |
| `shared/deps.py:569` | `upsert(..., ignore_duplicates=True)` | safe — never resets an existing balance |
| `api.py:2637` (was) | absolute `update({"credits_remaining": stale})` | **CRITICAL, fixed** — see CREDIT-DEBUG-001 |
| `shared/deps.py:366` | RMW on `mesecno_korisceno`/`mesec` | quota field only, never the balance — SOA-005, deferred |

## 2. Invariants

1. **Consumption** — total granted usage must never exceed available credits.
2. **Refund symmetry** — a failed operation refunds exactly what was charged.
3. **Concurrency** — no interleaving may create, lose, duplicate or resurrect credits.

## 3. Violation points found

| ID | Sev | Where | Violation | Status |
|---|---|---|---|---|
| F5 | CRITICAL | `deduct_n_credits` body | no balance predicate → concurrent overdraw | fixed, migration 107 |
| CREDIT-CONSUME-001 / SOA-001 | CRITICAL | `usage.py` n==1 branch | routed to `deduct_credit`, whose failure return is `0` not `-1`, so the 402 was unreachable | fixed, code only |
| CREDIT-DEBUG-001 | CRITICAL | `api.py` `/api/credits-debug` | deducted then blind-wrote a stale balance; any authenticated user, no rate limit | fixed |
| CREDIT-REFUND-001 | HIGH | `refund_one_credit` | RPC defined in no migration → Python RMW fallback could erase a concurrent charge | fixed, migration 107 |
| CREDIT-REFUND-002 | HIGH | `UsageService.refund` | recomputed from registry multiplier; explicit-multiplier callers refunded 6× a 1× charge | fixed |
| SOA-003 | HIGH (latent) | `supabase_setup.sql` | re-runnable GRANT would reopen the 102 lockdown | fixed |
| SOA-004 | HIGH (latent) | `supabase_migration.sql` | second `deduct_credit` against `public.profiles` | fixed |
| SOA-006 | MEDIUM | `api.py` prompt guard | charged, zero AI work, no refund | fixed |
| SOA-012 | MEDIUM | `api.py` SSE | disconnect = `BaseException` → refund skipped | fixed |
| SOA-009 | MEDIUM | `strategija.py`, `web3.py` | 402/429 masked as 500, paywall never fired | fixed (19 sites) |
| CREDIT-LOSTREPLY-003 | MEDIUM | `deps.py` | committed charge + lost reply is indistinguishable from no charge | fails closed; now logged distinctly |
| SOA-016 | LOW | `api.py` | refund display hardcoded `+1` | fixed |

## 4. Structural root cause

**The credit system had two of everything.** Two `deduct_credit` definitions
(different tables, different sentinels), two sentinel conventions, duplicate
helper copies in `api.py`, and a test fixture that was a third hand-typed
copy of the SQL. Migration 107 collapsed the refund side into one
implementation; this operation did the same for the consume side by routing
every charge through `deduct_n_credits`. Tests now enforce **exactly one
definition per credit function** repo-wide.

## 5. Deferred, with reasons

| ID | Why not fixed here |
|---|---|
| SOA-005 | `_increment_monthly_usage` RMW is on a quota column, never the balance, and its only reader (`require_credits`) is dead code. An atomic fix needs a new RPC + migration; queued, not blocking. |
| SOA-007 | Frontend auto-retries charged POSTs on 502/503 → up to 3 charges. Real, but a client-side change to shared dispatch logic; wants its own tested change, not a tail-end edit. |
| SOA-008 | `multi_agent` charges when all agents failed. Real; same reasoning. |
| SOA-010/011/013/014/015/017/018 | Accounting-precision and hygiene items; none can overdraw or mint. Listed in `CREDIT_SECOND_ORDER_AUDIT.md`. |
