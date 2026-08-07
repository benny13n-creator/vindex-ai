# SECURITY_CERTIFICATION — Program Lambda, Certification 008

Covers Team 2 (Security & RLS), Team 3 (Ownership/IDOR). Attacked RLS, ownership, API/RPC security, cache
tenant-isolation, AI-context isolation, upload security, billing/credit security — assuming an attacker who
knows the system.

## CRITICAL — re-confirmed, not newly discovered, FOUNDER ACTION REQUIRED

`deduct_credit`/`set_user_pro` SECURITY DEFINER RPCs (`supabase_setup.sql:117-148`,
`migrations/061_fix_missing_profiles_columns.sql:66-74`) have no ownership check and are callable by any
authenticated user — a live credit-drain / free-permanent-PRO exploit. Same for `profiles`' own UPDATE RLS
policy (no column scope). **Fixes were already written in Certification 002**
(`migrations/102_lambda002_rpc_ownership_lockdown.sql`, `103_lambda002_profiles_column_lockdown.sql`) — this
certification independently re-confirmed, via 3 separate teams (Security, Ownership, Migration/Schema Drift)
and adversarial Red Team review, that they are **still not applied to production**. This is not a code
fix — it requires the founder to run these 2 migrations. See `LAMBDA008-SEC-001` in the Debt Register.

## HIGH — fixed this sprint

**`routers/dokument.py`'s session-based document endpoints** (`/pitanje`, `/klasifikuj-sesija`) accepted a
client-supplied `namespace_prefix` and `session_id`, validating only that the Pinecone namespace exists and
hasn't expired (`uploaded_doc/session.py::validate_session`) — never checking that the requesting user
actually owns the referenced case. `pred_*` namespaces (permanent case documents, as opposed to `tmp_*`
temporary upload sessions) **never expire**, per the module's own docstring — meaning a leaked or guessed
`predmet_id` gave permanent, not just session-window, cross-tenant read access to another firm's documents.
Fixed via a new `_verify_pred_namespace_ownership` check, raising 404 (not 403, to avoid confirming another
firm's case exists) before any document content is fetched.

## LOW — fixed this sprint

**`routers/billing.py::billing_po_klijentu`** had no ownership filter on its initial `predmet_klijenti`
lookup by `klijent_id` — every downstream query WAS correctly filtered by `user_id`, so this was not
independently exploitable (worst case: a caller learns "this klijent_id has 0 of my invoices" vs. an
equivalent 404). Fixed as defense-in-depth: an unowned `klijent_id` now short-circuits to an empty result
before any further query runs.

## Full re-verification — 0 new exploitable IDOR findings out of 136 endpoints swept

Every path-parameterized endpoint across 60 router files plus 12 core `api.py` predmet endpoints was
checked for an explicit `.eq("user_id", uid)` (or equivalent) filter before mutation/read. All confirmed
compliant, or intentionally firm-scoped (multi-member-firm design, not a bug), or admin-gated. **No case
found of an app-layer endpoint relying on RLS-only protection while using the service-role client that
bypasses it** — the codebase consistently applies explicit app-layer ownership filters.

## Re-verified still fixed (no regression)

- `BL-001` (`GET /api/zadaci/predmet/{id}` ownership check) — present.
- `ask_agent`'s cross-tenant AI-context cache leak fix (Certification 003) — all 4 cache write sites
  checked, all consistently gated.
- `entities/{entity_id}/correct` IDOR fix (Certification 002) — full ownership chain implemented.
- `predmet_confirm_links` cross-tenant client-linking fix (Certification 002) — present.

## Still open, tracked, not re-litigated this sprint

- `SEC-039` — same class of cross-tenant exposure as the `dokument.py` fix above, on a different endpoint
  set (`IDOR_MATRIX.md:52`), re-confirmed present, not fixed this sprint (outside this sprint's fix budget
  after the CRITICAL and HIGH items above).
- `LAMBDA-OWN-001` — Clio webhook trusts an attacker-supplied `vindex_user_id` in the payload, shared secret
  is platform-wide, CREATE-only impact. Unchanged.
- `LAMBDA-004` — no systematic automated IDOR regression suite exists; this sprint's 136-endpoint sweep is a
  point-in-time manual result, not a durable guarantee, per the same standing gap prior certifications named.

**Verdict**: 2 new findings this sprint (1 HIGH, 1 LOW), both fixed. 1 CRITICAL item re-confirmed still
live in production, requiring founder action before beta. Platform's ownership/tenant-isolation foundation
otherwise held up under a full independent re-sweep.
