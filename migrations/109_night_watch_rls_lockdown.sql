-- ⚠ SUPERSEDED — DO NOT RUN. See migrations/110_rls_lockdown_idempotent.sql.
--
-- This file aborted on 2026-08-09 with:
--     ERROR: 42P01: relation "public.discovered_bilteni" does not exist
-- It assumed all five target tables exist; discovered_bilteni does not exist in
-- this database (migration 017 was evidently never applied here). 110 carries
-- the identical intent, guards every table with to_regclass, and is idempotent,
-- so it lands correctly whether or not this file's earlier statements committed
-- before the abort.
--
-- Only this comment block was added. No SQL statement below was modified.

-- ═══════════════════════════════════════════════════════════════════════════
-- 109 — Night Watch (2026-08-09): close two RLS/GRANT holes reachable with the
--       public anon key that is shipped in static/vindex.js.
--
-- STATUS: READY — NOT APPLIED. Drafted by the agent; the founder applies it.
-- Nothing here deletes or rewrites data. It only removes privileges that were
-- never intended to be granted.
-- ═══════════════════════════════════════════════════════════════════════════


-- ── B-01 (P0) — feature_usage: the quota counter was user-writable ─────────
--
-- migrations/064_feature_registry.sql:71 created:
--     CREATE POLICY "feature_usage_self" ON public.feature_usage
--       FOR ALL USING (user_id::text = auth.uid()::text);
--
-- FOR ALL covers UPDATE and DELETE, not just SELECT. Supabase grants
-- `authenticated` full DML on public tables by default and no REVOKE was ever
-- issued for this table, so a logged-in user could run, from the browser
-- console with the anon key already present in the page:
--
--     _supa.from('feature_usage').delete().eq('user_id', myUid)
--
-- shared/usage.py::consume() reads broj_koriscenja both for its friendly
-- pre-check and — through migration 108's increment_feature_usage RPC — for the
-- AUTHORITATIVE daily gate. Both then see 0, and dnevni_limit/mesecni_limit are
-- unbounded from that moment.
--
-- Migration 108's own header names the two features for which this counter is
-- the ONLY budget protection: copilot_ambient (200/day, 0 credits) and
-- morning_briefing (5/day, 0 credits). Both become free and unlimited. Wiping
-- krediti_potroseni also corrupts founder cost reporting.
--
-- This is the same class of hole migration 103 closed for profiles.is_pro — on
-- the very table migration 108 exists to protect.
--
-- The server always writes through SECURITY DEFINER RPCs owned by
-- service_role, so removing user DML costs the application nothing.

REVOKE INSERT, UPDATE, DELETE ON public.feature_usage FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON public.feature_usage FROM anon;

DROP POLICY IF EXISTS "feature_usage_self" ON public.feature_usage;
CREATE POLICY "feature_usage_self_read" ON public.feature_usage
    FOR SELECT USING (user_id::text = auth.uid()::text);


-- ── B-02 (P1) — four tables reachable with full DML by anon ────────────────
--
-- Two causes.
--
-- (a) Policies NAMED for service_role but missing the TO clause. A policy with
--     no TO applies to PUBLIC, and the body is USING (true) WITH CHECK (true).
--     Every other migration in the repo writes this correctly
--     (048:42, 049:58, 086:43, 087:37, 088:59 all use FOR ALL TO service_role),
--     which is what makes these two a typo rather than a decision.

DROP POLICY IF EXISTS "service_role_ingest_jobs" ON public.ingest_jobs;
CREATE POLICY "service_role_ingest_jobs" ON public.ingest_jobs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_discovered_bilteni" ON public.discovered_bilteni;
CREATE POLICY "service_role_discovered_bilteni" ON public.discovered_bilteni
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- (b) Two tables never had RLS enabled at all — the only two in the schema.
--     case_benchmarks holds every opted-in firm's outcome/value/naplaceno data
--     and feeds the cross-firm benchmark pool, so an unauthenticated visitor
--     holding the shipped anon key could both read it and poison it.

ALTER TABLE public.case_benchmarks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.zakoni_monitoring ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_case_benchmarks" ON public.case_benchmarks;
CREATE POLICY "service_role_case_benchmarks" ON public.case_benchmarks
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_zakoni_monitoring" ON public.zakoni_monitoring;
CREATE POLICY "service_role_zakoni_monitoring" ON public.zakoni_monitoring
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── B-06 (P2) — SECURITY DEFINER functions without a fixed search_path ─────
--
-- A definer function resolves unqualified names through the CALLER's
-- search_path. Only migrations 107 and 108 and the two functions in
-- supabase_setup.sql set it explicitly. ALTER FUNCTION ... SET search_path does
-- not touch the body and preserves ACLs.
--
-- Latent rather than live: every one of these has an explicit REVOKE FROM
-- PUBLIC/anon/authenticated, so the reachable caller set is service_role today.
-- Fixed now because that is one REVOKE away from being wrong.

DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
       AND p.prosecdef                                    -- SECURITY DEFINER
       AND (p.proconfig IS NULL
            OR NOT EXISTS (SELECT 1 FROM unnest(p.proconfig) c
                            WHERE c LIKE 'search\_path=%'))
  LOOP
    EXECUTE format('ALTER FUNCTION %s SET search_path = public', r.sig);
    RAISE NOTICE 'search_path fixed: %', r.sig;
  END LOOP;
END $$;


-- ── VERIFY (read-only; run after applying and paste the output back) ───────
--
-- EXPECT feature_usage: authenticated/anon FALSE for insert/update/delete,
--        TRUE for select; exactly one policy, named feature_usage_self_read.
--
-- SELECT has_table_privilege('authenticated','public.feature_usage','SELECT') AS auth_select,
--        has_table_privilege('authenticated','public.feature_usage','UPDATE') AS auth_update,
--        has_table_privilege('authenticated','public.feature_usage','DELETE') AS auth_delete,
--        has_table_privilege('anon','public.feature_usage','UPDATE')          AS anon_update;
--
-- SELECT tablename, policyname, roles, cmd
--   FROM pg_policies
--  WHERE tablename IN ('feature_usage','ingest_jobs','discovered_bilteni',
--                      'case_benchmarks','zakoni_monitoring')
--  ORDER BY tablename, policyname;
--
-- EXPECT rowsecurity = true for all four B-02 tables.
-- SELECT relname, relrowsecurity
--   FROM pg_class
--  WHERE relname IN ('ingest_jobs','discovered_bilteni','case_benchmarks','zakoni_monitoring');
--
-- EXPECT zero rows.
-- SELECT p.proname
--   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
--  WHERE n.nspname='public' AND p.prosecdef
--    AND (p.proconfig IS NULL OR NOT EXISTS (
--          SELECT 1 FROM unnest(p.proconfig) c WHERE c LIKE 'search\_path=%'));
