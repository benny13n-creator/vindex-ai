# CREDIT RACE — TEST MATRIX

**Harness:** `tests/test_beta_gate_credit_race_postgres.py` — a **real
PostgreSQL 17.9 server**, executing `migrations/107_beta_gate_credit_race_closure.sql`
**verbatim** (the shipped artifact, read from disk, not a copy). 36 tests.
Skips with a clear reason where no server is reachable; it ran, not skipped,
in both certification runs.

Asserted invariant everywhere:
`Σ(charged) + final_balance == initial_balance` **and** `final_balance >= 0`.

## §7 Contract (T1–T6)

| Test | Setup | Expected | Result |
|---|---|---|---|
| T1 exact balance | 10, request 10 | success, balance 0 | PASS |
| T2 insufficient | 10, request 11 | `-1`, balance unchanged 10 | PASS |
| T3 partial | 10, request 4 | success, balance 6 | PASS |
| T4 zero request | 10, request 0 | `-1`, no mutation | PASS |
| T5 negative request | 10, request −5 | `-1`, **no credit minted** | PASS |
| T6 nonexistent user | — | `-1`, unrelated rows untouched | PASS |
| NULL amount | 10, request NULL | `-1`, no mutation | PASS |
| drain-then-push | 3, then 5×1 more | `2,1,0` then five `-1` | PASS |

## §8/§9 Concurrency — mandated scenarios

| Scenario | Setup | Required | Result |
|---|---|---|---|
| **A** | balance 10, 20 concurrent × 2 | ≤5 granted, final 0 | **5 granted, final 0** — PASS |
| **B** | balance 100, 100 concurrent × 3 | ≤33 granted, reconciles | **≤33, exact** — PASS |
| **C** | balance 1, 50 concurrent × 1 | exactly 1 granted | **1 granted, 49 denied** — PASS |
| **D** | balance 10, 50 concurrent × 1 | exactly 10 granted | **10 granted, final 0** — PASS |
| **E** | balance 100, mixed 1/2/3/5/10 | charged ≤100, exact | PASS |
| duplicate storm | balance 5, 12 concurrent × 5 | exactly 1 funded | PASS |
| deduct+refund interleave | balance 100, 20×deduct ‖ 20×refund | `final == 100 − charged + refunded` | PASS |

Every request classified explicitly as SUCCESS / INSUFFICIENT_CREDITS / ERROR;
zero ERRORs, zero deadlocks, no worker left alive.

## §12 Full-stack (real `UsageService.consume` against the real function)

| Test | Result |
|---|---|
| charges the real multiplier amount (2×6 = 12 leaves the balance) | PASS |
| underfunded → 402 **and charges nothing** | PASS |
| consume→refund round trip is exactly net zero for a 6× feature | PASS |
| fractional price (0.5) charges nothing, does not 402 | PASS |
| 20 concurrent consume() at 12 credits on a 60 balance → ≤5 granted | PASS |
| **1-credit feature, 40 concurrent → exactly 1 granted** | PASS |
| 1-credit underfunded → 402, balance untouched | PASS |
| consume never calls `deduct_credit` for any amount | PASS |
| explicit-multiplier refund cannot mint | PASS |

## §5 Negative controls — proof the harness detects the real defects

A suite that passes against both the vulnerable and the fixed code proves
nothing. Two controls exist:

| Control | Behaviour observed | Meaning |
|---|---|---|
| pre-107 `deduct_n_credits` body, balance 1, 50 concurrent × 1 | **all 50 granted**, final 0 → invariant violated | harness detects the F5 defect |
| production `deduct_credit` body, balance 0, single call | returns **`0`** while charging nothing | harness detects the CREDIT-CONSUME-001 defect: `0 < 0` is false, so the 402 was unreachable |

Both controls assert the violation, so if either ever starts holding the
invariant the harness has lost its teeth and fails loudly.

## §6/§13 Migration hygiene (executed, not assumed)

| Check | Result |
|---|---|
| 107 produces production's verified ACL `{postgres=X/postgres,service_role=X/postgres}` | PASS |
| 107 is idempotent (full re-run changes nothing, function still correct) | PASS |
| **bare `CREATE OR REPLACE` does not reopen EXECUTE** | PASS — 102's lockdown survives |
| the two new refund functions are locked to `service_role` | PASS |

## Independent adversarial results (separate reviewer)

Could **not** break the SQL: 1700 concurrent ops on balance 1000 → charged
exactly 1000; `p_n` ∈ {0, −1, −5, NULL, INT_MAX, **INT_MIN**} all `-1` with
zero mutation; REPEATABLE READ and SERIALIZABLE both exact (serialization
failures map to `-1` → fail-closed); deadlock test all-or-nothing per
transaction; `pg_temp` shadowing defeated by schema-qualification.
