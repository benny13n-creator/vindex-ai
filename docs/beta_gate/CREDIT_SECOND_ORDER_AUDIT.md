# CREDIT SYSTEM — SECOND-ORDER AUDIT

Two independent reviewers, each briefed to assume the credit system was still
broken. One attacked the database with real concurrency; one audited the code
from four attacker perspectives. **Both found real defects the implementer
missed.** That is the headline: the migration-107 work was necessary and
correct, and it was not sufficient.

## Perspective A — "free AI usage without violating authentication"

| ID | Sev | Finding | Status |
|---|---|---|---|
| SOA-001 / CREDIT-CONSUME-001 | **CRITICAL** | `consume()` routed `n_credits == 1` to `deduct_credit`, whose NOT-FOUND branch returns `COALESCE(new_credits, 0)` — the balance, never `-1`. `if preostalo < 0` was unreachable; no 402; operation delivered. `n == 1` is the dominant registry price. Reproduced: balance 1 + 40 concurrent → 37 granted (36 free); balance 5 + 60 concurrent → 55 free. | **FIXED** — all charges routed through `deduct_n_credits` |
| CREDIT-DEBUG-001 | **CRITICAL** | `/api/credits-debug`, any authenticated user, no rate limit: deducted a real credit then blind-wrote a balance read earlier in the same request, erasing any charge committed in between. Loop it while running expensive operations → unlimited free usage. | **FIXED** — non-destructive `p_n=0` probe, zero writes |
| SOA-002 | HIGH | The "real database" test file installed a verbatim copy of the vulnerable `deduct_credit` as a fixture and **never called it**; every `consume()` test used n=12 or n=0. This is why SOA-001 survived a certification aimed at it. | **FIXED** — 1-credit concurrency test, routing test, and a negative control that exercises the vulnerable body |
| SOA-010 | MEDIUM | Fractional registry prices truncate to 0 (silent free feature); `feature_usage` logs the un-truncated float while `user_credits` moves by `int()`, so analytics diverge from the ledger. | Deferred — precision, cannot overdraw |

## Perspective B — "make a legitimate user's credits disappear"

| ID | Sev | Finding | Status |
|---|---|---|---|
| SOA-003 | HIGH (latent) | `supabase_setup.sql` still `GRANT`ed `deduct_credit` EXECUTE to `authenticated` — the exact cross-account drain migration 102 exists to close — and `shared/deps.py` instructs operators to re-run that file. Catalog proves 102's revoke is live, so this was a loaded gun, not an open wound. | **FIXED** — GRANT replaced with REVOKEs; re-running now converges on locked-down |
| SOA-004 | HIGH (latent) | `supabase_migration.sql` defined a **second** `deduct_credit`, same signature, against `public.profiles` with a different sentinel and no `search_path`. Last file to run wins; had it won, `user_credits` was never decremented and the whole product was free. | **FIXED** — removed; a test now enforces one definition per credit function |
| SOA-006 | MEDIUM | Prompt-guard rejection charged, did zero AI work, never refunded. | **FIXED** |
| SOA-012 | MEDIUM | SSE disconnect (`BaseException`) skipped every refund path. | **FIXED** |
| SOA-008 | MEDIUM | `multi_agent` swallows agent exceptions into `{"greska": …}`, so `gather` always "succeeds" and it charges up to 3 credits even when all agents failed; no refund site exists in that file. | Deferred |
| SOA-011 | MEDIUM | Only 4 of ~150 charged features can refund at all. | Deferred — not an invariant violation |
| SOA-017 | LOW | CIO/case_commander claim-then-generate can cache an empty report for 6 h on generation failure. | Deferred |

## Perspective C — "charge twice for one operation"

| ID | Sev | Finding | Status |
|---|---|---|---|
| SOA-007 | MEDIUM | `static/vindex.js` auto-retries charged POSTs up to twice on 502/503 or a non-JSON body. A gateway timeout during a 40 s GPT-4o call does not stop the backend — it charges and completes. Up to **3 charges per user action**. Aggravated because the AI-queue timeout deliberately returns 503, which is in the retry list. No credit-charged endpoint has an idempotency key. | Deferred — real; wants its own tested change to shared dispatch |
| SOA-014 | LOW | Copilot charges for intent routing, then the routed feature charges again. | Deferred |

## Perspective D — "refund twice / refund more than charged"

**No exploitable double refund exists.** All 8 refund sites traced; each pair
is mutually exclusive (flag-guarded, branch-exclusive, or separated by a
`raise`). Auditable negative result — see `CREDIT_REFUND_CHAOS_REPORT.md`.

The one real defect in this perspective was amount, not count:
**CREDIT-REFUND-002** (registry-multiplier recomputation minting up to 5
credits per failure) — **FIXED**.

## Verified clean (auditable negative results)

Direct Python writes to `credits_remaining` (only auto-heal INSERT and
`ignore_duplicates` upsert — neither can overwrite) · Python read-modify-write
on the balance (removed) · `/api/credits-debug` (now zero writes) · RPC
exposure of the three 107 functions (`REVOKE`d, catalog-verified) ·
`user_credits` RLS (SELECT-only for `authenticated`) · unknown `feature_key`
(raises loudly, no silent free feature) · founder bypass (exact match on a
JWT-derived email against a mandatory env var) · GDPR deletion (does not touch
credits) · in-memory balance cache (none exists) · `consume()` inside a retry
decorator (none server-side) · copilot cross-charging (21 handlers traced,
clean) · cooldown TOCTOU (genuine atomic claim).

## Deferred items — consolidated justification

None of the deferred findings can **overdraw** or **mint** credits; they are
accounting-precision, over-charge, or hygiene issues. Each is recorded above
with file:line. They are deliberately not bundled into a certification change
where they would receive less scrutiny than they deserve:

- **SOA-007** (client retry double-charge) touches shared frontend dispatch used by every endpoint.
- **SOA-008** (multi_agent) needs a per-agent success accounting decision.
- **SOA-005** (`_increment_monthly_usage` RMW) needs a new RPC and therefore a new migration; its only reader is dead code today.
- **SOA-010/011/013/014/015/017/018** are precision/hygiene.

## Structural lesson

The credit system had **two of everything**: two `deduct_credit` definitions
(different tables, different sentinels), two sentinel conventions, duplicate
helper copies in `api.py`, and a test fixture that was a third hand-typed copy
of the SQL. Migration 107 collapsed the refund side to one implementation;
this operation did the same for consumption. Repo-wide tests now enforce
**exactly one definition per credit function**, so this class cannot silently
return.
