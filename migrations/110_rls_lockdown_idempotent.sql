-- ═══════════════════════════════════════════════════════════════════════════
-- 110 — Supersedes 109. Same intent, made idempotent and defensive.
--
-- WHY THIS FILE EXISTS
-- Migration 109 aborted partway with:
--     ERROR: 42P01: relation "public.discovered_bilteni" does not exist
--
-- That was my error: 109 assumed all five target tables exist in production.
-- Four do (feature_usage, ingest_jobs, case_benchmarks, zakoni_monitoring);
-- discovered_bilteni does not — migration 017 created it, but this database
-- has no such relation, so 017 was evidently never applied here.
--
-- The abort leaves the applied state AMBIGUOUS: depending on whether the SQL
-- editor wrapped the script in a transaction, either nothing landed, or the
-- statements before the failing one did. Rather than guess, every statement
-- below is idempotent and produces the correct end state in BOTH worlds.
-- Run this file; ignore 109.
--
-- 109 IS NOT EDITED. It failed, it is superseded, and it stays on record as
-- written -- the forward-migration rule exists precisely for this situation.
--
-- STATUS: READY. Nothing here deletes or rewrites data; it only removes
-- privileges that were never intended to be granted. A missing table is
-- skipped with a NOTICE instead of aborting the run.
-- ═══════════════════════════════════════════════════════════════════════════


-- ── B-01 (P0) — feature_usage: the quota counter was user-writable ─────────
--
-- migrations/064_feature_registry.sql:71 created the policy as FOR ALL, which
-- covers UPDATE and DELETE. Supabase grants `authenticated` full DML on public
-- tables by default, no REVOKE was ever issued for this table, and the anon key
-- is shipped in static/vindex.js. So a logged-in user could run, from the
-- browser console:
--
--     _supa.from('feature_usage').delete().eq('user_id', myUid)
--
-- shared/usage.py::consume() reads broj_koriscenja for its friendly pre-check
-- AND, via migration 108's increment_feature_usage RPC, for the AUTHORITATIVE
-- daily gate. Both then see 0, and dnevni_limit/mesecni_limit are unbounded.
-- Migration 108's own header names the two features for which this counter is
-- the ONLY budget protection -- copilot_ambient (200/day) and morning_briefing
-- (5/day), both priced at zero credits. Both become free and unlimited.
--
-- Same class of hole migration 103 closed for profiles.is_pro, on the very
-- table migration 108 exists to protect.
--
-- The server always writes through SECURITY DEFINER RPCs owned by service_role,
-- so removing user DML costs the application nothing.

DO $$
BEGIN
  IF to_regclass('public.feature_usage') IS NULL THEN
    RAISE NOTICE 'feature_usage ne postoji — preskačem';
  ELSE
    REVOKE INSERT, UPDATE, DELETE ON public.feature_usage FROM authenticated;
    REVOKE INSERT, UPDATE, DELETE ON public.feature_usage FROM anon;

    DROP POLICY IF EXISTS "feature_usage_self"      ON public.feature_usage;
    DROP POLICY IF EXISTS "feature_usage_self_read" ON public.feature_usage;
    CREATE POLICY "feature_usage_self_read" ON public.feature_usage
        FOR SELECT USING (user_id::text = auth.uid()::text);

    RAISE NOTICE 'feature_usage: DML revoked, policy narrowed to SELECT';
  END IF;
END $$;


-- ── B-02 (P1) — tables reachable with full DML by anon ─────────────────────
--
-- Two causes.
--
-- (a) Policies NAMED for service_role but missing the TO clause. A policy with
--     no TO applies to PUBLIC, and the body is USING (true) WITH CHECK (true).
--     Every other migration writes this correctly (048:42, 049:58, 086:43,
--     087:37, 088:59 all use FOR ALL TO service_role), which is what makes
--     these a typo rather than a decision.
--
-- (b) case_benchmarks and zakoni_monitoring are the only two tables in the
--     schema that are created and never get RLS enabled at all. case_benchmarks
--     holds every opted-in firm's outcome/value/naplaceno data and feeds the
--     cross-firm benchmark pool, so it was both readable and poisonable by an
--     unauthenticated visitor holding the shipped anon key.
--
-- discovered_bilteni is included for completeness and skipped automatically
-- where it does not exist -- which is the case in this database today.

DO $$
DECLARE
  t   TEXT;
  pol TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['ingest_jobs','discovered_bilteni','case_benchmarks','zakoni_monitoring']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE NOTICE '% ne postoji u ovoj bazi — preskačem', t;
      CONTINUE;
    END IF;

    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);

    -- Drop the mis-written policy under both the historical name and the name
    -- this migration uses, so a re-run is clean either way.
    pol := 'service_role_' || t;
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pol, t);
    EXECUTE format(
      'CREATE POLICY %I ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)',
      pol, t);

    RAISE NOTICE '%: RLS enabled, policy scoped TO service_role', t;
  END LOOP;
END $$;


-- ── B-06 (P2) — SECURITY DEFINER functions without a fixed search_path ─────
--
-- A definer function resolves unqualified names through the CALLER's
-- search_path. Only migrations 107 and 108 and the two functions in
-- supabase_setup.sql set it explicitly.
--
-- Latent rather than live: every one of these carries an explicit REVOKE FROM
-- PUBLIC/anon/authenticated, so the reachable caller set is service_role today.
-- Fixed now because that is one REVOKE away from being wrong. ALTER FUNCTION
-- ... SET search_path touches neither the body nor the ACLs.

DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
       AND p.prosecdef
       AND (p.proconfig IS NULL
            OR NOT EXISTS (SELECT 1 FROM unnest(p.proconfig) c
                            WHERE c LIKE 'search\_path=%'))
  LOOP
    EXECUTE format('ALTER FUNCTION %s SET search_path = public', r.sig);
    RAISE NOTICE 'search_path fixed: %', r.sig;
  END LOOP;
END $$;


-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFY — read-only. Run after applying and paste the output back.
-- This also resolves the ambiguity about how far 109 got: the end state is
-- what matters, and these four queries describe it completely.
-- ═══════════════════════════════════════════════════════════════════════════

-- Q1. EXPECT auth_select = true; auth_update / auth_delete / anon_update = false.
SELECT has_table_privilege('authenticated','public.feature_usage','SELECT') AS auth_select,
       has_table_privilege('authenticated','public.feature_usage','UPDATE') AS auth_update,
       has_table_privilege('authenticated','public.feature_usage','DELETE') AS auth_delete,
       has_table_privilege('anon','public.feature_usage','UPDATE')          AS anon_update;

-- Q2. EXPECT exactly one feature_usage policy, named feature_usage_self_read,
--     cmd = SELECT; and each other table's policy with roles = {service_role}.
SELECT tablename, policyname, roles, cmd
  FROM pg_policies
 WHERE tablename IN ('feature_usage','ingest_jobs','case_benchmarks','zakoni_monitoring')
 ORDER BY tablename, policyname;

-- Q3. EXPECT relrowsecurity = true for all present tables.
SELECT relname, relrowsecurity
  FROM pg_class
 WHERE relname IN ('ingest_jobs','case_benchmarks','zakoni_monitoring','feature_usage');

-- Q4. EXPECT zero rows.
SELECT p.proname
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public' AND p.prosecdef
   AND (p.proconfig IS NULL OR NOT EXISTS (
         SELECT 1 FROM unnest(p.proconfig) c WHERE c LIKE 'search\_path=%'));
