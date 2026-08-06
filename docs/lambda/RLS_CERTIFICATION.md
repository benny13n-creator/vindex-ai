# RLS Certification — Program Lambda, Certification 002

## The one fact that reframes this whole certification

`shared/deps.py::_get_supa()` — the Supabase client used by essentially the entire backend — authenticates
with the **service role key**, which bypasses Row-Level Security entirely. This has been a known architectural
fact since `SEC-004` (2026-07-23/24). It means "RLS certification" for this app cannot mean "is RLS correctly
configured" — 197 `CREATE POLICY` statements were sampled across 40+ migration files and essentially all of
them are individually correct — it has to mean **"is the real enforcement layer complete."** The real
enforcement layer is Python `.eq("user_id", uid)` filtering, audited endpoint-by-endpoint in `IDOR_MATRIX.md`.
This report covers the two places RLS is NOT decorative: the frontend's direct-to-Supabase calls, and
`SECURITY DEFINER` RPC functions (which run with the function owner's privileges regardless of who calls
them or through what client).

## Result: 2 CRITICAL, directly exploitable database-layer bypasses found

### `deduct_credit(p_user_id UUID)` — CONFIRMED VULNERABLE

`supabase_setup.sql:117-148`. `SECURITY DEFINER`. Line 148 explicitly runs
`GRANT EXECUTE ON FUNCTION public.deduct_credit(UUID) TO authenticated;`. The function body trusts
`p_user_id` with no `p_user_id = auth.uid()` check. Any authenticated user can call
`rpc("deduct_credit", {"p_user_id": "<victim uuid>"})` directly against PostgREST — no FastAPI route, no
rate limit, no `require_credits` guard involved — and drain any other user's credits to 0. **Status: FIXED**
via `migrations/102_lambda002_rpc_ownership_lockdown.sql` (not yet applied to live Supabase — see below).

### `set_user_pro(p_email TEXT, p_is_pro BOOLEAN)` — CONFIRMED VULNERABLE

`migrations/061_fix_missing_profiles_columns.sql:66-74`. `SECURITY DEFINER`. Repo-wide grep confirms **zero**
`GRANT`/`REVOKE` statement was ever written for this function — Postgres's own default is `EXECUTE` granted
to `PUBLIC` at creation time, which Supabase's `authenticated`/`anon` roles inherit. Written as a founder-only
SQL-Editor helper (its own comment: "Primer upotrebe: SELECT set_user_pro(...)") but nothing in SQL enforced
that. Any authenticated user could call `rpc("set_user_pro", {"p_email": "<own email>", "p_is_pro": true})`
for a free, permanent PRO upgrade with zero payment — a monetary-impact bug, not just a data-isolation one —
or strip a victim's PRO status by supplying their email with `p_is_pro: false`. **Status: FIXED** via the
same migration (not yet applied — see below).

### 3 more functions, same missing-`REVOKE` pattern, defense-in-depth only

`deduct_n_credits(p_user_id, p_n)` (`migrations/smart_contract_analyses.sql:56-72`),
`get_activity_averages(p_user_id)` (`044_anomaly_detection.sql:82-104`),
`get_next_broj_fakture(p_user_id)` (`003_billing.sql:107-119`, confirmed unused by the Python codebase via
grep — a dead but still-live RPC). None had an explicit `GRANT TO authenticated`, so none is a confirmed live
exploit the way the first two are, but none had a `REVOKE FROM PUBLIC` either — under plain Postgres defaults
this is also `PUBLIC`-executable. Locked down in the same migration as defense-in-depth.

## Why this is a "declared control ≠ enforced control" gap, not a regression

`migrations/073_intake_foundations.sql:344-345` contains this exact comment, written by a prior sprint:
*"Svi RPC-ovi pozivaju samo backend workeri (service_role ključ) — isti obrazac kao
deduct_credit()/deduct_n_credits(). Nikad izloženo anon/authenticated."* — a later author **believed**
`deduct_credit`/`deduct_n_credits` already followed the safe REVOKE-from-PUBLIC pattern that migration 073
itself correctly applies. They didn't. This is direct in-repo evidence that the safe pattern was known and
intentionally applied going forward (see also `091_event_bus_atomic_claim.sql`, `092_finalize_atomic_claim.sql`,
`095_intake_bulletproofing.sql` — all correctly locked down), but never retrofitted onto the two earliest,
highest-impact functions.

## Everything else: SAFE and, where it matters, load-bearing

- **`static/vindex.js`** is the only non-service-role Supabase client in the codebase (browser, end-user JWT).
  It touches 3 tables directly: `profiles` (SAFE, `profiles_select_own`), `reported_errors` (SAFE,
  insert-own policy), and — critically — **`conversations`**, where `loadChatHistory()` filters only by
  `session_id`, relying entirely on the `conversations_own` policy (`auth.uid()=user_id`) to prevent
  cross-user chat-history reads via a guessed session id. This policy is correctly written and **is the sole
  guard** for this one table — the single place in the whole app where RLS is genuinely, not decoratively,
  load-bearing.
- **19 other `SECURITY DEFINER`/RPC functions** examined: 7 correctly locked down already (the intake/event-bus
  atomic-claim RPCs), 7 are trigger-only (never called via `.rpc()`, no caller-supplied identity parameter to
  exploit), 5 covered above.
- **197 RLS policies sampled** across owner-only, firm-shared-read, service-role-only/deny-all, and
  ownership-join patterns — no malformed or inverted condition found in the sample. Individually correct;
  irrelevant to the real request path for every table the backend touches via the service-role client.

## Storage RLS: cannot be certified from this repository

No `CREATE POLICY ON storage.objects` (or any `storage.*` policy) exists anywhere in the repo. Either bucket
policies were configured manually in the Supabase Dashboard (invisible to a code audit) or none exist and
the 3 real buckets rely solely on the backend's own ownership checks (confirmed sufficient — see
`STORAGE_SECURITY_REPORT.md`). This is a genuine audit blind spot, not a finding either way — flagged for the
founder to confirm live in the Dashboard.

## Outstanding action

`migrations/102_lambda002_rpc_ownership_lockdown.sql` exists on disk and is **not yet applied to live
Supabase** — per this project's standing rule, migrations are run by the founder, never auto-executed. Until
it runs, `deduct_credit` and `set_user_pro` remain exploitable in production exactly as described above. This
is the single highest-priority action item from the entire sprint.
