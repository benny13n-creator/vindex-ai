# PRODUCTION MIGRATION 107 — VERIFICATION RECORD

**Status: UNVERIFIED — awaiting read-only production catalog results.**

Founder reported on 2026-08-08 that `migrations/107_beta_gate_credit_race_closure.sql`
was executed against production. Per this operation's Rule 1, a report of
execution is **not** evidence. This file records the verification chain and
will be updated only when catalog output is supplied.

## Evidence categories (never blurred)

| Category | Item |
|---|---|
| **Independently verified** | Migration 102 privileges (all 5 RPCs `anon=false authenticated=false service_role=true`, `proacl={postgres=X/postgres,service_role=X/postgres}`) — catalog read 2026-08-08 |
| **Independently verified** | Migration 103 column grants (`authenticated`-writable on `public.profiles` = `full_name` only) — catalog read 2026-08-08 |
| **Independently verified** | Pre-107 `deduct_n_credits` body was the unguarded `GREATEST(0, credits_remaining - p_n)` — catalog read 2026-08-08 |
| **Independently verified** | `deduct_credit` deployed body targets `public.user_credits` and returns `COALESCE(new_credits, 0)` — catalog read 2026-08-08. This settles SOA-004: the conflicting `public.profiles` variant is NOT deployed. |
| **Founder-reported** | Migration 107 executed |
| **Locally reproduced** | Migration 107 behaviour, 36 tests against real PostgreSQL 17 — see `CREDIT_RACE_TEST_MATRIX.md` |
| **NOT yet verified** | The deployed `deduct_n_credits` body after 107; existence + atomicity of `refund_n_credits` / `refund_one_credit`; that 107 did not disturb the 102 lockdown |

## Integrity of what was applied

`migrations/107_beta_gate_credit_race_closure.sql`
- introduced in commit `d2439e6`, unmodified since
- `sha256 = f7029d06ba0dd12dfbc118fc98d798a687e3b5501cccb327b01e229e0b74987c`
- working copy == committed copy (verified)

The "migration applied differs from migration tested" stop condition is
therefore **cleared**: the founder ran the same bytes that the 36-test
PostgreSQL suite exercises.

## Required verification

Run `QUERY A` in `VERIFY_MIGRATIONS_102_103_READONLY.sql` (read-only; SELECTs
against `pg_roles`, `pg_proc`, `pg_class`, `pg_policies`, `information_schema`
only). Required results:

| Row | Required |
|---|---|
| `1 · privilege` × 7 functions | `PASS` for all — including the two functions 107 adds |
| `3 · F5 deduct body` | `PASS - balance guard deployed` |
| `3b · refund body` | `PASS - atomic refund deployed`, `refund_one_credit: present` |
| `2 · mig103 columns` | `PASS` (unchanged) |
| `4 · search_path` | `PASS - search_path set` |

**Any `FAIL` or `INCONCLUSIVE` on rows 1, 3 or 3b keeps Beta at NO-GO.**

## Known limitation of the verifier (fixed, worth recording)

The earlier version of this script reported `PASS` for `deduct_credit` on the
predicate `LIKE '%credits_remaining > 0%'`. Both the correct body and the
defective `public.profiles` variant satisfy that string, so the verifier
would have blessed a broken deployment (finding SOA-004, raised by the
second-order auditor). The application no longer calls `deduct_credit` at
all, which removes the dependency, but the lesson stands: a verification
predicate must discriminate, not merely match.

## Post-verification actions

Once catalog output shows PASS:
1. Update this file with the raw output and change the header to VERIFIED.
2. Update `ARCHITECTURAL_DEBT_REGISTER.md`'s `LAMBDA008-SEC-001` entry from
   "founder-reported, not independently technically verified" to verified,
   citing the catalog evidence.
3. Re-evaluate the Beta Gate verdict in `FINAL_BETA_GATE_CERTIFICATE.md`.

Nothing above may be done on the strength of a report of execution.
