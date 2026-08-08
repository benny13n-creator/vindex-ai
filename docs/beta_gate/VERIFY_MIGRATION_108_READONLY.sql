-- ═══════════════════════════════════════════════════════════════════════════
-- READ-ONLY verification of migration 108 (atomic usage counters).
-- Nothing here writes. No INSERT/UPDATE/DELETE/ALTER/CREATE/DROP.
-- Paste the output back.
--
-- WHY THIS IS STILL NEEDED
-- Existence and exact signatures are already PROVEN from outside the database:
-- a probe with correct argument names and a deliberately invalid UUID resolves
-- the function and then aborts at argument casting (SQLSTATE 22P02) before any
-- function body runs. Positive control deduct_n_credits -> 22P02; negative
-- control (an invented name) -> PGRST202. Both migration-108 functions
-- answered 22P02, and migrations/108_atomic_usage_counters.sql is the only
-- file in the repo that defines either of them.
--
-- What that CANNOT show is the function BODY. Signature identity does not
-- prove the shipped atomic implementation is what is installed. Q1/Q2 below
-- close that, and only they can.
-- ═══════════════════════════════════════════════════════════════════════════

-- Q1 ── The two function definitions, verbatim.
-- EXPECT increment_feature_usage: a single INSERT ... ON CONFLICT
--        (user_id, feature_key, dan) DO UPDATE ... WHERE p_dnevni_limit IS NULL
--        OR broj_koriscenja < p_dnevni_limit, RETURNING into new_count,
--        `IF NOT FOUND THEN RETURN -1`.
-- EXPECT increment_monthly_usage: a single UPDATE ... SET mesecno_korisceno =
--        CASE WHEN mesec IS NOT DISTINCT FROM p_mesec THEN COALESCE(...)+1
--        ELSE 1 END, RETURNING into new_count, `IF NOT FOUND THEN RETURN -1`.
-- FAIL  if either body contains a SELECT followed by a separate UPDATE — that
--        is the pre-108 read-modify-write and INV-005 does not hold.
SELECT p.proname,
       pg_get_function_identity_arguments(p.oid) AS args,
       p.prosecdef                               AS security_definer,
       p.proconfig                               AS settings,
       pg_get_functiondef(p.oid)                 AS definition
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND p.proname IN ('increment_feature_usage', 'increment_monthly_usage')
 ORDER BY p.proname;

-- Q2 ── The ON CONFLICT target must actually exist.
-- increment_feature_usage's ON CONFLICT (user_id, feature_key, dan) needs a
-- matching UNIQUE constraint or index. Without it the function errors at
-- runtime on every call and _increment_usage fails soft, returning 0 — the
-- daily limit silently stops being enforced, which for the zero-credit
-- features (copilot_ambient, morning_briefing) is the ONLY spend protection
-- there is.
-- EXPECT at least one row.
SELECT i.relname AS index_name,
       ix.indisunique,
       pg_get_indexdef(ix.indexrelid) AS definition
  FROM pg_index ix
  JOIN pg_class i ON i.oid = ix.indexrelid
  JOIN pg_class t ON t.oid = ix.indrelid
 WHERE t.relname = 'feature_usage'
   AND ix.indisunique;

-- Q3 ── Privilege lockdown (migration 108's REVOKE/GRANT block).
-- EXPECT: service_role has EXECUTE; anon and authenticated do NOT.
-- A NULL proacl means the ACL was never touched, which in PostgreSQL means
-- PUBLIC still has EXECUTE — that is a FAIL, not a blank.
SELECT p.proname,
       p.proacl,
       has_function_privilege('service_role',  p.oid, 'EXECUTE') AS service_role,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated,
       has_function_privilege('anon',          p.oid, 'EXECUTE') AS anon
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
   AND p.proname IN ('increment_feature_usage', 'increment_monthly_usage')
 ORDER BY p.proname;

-- Q4 ── Column types the functions and the test harness both assume.
-- Note: the throwaway test cluster models krediti_potroseni as DOUBLE
-- PRECISION while production reports `numeric` over PostgREST. Both accept the
-- function's DOUBLE PRECISION argument, so this is a fidelity note on the
-- harness rather than a production defect — but it should be seen, not assumed.
SELECT table_name, column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name IN ('feature_usage', 'user_credits')
 ORDER BY table_name, ordinal_position;

-- Q5 ── If a migration registry table exists, show migration 108's row.
-- Harmless if the table does not exist; the query simply returns nothing.
SELECT table_schema, table_name
  FROM information_schema.tables
 WHERE table_name ILIKE '%migration%'
    OR table_name ILIKE '%schema_version%'
 ORDER BY 1, 2;
