-- ============================================================================
-- SEC-034 -- Live schema completeness check (READ-ONLY, safe to run anytime)
-- ============================================================================
-- Purpose: SEC-034 (docs/security/SECURITY_GAP_REGISTER.md) was discovered
-- when two migrations (054, 056) turned out to have silently done nothing
-- against production, because CREATE TABLE IF NOT EXISTS found the table
-- already existing in a bare, incomplete form. Both migration FILES were
-- themselves correct and complete -- the mismatch only existed between the
-- file and the live database, which is invisible to any repo-only analysis.
-- This query closes that gap: it inspects every table Postgres actually has
-- right now and reports RLS/policy/index/FK counts in one pass, so the same
-- class of gap can be found proactively instead of one table at a time via
-- a failed migration.
--
-- This is READ-ONLY -- pure SELECT statements against system catalogs, does
-- not modify anything. Safe to run whenever, as often as wanted.
--
-- HOW TO READ THE OUTPUT: this does not know what each table is SUPPOSED
-- to have (that requires cross-referencing migrations/*.sql by hand, or
-- future tooling) -- it reports what's actually there. Tables with
-- rls_enabled=false AND fk_count=0 AND policy_count=0 are the most likely
-- candidates for "silently incomplete" (matches exactly what predmet_
-- delegiranja and tos_acceptances looked like before they were fixed) --
-- but a genuinely simple/internal table can legitimately have zero of
-- these too. Cross-reference against the table's own migration file before
-- concluding anything is actually wrong.
-- ============================================================================

WITH table_list AS (
    SELECT c.oid, c.relname AS table_name, c.relrowsecurity AS rls_enabled
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
),
fk_counts AS (
    SELECT conrelid, count(*) AS fk_count
    FROM pg_constraint
    WHERE contype = 'f'
    GROUP BY conrelid
),
policy_counts AS (
    SELECT tablename, count(*) AS policy_count
    FROM pg_policies
    WHERE schemaname = 'public'
    GROUP BY tablename
),
index_counts AS (
    -- Excludes the automatic primary-key index (named '<table>_pkey') so
    -- the count reflects deliberately-added indexes, not just the PK.
    SELECT tablename, count(*) AS index_count
    FROM pg_indexes
    WHERE schemaname = 'public' AND indexname NOT LIKE '%_pkey'
    GROUP BY tablename
),
approx_rows AS (
    SELECT relname AS table_name, n_live_tup AS approx_row_count
    FROM pg_stat_user_tables
    WHERE schemaname = 'public'
)
SELECT
    t.table_name,
    t.rls_enabled,
    COALESCE(fk.fk_count, 0)      AS fk_count,
    COALESCE(pol.policy_count, 0) AS policy_count,
    COALESCE(idx.index_count, 0)  AS index_count,
    COALESCE(ar.approx_row_count, 0) AS approx_row_count,
    CASE
        WHEN NOT t.rls_enabled AND COALESCE(fk.fk_count, 0) = 0 AND COALESCE(pol.policy_count, 0) = 0
            THEN 'CHECK -- no RLS, no FK, no policy (matches the pre-fix predmet_delegiranja/tos_acceptances shape)'
        ELSE ''
    END AS flag
FROM table_list t
LEFT JOIN fk_counts    fk  ON fk.conrelid = t.oid
LEFT JOIN policy_counts pol ON pol.tablename = t.table_name
LEFT JOIN index_counts  idx ON idx.tablename = t.table_name
LEFT JOIN approx_rows   ar  ON ar.table_name = t.table_name
ORDER BY (flag <> '') DESC, t.table_name;
