# CREDIT REFUND — CHAOS REPORT

Invariant under test in every scenario:
`initial_balance − legitimate_charges + legitimate_refunds == final_balance`

## Findings

### CREDIT-REFUND-001 — the refund path had no atomic implementation at all (HIGH, fixed)

`shared/deps.py::_refund_one_credit` called `rpc("refund_one_credit")`. That
function was **defined in no migration anywhere in the repository** — grep
over `*.sql` returned nothing. Every refund therefore raised and fell into
the Python fallback:

```python
cur = select credits_remaining          # read
update credits_remaining = cur + 1      # write
```

Two concurrent refunds lose a credit. Worse, a refund racing a **charge**
writes back a balance read *before* the charge, erasing it — free AI usage
through the refund door, the same invariant violation as F5.

**Fixed** in migration 107: `refund_n_credits` / `refund_one_credit` are
single-statement increments. The racy fallback was **deleted, not replaced** —
a failed refund under-credits the user (bounded, loudly logged), whereas a
racy refund silently corrupts the balance.

### CREDIT-REFUND-002 — refund minted credits for three routers (HIGH, fixed)

`refund()` recomputed the amount from the **registry** `credit_multiplier`,
while `routers/strategija.py` (8 sites), `digital_twin.py` and
`strategy_simulator.py` charge with an **explicit** `multiplier=1`.
Reproduced against the real database:

```
krediti=1 registry_mult=6  consume(multiplier=1): charged=1 refunded=6  net +5   MINTS
krediti=1 registry_mult=3  consume(multiplier=1): charged=1 refunded=3  net +2   MINTS
krediti=1 registry_mult=1  consume(multiplier=6): charged=6 refunded=1  net −5   LOSES
```

Latent only because those three routers have zero refund call sites today —
a loaded gun aimed at the exact features the fix's own docstring cited.
**Fixed:** `refund(..., credits=N)` refunds precisely what was charged, with
no recomputation. `multiplier=` retained for runtime-computed factors.

### SOA-006 — prompt-guard rejection charged and never refunded (MEDIUM, fixed)

`api.py` `/api/pitanje`: the guard-blocked branch is a **normal return**, so
neither `except` handler ran, and it sits above the cache-hit refund check.
Zero AI work; the credit was kept on every attempt. A lawyer whose case
description trips a false positive paid each time. **Fixed:** refund before
the return, `_credit_consumed = False` to prevent double refund.

### SOA-012 — client disconnect skipped the refund entirely (MEDIUM, fixed)

`/api/pitanje/stream` consumes the credit *outside* the generator; all refund
paths lived inside `except Exception`. Starlette closes the generator on
disconnect, raising `GeneratorExit` / `CancelledError` — **`BaseException`,
not `Exception`** — so no refund ran. Closing the tab on a slow answer cost a
credit for nothing. **Fixed:** `except BaseException` refunds then re-raises
(cancellation is never swallowed), with a `_refunded` flag making the three
paths idempotent.

## Chaos scenarios and results

| Scenario | Result |
|---|---|
| charge ‖ refund, 20 + 20 concurrent, same user | `final == initial − charged + refunded` exactly — PASS |
| multiple simultaneous refunds | atomic increment, no lost update — PASS |
| deduct → compensating refund (6× feature) | net zero, exact — PASS |
| rollback after deduction inside an explicit transaction | balance fully restored — PASS |
| commit after deduction | persists — PASS |
| refund of 0 / negative | `-1`, **cannot drain** — PASS |
| refund for nonexistent user | `-1`, no row created — PASS |
| retry storm (12 identical concurrent charges, balance 5) | exactly 1 funded — PASS |
| response lost after commit | fails **closed** (user not delivered); logged `[CREDIT_RECONCILE]` — accepted, see below |

## Double-refund analysis (independent reviewer, negative result)

All 8 refund call sites traced individually; **no exploitable double refund
exists**. `/api/pitanje` is guarded by `_credit_consumed`, cleared immediately
after the success-path refund with no awaitable between. `/api/pitanje/stream`
success and error refunds are mutually exclusive branches. `copilot.py`'s two
sites are separated by a `raise`. `predmet_upload_ai` has a single gated site.

## Accepted residual risks

| Risk | Why accepted |
|---|---|
| `refund_n_credits` has no ledger, cap, or link to a prior charge | `service_role`-only (verified in catalog); amount is registry-derived, not caller-controlled. A refund ledger is an architecture change, not a bug fix. |
| Charge committed, reply lost → user billed without delivery | Undecidable without an idempotency key, which the product deliberately lacks. Failing closed is the safe direction; now emits a distinct `[CREDIT_RECONCILE]` log for manual reconciliation. |
| `refund()` re-derives price from a 60 s registry cache | An Admin Console price edit between charge and refund refunds the stale amount. Mitigated by `credits=`; callers using it are exact. |
| Only 4 features refund at all (SOA-011) | Not a violation of the invariant — those features charge correctly and simply never compensate on failure. Making the safe shape default (a `charged()` context manager) is queued, not blocking. |
