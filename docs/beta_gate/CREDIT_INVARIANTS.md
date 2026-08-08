# Credit system — invariant register (P1-E)

Recorded 2026-08-08. Every row names the invariant, the single place that
enforces it, and the test that **was actually executed** to prove it.

The distinction matters here more than usual. Both migration-107 and
migration-108 test files skip silently when no PostgreSQL server is reachable,
and for most of their life nobody supplied one — so they reported "green"
without running. When a server was finally attached, 11 of 39 failed
immediately. A row below that says PROVEN means the test ran against
PostgreSQL 17 on 2026-08-08 and passed; nothing here is claimed from reading
code.

## Register

| ID | Invariant | Enforced by | Proof | Status |
|----|-----------|-------------|-------|--------|
| INV-001 | A balance can never go negative. | `deduct_n_credits`'s `WHERE credits_remaining >= p_n` (migration 107) | `test_balance_can_never_go_negative_by_construction`, `test_T2_insufficient_balance_fails_and_does_not_mutate` | PROVEN (real PG) |
| INV-002 | Credits are conserved: `spent + remaining == initial`, whatever the interleaving. | single-statement conditional UPDATE | scenarios A–E (`10 balance/20×2`, `100/100×3`, `1/50×1`, `10/50×1`, mixed sizes) | PROVEN (real PG, concurrent) |
| INV-003 | A result that was not delivered is not charged. | per-endpoint gating | `test_p1_charge_on_failure.py` — conflict_check, `/dokument/pitanje`, multi_agent, `/pipeline` | PROVEN (unit) |
| INV-004 | A refund can never mint credits beyond what was charged. | `refund_n_credits` + explicit `credits=` pass-through | `test_refund_with_explicit_credits_cannot_mint`, `test_deduct_then_compensating_refund_is_net_zero`, `test_refund_contract_rejects_non_positive` | PROVEN (real PG) |
| INV-005 | Daily and monthly counters never exceed their configured limit, and never lose a count. | `increment_feature_usage` / `increment_monthly_usage` (migration 108) | `test_concurrent_calls_cannot_exceed_the_daily_limit`, `test_concurrent_increments_lose_nothing`, `test_P1C_fifty_concurrent_charges_count_as_exactly_fifty` | PROVEN (real PG, 50 threads) |
| INV-006 | A charge the database refused consumes no monthly quota — and one it accepted consumes exactly one slot. | `_deduct_n_credits` increments only on success | `test_INV006_rejected_charge_does_not_consume_monthly_quota`, `test_INV006_accepted_charge_does_consume_monthly_quota` | PROVEN (real PG) |
| INV-007 | Concurrent requests cannot together spend more than the balance funds. | atomicity of INV-001 under READ COMMITTED re-check | `test_concurrent_consume_through_real_python_path_cannot_overdraw`, `test_concurrent_duplicate_requests_cannot_overdraw` | PROVEN (real PG, concurrent) |

## Negative controls

An invariant suite that passes against both the vulnerable and the fixed code
proves nothing. Each of these was run with the fix reverted, and failed:

| Control | Reverted to | Observed |
|---------|-------------|----------|
| `test_negative_control_legacy_body_DOES_overdraw` | pre-107 `deduct_n_credits` | 50 of 50 requests succeed against a 1-credit balance |
| `test_negative_control_deduct_credit_reports_success_when_it_charged_nothing` | `deduct_credit` on the 1-credit path | success reported, nothing charged |
| `test_negative_control_read_modify_write_loses_updates` | pre-108 counter pattern | counts land well below the number of calls |
| P1-C (2 of 3 tests) | pre-P1-C `_increment_monthly_usage` | fails |
| CI-RED-002 regression test | pre-fix `smart_intake.py` | 0 `NEW_CLIENT_LINKED` emissions instead of 1 |

## Not covered

Stated plainly rather than left to be discovered:

- **Retry idempotency.** No invariant asserts that repeating a request charges
  once. It does not: `/multi-agent/pipeline`, `/kompletna-analiza` and the other
  202-job endpoints re-charge completed work on retry. Closing this needs a
  request-level idempotency key; the repo already has the pattern
  (`idempotency_key` + partial UNIQUE + RPC, migration 073).
- **Charge-on-failure beyond the four endpoints fixed.** Roughly 48 of ~50
  routers charge up front with no refund path.
- **INV-005 in production.** It depends on `migrations/108_atomic_usage_counters.sql`,
  which is READY BUT NOT APPLIED. Until the founder runs it, the counters are
  the pre-108 read-modify-write on the live database, and the P1-C call falls
  through to an in-memory counter.
