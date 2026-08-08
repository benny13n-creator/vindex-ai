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


-- ═══════════════════════════════════════════════════════════════════════════
-- QUERY A — CONSOLIDATED SINGLE-RUN VERDICT  ◄── RUN THIS ONE FIRST
--
-- The Supabase SQL Editor displays only the LAST statement's result set when
-- a multi-statement file is run, so the individual blocks further down were
-- silently discarded on the first attempt. This block returns every check as
-- rows of ONE result set: run it alone, paste the whole table back.
-- Still 100% read-only.
-- ═══════════════════════════════════════════════════════════════════════════
WITH fn(sig) AS (
    VALUES ('public.deduct_credit(uuid)'),
           ('public.set_user_pro(text, boolean)'),
           ('public.deduct_n_credits(uuid, integer)'),
           ('public.get_activity_averages(uuid)'),
           ('public.get_next_broj_fakture(uuid)'),
           -- added by migration 107; before it, refund_one_credit did not
           -- exist at all and refund_n_credits had never been conceived, so
           -- both rows read INCONCLUSIVE until 107 is applied.
           ('public.refund_n_credits(uuid, integer)'),
           ('public.refund_one_credit(uuid)')
),
fnres AS (
    SELECT f.sig, to_regprocedure(f.sig) AS proc FROM fn f
),
col(name, upd) AS (
    SELECT c.column_name,
           has_column_privilege('authenticated', 'public.profiles', c.column_name, 'UPDATE')
    FROM information_schema.columns c
    WHERE c.table_schema = 'public' AND c.table_name = 'profiles'
)
SELECT '0 · roles exist' AS check_id,
       'anon / authenticated / service_role' AS target,
       CASE WHEN (SELECT count(*) FROM pg_roles
                  WHERE rolname IN ('anon','authenticated','service_role')) = 3
            THEN 'PASS' ELSE 'INCONCLUSIVE' END AS verdict,
       'found ' || (SELECT count(*) FROM pg_roles
                    WHERE rolname IN ('anon','authenticated','service_role'))::text || '/3' AS evidence

UNION ALL
SELECT '1 · mig102 privilege',
       r.sig,
       CASE
         WHEN r.proc IS NULL THEN 'INCONCLUSIVE - function not found'
         WHEN has_function_privilege('anon', r.proc, 'EXECUTE')
           OR has_function_privilege('authenticated', r.proc, 'EXECUTE')
              THEN 'FAIL - client role can still execute'
         WHEN NOT has_function_privilege('service_role', r.proc, 'EXECUTE')
              THEN 'FAIL - service_role lacks EXECUTE'
         ELSE 'PASS'
       END,
       'proacl=' || COALESCE((SELECT p.proacl::text FROM pg_proc p WHERE p.oid = r.proc), 'NULL')
         || ' | anon=' || COALESCE(has_function_privilege('anon', r.proc, 'EXECUTE')::text, '?')
         || ' auth='   || COALESCE(has_function_privilege('authenticated', r.proc, 'EXECUTE')::text, '?')
         || ' svc='    || COALESCE(has_function_privilege('service_role', r.proc, 'EXECUTE')::text, '?')
FROM fnres r

UNION ALL
SELECT '2 · mig103 columns',
       'public.profiles UPDATE grants for authenticated',
       CASE
         WHEN to_regclass('public.profiles') IS NULL THEN 'INCONCLUSIVE - table not found'
         WHEN COALESCE((SELECT upd FROM col WHERE name = 'is_pro'), FALSE)
              THEN 'FAIL - authenticated can write is_pro (free PRO reachable)'
         WHEN NOT COALESCE((SELECT upd FROM col WHERE name = 'full_name'), FALSE)
              THEN 'FAIL - authenticated cannot write full_name (Settings would break)'
         WHEN (SELECT count(*) FROM col WHERE upd AND name <> 'full_name') > 0
              THEN 'FAIL - writable columns beyond full_name'
         ELSE 'PASS'
       END,
       'authenticated-writable: '
         || COALESCE((SELECT string_agg(name, ', ' ORDER BY name) FROM col WHERE upd), '(none)')

UNION ALL
SELECT '3 · F5 credit-race body',
       'public.deduct_n_credits(uuid, integer)',
       CASE
         WHEN to_regprocedure('public.deduct_n_credits(uuid, integer)') IS NULL
              THEN 'INCONCLUSIVE - function not found'
         WHEN pg_get_functiondef(to_regprocedure('public.deduct_n_credits(uuid, integer)'))
              LIKE '%credits_remaining >= p_n%'
              THEN 'PASS - balance guard deployed'
         WHEN pg_get_functiondef(to_regprocedure('public.deduct_n_credits(uuid, integer)'))
              LIKE '%GREATEST(0, credits_remaining - p_n)%'
              THEN 'FAIL - old unguarded body still live (credit race OPEN)'
         ELSE 'INCONCLUSIVE - body matches neither known version'
       END,
       left(replace(COALESCE(
              pg_get_functiondef(to_regprocedure('public.deduct_n_credits(uuid, integer)')),
              'n/a'), E'\n', ' '), 600)

UNION ALL
SELECT '3b · refund atomicity (mig 107)',
       'public.refund_n_credits(uuid, integer)',
       CASE
         WHEN to_regprocedure('public.refund_n_credits(uuid, integer)') IS NULL
              THEN 'FAIL - refund_n_credits missing (migration 107 NOT applied); refunds race'
         WHEN pg_get_functiondef(to_regprocedure('public.refund_n_credits(uuid, integer)'))
              LIKE '%credits_remaining + p_n%'
              THEN 'PASS - atomic single-statement refund deployed'
         ELSE 'INCONCLUSIVE - body differs from expected'
       END,
       CASE WHEN to_regprocedure('public.refund_one_credit(uuid)') IS NULL
            THEN 'refund_one_credit: MISSING (shared/deps.py calls it on every refund)'
            ELSE 'refund_one_credit: present' END

UNION ALL
SELECT '4 · profiles RLS (context only)',
       'public.profiles',
       CASE WHEN (SELECT c.relrowsecurity FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname='public' AND c.relname='profiles')
            THEN 'INFO - RLS enabled' ELSE 'INFO - RLS disabled' END,
       'policies: ' || COALESCE((SELECT string_agg(policyname || '/' || cmd, ', ' ORDER BY policyname)
                                 FROM pg_policies
                                 WHERE schemaname='public' AND tablename='profiles'), '(none)')
ORDER BY 1, 2;


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
