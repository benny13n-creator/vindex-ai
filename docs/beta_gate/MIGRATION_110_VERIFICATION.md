# Migration 110 — APPLIED + VERIFIED (2026-08-09)

Founder ran `migrations/110_rls_lockdown_idempotent.sql`; all four read-only
verification queries returned the expected result. Recorded here because the
preceding attempt (109) failed, which left the applied state ambiguous — this
document is what resolves it. The end state is what counts, and this is it.

## Q1 — GRANT layer on feature_usage (the P0)

| auth_select | auth_update | auth_delete | anon_update |
|---|---|---|---|
| true | **false** | **false** | **false** |

The browser-console attack — `_supa.from('feature_usage').delete().eq('user_id', myUid)`
with the anon key that ships in `static/vindex.js` — now fails at the GRANT
layer, before RLS is consulted at all. `copilot_ambient` (200/day) and
`morning_briefing` (5/day), both priced at zero credits and both protected by
nothing except this counter, can no longer be made free and unlimited.

`auth_select = true` is intended: a user must still see their own usage.

## Q2 — policies

| tablename | policyname | roles | cmd |
|---|---|---|---|
| case_benchmarks | service_role_case_benchmarks | {service_role} | ALL |
| feature_usage | feature_usage_self_read | {public} | SELECT |
| feature_usage | feature_usage_service_role | {public} | ALL |
| ingest_jobs | service_role_ingest_jobs | {service_role} | ALL |
| zakoni_monitoring | service_role_zakoni_monitoring | {service_role} | ALL |

`ingest_jobs` is now scoped `TO service_role` — B-02(a) closed.

### The second feature_usage policy: checked, and clean

`feature_usage_service_role` shows `roles = {public}` and `cmd = ALL`, which is
the same shape as the `ingest_jobs` defect this migration fixed. Permissive
policies OR together, so a `USING (true)` there would have made
`feature_usage_self_read` decorative and exposed every user's usage data to
every other user.

It is not `USING (true)`. Its qualifier is:

    (auth.role() = 'service_role'::text)

For an authenticated caller `auth.role()` returns `'authenticated'`, the policy
evaluates false and contributes no rows, so the union is exactly what
`feature_usage_self_read` allows: the caller's own rows. `{public}` here means
only that the policy is *evaluated* for everyone; the predicate does the
scoping, and the role claim sits inside a signed JWT the user cannot forge.

Tenant isolation holds. Recorded so the next audit does not re-raise it.

## Q3 — RLS enabled

| relname | relrowsecurity |
|---|---|
| case_benchmarks | true |
| feature_usage | true |
| ingest_jobs | true |
| zakoni_monitoring | true |

`case_benchmarks` and `zakoni_monitoring` were the only two tables in the whole
schema created without RLS. `case_benchmarks` holds every opted-in firm's
outcome/value data and feeds the cross-firm benchmark pool — it was readable and
poisonable by an unauthenticated visitor. B-02(b) closed.

That `zakoni_monitoring`, the last entry in the migration's loop, has RLS also
proves the `to_regclass` guard worked: it skipped the missing table instead of
aborting the run, which is precisely what 109 did not do.

## Q4 — SECURITY DEFINER functions without a fixed search_path

Zero rows. B-06 closed.

## Not done, and why

`discovered_bilteni` was skipped: it does not exist in this database. Migration
017 created it and was evidently never applied here — a separate finding, and
the reason 109 aborted. Nothing in the application reads that table today.
