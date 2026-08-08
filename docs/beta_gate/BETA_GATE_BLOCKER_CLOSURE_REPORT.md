# BETA GATE — BLOCKER CLOSURE REPORT

**Date:** 2026-08-08
**Operation:** Beta Gate Blocker Closure & Final Re-Certification
**Method:** read-only PostgreSQL catalog verification against the live
production database, executed by the founder in the Supabase SQL Editor.
**Verification script:** `docs/beta_gate/VERIFY_MIGRATIONS_102_103_READONLY.sql`
(QUERY A — consolidated single-run verdict)

**No production write of any kind was performed.** A live behavioural test
(throwaway account + real `deduct_n_credits` call) was proposed and
explicitly rejected by the founder; the catalog-inspection path was used
instead. Every statement executed was a `SELECT` against `pg_roles`,
`pg_proc`, `pg_class`, `pg_policies` and `information_schema`.

---

## 1. Headline

Two of the three outstanding database-layer questions are now **independently
verified applied** for the first time in this project's history. The third —
the Final Beta Gate's own single CONDITIONAL-GO blocker — is now
**verified NOT applied**, which converts a previously assumed-pending item
into a **confirmed live production vulnerability**.

| Item | Prior status | Verified status |
|---|---|---|
| Migration 102 (RPC ownership lockdown) | founder-reported applied, never verified | **VERIFIED APPLIED** |
| Migration 103 (profiles column lockdown) | founder-reported applied, never verified | **VERIFIED APPLIED** |
| `deduct_n_credits` balance guard (F5) | assumed pending founder action | **VERIFIED NOT APPLIED — race is LIVE** |

---

## 2. Migration 102 — VERIFIED APPLIED

All five functions returned identical, unambiguous ACL evidence:

```
proacl = {postgres=X/postgres,service_role=X/postgres}
anon=false  authenticated=false  service_role=true
```

| Function | Verdict |
|---|---|
| `public.deduct_credit(uuid)` | PASS |
| `public.set_user_pro(text, boolean)` | PASS |
| `public.deduct_n_credits(uuid, integer)` | PASS |
| `public.get_activity_averages(uuid)` | PASS |
| `public.get_next_broj_fakture(uuid)` | PASS |

**Why this is conclusive.** The stored ACL contains exactly two grantees —
the owner (`postgres`) and `service_role`. There is no bare `=X/postgres`
entry, which is how Postgres represents a grant to `PUBLIC`. Had migration
102 never run, `proacl` would have been `NULL` (defaults apply → `PUBLIC`
holds `EXECUTE`), and `has_function_privilege('authenticated', …)` would
have returned `true`. Both independent signals agree.

**Consequence:** the two CRITICAL exploits this migration existed to close —
cross-account credit drain via `deduct_credit`, and free permanent PRO via
`set_user_pro` — are confirmed closed at the database layer. Neither is
callable by `anon` or `authenticated` through PostgREST.

## 3. Migration 103 — VERIFIED APPLIED

```
authenticated-writable columns on public.profiles: full_name
```

Exactly one column. `is_pro`, `plan`, `trial_kraj` and every other column
are not writable by `authenticated`, and no column is writable by `anon`.

**Why this is conclusive.** This is a column-level `has_column_privilege`
result, enumerated across every column that actually exists on the table
rather than a hard-coded list — so a column added after the migration was
authored could not have hidden from the check. The devtools attack the
migration was written to stop
(`supabase.from('profiles').update({is_pro:true})`) is now rejected at the
GRANT layer, which is the only layer that can express column scope. RLS was
never the control here and its state was not treated as evidence.

**Note (informational, not a blocker):** `public.profiles` carries
duplicated/overlapping policies —
`Korisnici azuriraju sopstveni profil/UPDATE` and
`Korisnici ažuriraju sopstveni profil/UPDATE` (identical but for
diacritics), plus three SELECT policies
(`Korisnici citaju…`, `Korisnici čitaju…`, `profiles_select_own`). Multiple
permissive policies OR together in Postgres, so this widens nothing given
the column GRANT above is the real control, but it is schema drift worth a
future cleanup pass. Not fixed here (out of this operation's scope, and it
would be a production write).

## 4. F5 credit-race — VERIFIED NOT APPLIED (blocker confirmed live)

Deployed body of `public.deduct_n_credits(uuid, integer)`:

```sql
UPDATE public.user_credits
  SET credits_remaining = GREATEST(0, credits_remaining - p_n)
WHERE user_id = p_user_id
RETURNING credits_remaining INTO new_balance;
RETURN COALESCE(new_balance, 0);
```

This is the **original, unguarded version**. It has neither the
`AND credits_remaining >= p_n` predicate nor the `RETURN -1` sentinel that
`migrations/smart_contract_analyses.sql` introduces.

### 4.1 Exploitability, restated against verified production state

The `UPDATE` carries no balance predicate, so it succeeds unconditionally
and floors at zero. Under the app's real 4-gunicorn-worker topology, two or
more concurrent requests from the same user at or near exhaustion each pass
`UsageService.consume`'s pre-check, each call the RPC, and each receive a
non-negative value. Every one of them is treated as a successful charge.
The user receives N multiplier-priced AI operations while the balance can
only ever fall to 0. The higher the multiplier (strategija = 6×, multi_agent,
strategy_simulator, digital_twin, smart-contract analyzer), the larger the
uncharged spend per burst.

### 4.2 New finding — the shipped Python fix is currently INERT

`shared/deps.py::_deduct_n_credits` and `shared/usage.py::UsageService.consume`
were rewritten during Final Beta Gate to depend on the **new** RPC contract:
a `-1` return means "not charged, insufficient balance", which
`consume()` converts into HTTP 402.

Against the **deployed old body**, `-1` is unreachable: the function returns
`COALESCE(new_balance, 0)`, which is always ≥ 0 — including when the row is
missing entirely. Therefore:

- `_deduct_n_credits` always sees `new_balance >= 0`, so it always increments monthly usage and returns a non-negative value;
- `consume()`'s `if preostalo < 0` branch can never fire;
- the 402 protection never triggers.

**This introduced no regression** — behaviour is byte-for-byte equivalent to
the pre-Beta-Gate state — but it means the application-layer half of the fix
provides **zero** protection until the migration runs. The two halves are
only meaningful together. This is exactly why the Final Beta Gate
certificate refused to call F5 closed, and that refusal is now vindicated by
direct evidence rather than caution.

### 4.3 Why this was not fixed in this operation

The fix is a production write (`CREATE OR REPLACE FUNCTION`), which the
founder explicitly prohibited for this operation. No safe code-only
workaround was implemented, deliberately:

- PostgREST cannot express an atomic `SET col = col - n` guarded decrement, so an equivalent guarantee cannot be built from `.update()` calls;
- the one available atomic primitive, `deduct_credit`, decrements by exactly 1 and returns an ambiguous `0` at the boundary, so an N-iteration loop would introduce partial-charge and refund-failure paths of its own;
- rewriting the billing charge path — the most financially sensitive code in the product — to work around a defect whose real fix is a 10-line idempotent SQL paste would add materially more risk than it removes.

The correct action is a single founder-run migration, documented in §6.

## 5. Gate Answers

| Question | Answer | Basis |
|---|---|---|
| **A.** Is the credit race technically closed? | **NO** | deployed body has no balance predicate (§4) |
| **B.** Is the production migration independently verified? | **YES — verified NOT applied** | `pg_get_functiondef` output (§4) |
| **C.** Did the adversarial concurrency test pass? | **NOT RUN** | blocked upstream: a concurrency proof against production would require live writes, which are prohibited; against a mock it would prove only the contract, which the existing suite already covers |
| **D.** Did the second-order audit find a new blocker? | **YES — one** | the shipped Python fix is inert against the deployed RPC (§4.2) |
| **E.** Does full regression pass? | **YES (unchanged)** | 3,443 passed / 1 skipped / 0 failed, twice, at commit `bf7fede`; no code changed in this operation |
| **F.** Any CRITICAL/HIGH blocker preventing closed beta? | **YES — one CRITICAL** | F5, verified live |

## 6. Required Action — exact and complete

Run in Supabase Dashboard → SQL Editor. Idempotent, and the only statement
needed (the table half of `smart_contract_analyses.sql` is already applied):

```sql
CREATE OR REPLACE FUNCTION public.deduct_n_credits(p_user_id UUID, p_n INTEGER)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  new_balance INTEGER;
BEGIN
  UPDATE public.user_credits
    SET credits_remaining = credits_remaining - p_n
  WHERE user_id = p_user_id
    AND credits_remaining >= p_n
  RETURNING credits_remaining INTO new_balance;

  IF NOT FOUND THEN
    RETURN -1;
  END IF;

  RETURN new_balance;
END;
$$;

GRANT EXECUTE ON FUNCTION public.deduct_n_credits(UUID, INTEGER) TO service_role;
```

**`CREATE OR REPLACE FUNCTION` does not reset privileges**, so the verified
migration-102 lockdown on this function survives it. The trailing `GRANT` is
a no-op re-assertion, harmless and idempotent.

**Then re-run QUERY A** from
`docs/beta_gate/VERIFY_MIGRATIONS_102_103_READONLY.sql`. Required results:

- row `3 · F5 credit-race body` → `PASS - balance guard deployed`
- all five `1 · mig102 privilege` rows → still `PASS` (proves the `CREATE OR REPLACE` did not silently reopen execute privileges)

## 7. Recommended follow-up (NOT implemented — requires founder approval)

A startup or health-check probe that detects application-code / deployed-RPC
contract drift. The entire failure mode in §4.2 is invisible to the test
suite by construction: the suite mocks the RPC, so it validates the contract
the code expects, never the contract the database actually offers. A
read-only `pg_get_functiondef`-style assertion (or a probe call with a
known-insufficient amount against a dedicated fixture row) surfaced on the
admin health endpoint would have caught this on day one. Deliberately not
built in this operation — it is new capability, not evidence gathering.

## 8. Final Status

```
Migration 102                  VERIFIED APPLIED
Migration 103                  VERIFIED APPLIED
F5 deduct_n_credits guard      VERIFIED NOT APPLIED — credit race LIVE
Full regression                PASS (3,443 / 1 skipped / 0 failed, x2, unchanged)

BETA GATE STATUS               NO-GO
Reason                         one CRITICAL production blocker, confirmed by
                               direct catalog evidence, closed by one
                               founder-run SQL statement (§6)
```

This is a **narrower and better-evidenced** NO-GO than the previous
CONDITIONAL GO, not a worse outcome: two long-standing unverified security
claims were converted to verified-good, and the one remaining item moved
from "assumed pending" to "proven open with an exact, tested remedy".
