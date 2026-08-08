# PRODUCTION MIGRATION 107 — VERIFICATION RECORD

**Status: ✅ VERIFIED APPLIED — 2026-08-08**

Migration 107 is confirmed live in production by read-only PostgreSQL catalog
inspection. This supersedes the founder-reported status; the evidence below is
the database's own account of itself, not a report of execution.

## Verification output (production, 2026-08-08)

| Check | Result |
|---|---|
| 1. `deduct_n_credits` — balance guard (`credits_remaining >= p_n`) | **USPEH** |
| 2. `deduct_n_credits` — rejects `p_n <= 0` / NULL | **USPEH** |
| 3. `deduct_n_credits` — `search_path` hardening | **USPEH** |
| 4. `refund_n_credits` — exists and is a single atomic statement | **USPEH** |
| 5. `refund_one_credit` — exists | **USPEH** |
| 6. Privileges — `anon`/`authenticated` cannot execute; `service_role` can | **USPEH** |

6/6. Method: `pg_get_functiondef` + `has_function_privilege` +
`to_regprocedure` against the live catalog. Read-only; no `INSERT`/`UPDATE`/
`DELETE`/`GRANT`/`REVOKE`, no test account created, no credit touched, no
protected RPC invoked.

Integrity: `migrations/107_beta_gate_credit_race_closure.sql`, commit
`d2439e6`, `sha256 f7029d06ba0dd12dfbc118fc98d798a687e3b5501cccb327b01e229e0b74987c`,
unmodified since. What was applied is byte-identical to what the 36-test
PostgreSQL suite exercises.

Check 6 additionally proves `CREATE OR REPLACE FUNCTION` did **not** reopen the
migration-102 lockdown — the concern §13 forbade assuming away.

## Evidence categories (never blurred)

| Category | Item |
|---|---|
| **Independently verified** | Migration 102 — all 5 RPCs locked to `service_role` |
| **Independently verified** | Migration 103 — `authenticated` may write only `profiles.full_name` |
| **Independently verified** | Pre-107 `deduct_n_credits` was the unguarded `GREATEST(0, …)` body |
| **Independently verified** | `deduct_credit` deployed body targets `user_credits` (settles SOA-004: the `profiles` variant is not deployed) |
| **Independently verified** | **Migration 107 applied — 6/6 catalog checks** |
| **Locally reproduced** | 107 behaviour: 36 real-PostgreSQL tests, 5 mandated concurrency scenarios, 2 negative controls |
| **NOT yet verified** | **The deployed application version** — see below |

## ⚠ Remaining gap: the database is fixed, the application build is unconfirmed

Migration 107 closes the race **at the database layer**. But three of this
operation's CRITICAL/HIGH findings are **application-code** fixes, not SQL:

| Finding | Fix location | Commit |
|---|---|---|
| CREDIT-CONSUME-001 (CRITICAL) — `n_credits == 1` routed to `deduct_credit`, whose failure return is `0`, never `-1`, so the 402 was unreachable | `shared/usage.py` | `0561e6c` |
| CREDIT-DEBUG-001 (CRITICAL) — `/api/credits-debug` deducted then blind-wrote a stale balance | `api.py` | `4e6e4f1` |
| CREDIT-REFUND-002 (HIGH) — refund minted credits for explicit-multiplier callers | `shared/usage.py` | `0561e6c` |

If production still runs a build older than `0561e6c`, the 1-credit path —
the dominant price (`ai_pravna_pitanja`, `copilot`, `strategija` at
multiplier=1, ~25 more) — **remains exploitable despite migration 107**,
because that code path never reaches the fixed function.

Verifying the migration therefore does not, by itself, license a Beta GO.

### How to verify the deployed build

Log in to production and open `GET /api/credits-debug`. The response
distinguishes the builds unambiguously:

| Response contains | Meaning |
|---|---|
| key `credit_rpc` with `"OK — … migracija 107 je primenjena"` | ✅ new build **and** 107 live |
| key `credit_rpc` with `"KRITIČNO: … migracija 107 NIJE primenjena"` | new build, but the DB regressed |
| key `deduct_credit_rpc` (old key) | ❌ **old build still deployed** — CRITICAL fixes not live |

This endpoint is safe to call: since `4e6e4f1` it performs zero writes and
probes with `deduct_n_credits(uid, 0)`, which 107's own `p_n <= 0` guard
rejects while mutating nothing. It was deliberately built as the
application-visible contract-drift detector whose absence is the reason a
vulnerable function body survived in production while CI stayed green.

## Post-verification actions completed

1. ✅ This file updated with catalog output; status VERIFIED.
2. ✅ `ARCHITECTURAL_DEBT_REGISTER.md` — 107 recorded as independently verified.
3. ✅ Beta Gate verdict re-evaluated in `FINAL_BETA_GATE_CERTIFICATE.md`.
