-- ═══════════════════════════════════════════════════════════════════════════
-- READ-ONLY PRODUCTION VERIFICATION — migrations 102 + 103 (+ credit-race body)
--
-- Vindex AI — Beta Gate Blocker Closure, 2026-08-08
--
-- PURPOSE: establish, from PostgreSQL system catalogs ONLY, whether the
-- protections declared in
--   migrations/102_lambda002_rpc_ownership_lockdown.sql
--   migrations/103_lambda002_profiles_column_lockdown.sql
-- are actually deployed in the live database.
--
-- SAFETY: every statement below is a SELECT against catalog/metadata. There
-- is no INSERT, UPDATE, DELETE, GRANT, REVOKE, CREATE or DROP anywhere in
-- this file. It cannot modify data, privileges, users, credits or schema.
--
-- HOW TO RUN: Supabase Dashboard → SQL Editor → New query.
-- Run each numbered QUERY block separately and copy back its full result.
--
-- WHY CATALOG INSPECTION AND NOT A BEHAVIOURAL TEST: a behavioural test
-- would require calling the protected functions or writing to profiles with
-- a non-service-role key -- i.e. a production write. Catalog inspection
-- answers the same question with zero mutation.
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 0 — PRECONDITION: the three Supabase roles must exist.
-- If any row is missing, every later has_*_privilege() call would error and
-- the whole verification is inconclusive rather than FAIL.
-- ───────────────────────────────────────────────────────────────────────────
SELECT rolname,
       rolsuper,
       rolbypassrls
FROM pg_roles
WHERE rolname IN ('anon', 'authenticated', 'service_role')
ORDER BY rolname;


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 1 — MIGRATION 102: execute privilege on all 5 locked-down functions.
--
-- Migration 102 does, for each of the 5 functions:
--     REVOKE ALL ... FROM PUBLIC;
--     REVOKE ALL ... FROM anon;
--     REVOKE ALL ... FROM authenticated;
--     GRANT EXECUTE ... TO service_role;
--
-- has_function_privilege() is used rather than raw ACL parsing because it
-- resolves PUBLIC grants and role inheritance -- it answers the actual
-- security question ("can this role execute this function?"), not just
-- "what literal ACL string is stored".
--
-- proacl_raw is included as primary evidence:
--   NULL  = privileges were NEVER explicitly modified on this function, i.e.
--           Postgres defaults apply, i.e. EXECUTE is granted to PUBLIC.
--           A NULL proacl on any of these 5 is by itself proof that
--           migration 102 was not applied to that function.
-- ───────────────────────────────────────────────────────────────────────────
WITH targets(sig) AS (
    VALUES ('public.deduct_credit(uuid)'),
           ('public.set_user_pro(text, boolean)'),
           ('public.deduct_n_credits(uuid, integer)'),
           ('public.get_activity_averages(uuid)'),
           ('public.get_next_broj_fakture(uuid)')
),
r AS (
    SELECT t.sig,
           to_regprocedure(t.sig) AS proc   -- NULL (no error) if absent
    FROM targets t
)
SELECT
    r.sig                                                        AS function_signature,
    (r.proc IS NOT NULL)                                         AS function_exists,
    p.prosecdef                                                  AS is_security_definer,
    pg_get_userbyid(p.proowner)                                  AS owner,
    p.proacl::text                                               AS proacl_raw,
    (p.proacl IS NOT NULL)                                       AS acl_explicitly_set,
    has_function_privilege('anon',          r.proc, 'EXECUTE')   AS anon_can_execute,
    has_function_privilege('authenticated', r.proc, 'EXECUTE')   AS authenticated_can_execute,
    has_function_privilege('service_role',  r.proc, 'EXECUTE')   AS service_role_can_execute,
    CASE
        WHEN r.proc IS NULL
            THEN 'INCONCLUSIVE - function not found'
        WHEN has_function_privilege('anon', r.proc, 'EXECUTE')
          OR has_function_privilege('authenticated', r.proc, 'EXECUTE')
            THEN 'FAIL - client role can still execute (102 NOT applied here)'
        WHEN NOT has_function_privilege('service_role', r.proc, 'EXECUTE')
            THEN 'FAIL - service_role lacks EXECUTE (backend would break)'
        ELSE 'PASS'
    END                                                          AS verdict
FROM r
LEFT JOIN pg_proc p ON p.oid = r.proc
ORDER BY r.sig;


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 2 — MIGRATION 103: per-column UPDATE privilege on public.profiles.
--
-- Migration 103 does:
--     REVOKE UPDATE ON public.profiles FROM authenticated;
--     REVOKE UPDATE ON public.profiles FROM anon;
--     GRANT UPDATE (full_name) ON public.profiles TO authenticated;
--
-- This is the DECISIVE query. The question is NOT "is RLS enabled" -- RLS
-- scopes ROWS, never COLUMNS, which is precisely why migration 103 exists.
-- The question is: can an ordinary client role still write the privilege
-- columns (is_pro / plan / trial_kraj) on its own row?
--
-- Every column is enumerated rather than hard-coding names, so a column
-- added after the migration was written cannot hide from this check.
-- ───────────────────────────────────────────────────────────────────────────
SELECT
    c.column_name,
    has_column_privilege('authenticated', 'public.profiles', c.column_name, 'UPDATE') AS authenticated_can_update,
    has_column_privilege('anon',          'public.profiles', c.column_name, 'UPDATE') AS anon_can_update,
    has_column_privilege('service_role',  'public.profiles', c.column_name, 'UPDATE') AS service_role_can_update
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name   = 'profiles'
ORDER BY c.column_name;


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 3 — MIGRATION 103: single-line verdict.
--
-- NOTE ON A DELIBERATE SUBTLETY: after migration 103 is correctly applied,
-- has_table_privilege('authenticated','public.profiles','UPDATE') is still
-- TRUE, because the role retains UPDATE on the single column full_name.
-- Table-level UPDATE being TRUE is therefore NOT evidence of failure and
-- must not be read as such. Only the per-column result decides.
-- ───────────────────────────────────────────────────────────────────────────
SELECT
    has_table_privilege('authenticated', 'public.profiles', 'UPDATE')                  AS authenticated_table_update_any_column,
    has_column_privilege('authenticated', 'public.profiles', 'full_name', 'UPDATE')    AS can_update_full_name_expected_true,
    has_column_privilege('authenticated', 'public.profiles', 'is_pro',    'UPDATE')    AS can_update_is_pro_expected_false,
    (SELECT count(*)
       FROM information_schema.columns c
      WHERE c.table_schema = 'public'
        AND c.table_name   = 'profiles'
        AND c.column_name <> 'full_name'
        AND has_column_privilege('authenticated', 'public.profiles', c.column_name, 'UPDATE')
    )                                                                                  AS other_writable_columns_expected_0,
    CASE
        WHEN to_regclass('public.profiles') IS NULL
            THEN 'INCONCLUSIVE - table public.profiles not found'
        WHEN has_column_privilege('authenticated', 'public.profiles', 'is_pro', 'UPDATE')
            THEN 'FAIL - authenticated can still write is_pro (103 NOT applied): free PRO via devtools'
        WHEN NOT has_column_privilege('authenticated', 'public.profiles', 'full_name', 'UPDATE')
            THEN 'FAIL - authenticated cannot write full_name (name change in Settings would break)'
        WHEN (SELECT count(*)
                FROM information_schema.columns c
               WHERE c.table_schema = 'public'
                 AND c.table_name   = 'profiles'
                 AND c.column_name <> 'full_name'
                 AND has_column_privilege('authenticated', 'public.profiles', c.column_name, 'UPDATE')) > 0
            THEN 'FAIL - authenticated can write columns other than full_name (see QUERY 2 for which)'
        ELSE 'PASS'
    END                                                                                AS verdict;


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 4 — CONTEXT ONLY (not decisive): RLS state + policies on profiles.
-- Included so the row-scoping layer can be seen alongside the column-scoping
-- layer. A correct result here does NOT substitute for QUERY 2/3.
-- ───────────────────────────────────────────────────────────────────────────
SELECT
    c.relname               AS table_name,
    c.relrowsecurity        AS rls_enabled,
    c.relforcerowsecurity   AS rls_forced
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'profiles';

SELECT policyname, cmd, roles, qual, with_check
FROM pg_policies
WHERE schemaname = 'public' AND tablename = 'profiles'
ORDER BY policyname;


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 5 — CREDIT-RACE BODY CHECK (migrations/smart_contract_analyses.sql).
--
-- In scope because it is the credit-lockdown half of the same question and
-- is the single remaining CONDITIONAL-GO blocker from the Final Beta Gate
-- certificate. Migration 102 governs WHO may execute deduct_n_credits;
-- this governs whether the deployed BODY still has the balance-floor bug.
--
-- Expected (fixed) body contains:   credits_remaining >= p_n
-- Old (vulnerable) body contains:   GREATEST(0, credits_remaining - p_n)
-- ───────────────────────────────────────────────────────────────────────────
SELECT
    CASE
        WHEN to_regprocedure('public.deduct_n_credits(uuid, integer)') IS NULL
            THEN 'INCONCLUSIVE - function not found'
        WHEN pg_get_functiondef(to_regprocedure('public.deduct_n_credits(uuid, integer)')) LIKE '%credits_remaining >= p_n%'
            THEN 'PASS - balance guard present (credit-race fix IS deployed)'
        WHEN pg_get_functiondef(to_regprocedure('public.deduct_n_credits(uuid, integer)')) LIKE '%GREATEST(0, credits_remaining - p_n)%'
            THEN 'FAIL - old unguarded body still deployed (credit race is LIVE)'
        ELSE 'INCONCLUSIVE - body differs from both known versions, inspect below'
    END AS credit_race_verdict,
    pg_get_functiondef(to_regprocedure('public.deduct_n_credits(uuid, integer)')) AS deployed_function_body;


-- ───────────────────────────────────────────────────────────────────────────
-- QUERY 6 — Same body check for the single-credit sibling, for completeness.
-- deduct_credit has always had its WHERE guard (supabase_setup.sql); this
-- confirms the deployed copy still matches that, i.e. nothing regressed it.
-- Expected: body contains  AND credits_remaining > 0
-- ───────────────────────────────────────────────────────────────────────────
SELECT
    CASE
        WHEN to_regprocedure('public.deduct_credit(uuid)') IS NULL
            THEN 'INCONCLUSIVE - function not found'
        WHEN pg_get_functiondef(to_regprocedure('public.deduct_credit(uuid)')) LIKE '%credits_remaining > 0%'
            THEN 'PASS - single-credit guard present'
        ELSE 'FAIL - expected balance guard missing, inspect body below'
    END AS deduct_credit_verdict,
    pg_get_functiondef(to_regprocedure('public.deduct_credit(uuid)')) AS deployed_function_body;
