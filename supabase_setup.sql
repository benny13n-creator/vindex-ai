-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Supabase database migration v2
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Safe to re-run (idempotent): CREATE IF NOT EXISTS, CREATE OR REPLACE,
-- DROP TRIGGER IF EXISTS, ON CONFLICT DO NOTHING.
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── 1. PROFILES TABLE ───────────────────────────────────────────────────────
-- User metadata + PRO subscription flag.
-- credits_remaining intentionally NOT here — lives in user_credits.

CREATE TABLE IF NOT EXISTS public.profiles (
  id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email      TEXT,
  is_pro     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'profiles' AND policyname = 'Korisnici citaju sopstveni profil'
  ) THEN
    CREATE POLICY "Korisnici citaju sopstveni profil"
      ON public.profiles FOR SELECT
      USING (auth.uid() = id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'profiles' AND policyname = 'Korisnici azuriraju sopstveni profil'
  ) THEN
    CREATE POLICY "Korisnici azuriraju sopstveni profil"
      ON public.profiles FOR UPDATE
      USING (auth.uid() = id);
  END IF;
END $$;

-- Service role full access (bypasses RLS by default, but be explicit)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles TO service_role;


-- ─── 2. USER_CREDITS TABLE ───────────────────────────────────────────────────
-- One row per user. credits_remaining starts at 15 for every new registration.
-- Backend service role decrements via deduct_credit RPC.
-- Clients can only SELECT their own row.

CREATE TABLE IF NOT EXISTS public.user_credits (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  credits_remaining INTEGER     NOT NULL DEFAULT 15,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT user_credits_user_id_key UNIQUE (user_id)
);

ALTER TABLE public.user_credits ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'user_credits' AND policyname = 'Korisnici citaju sopstvene kredite'
  ) THEN
    CREATE POLICY "Korisnici citaju sopstvene kredite"
      ON public.user_credits FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;

-- Service role full access (needed for backend upsert + deduct_credit function)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_credits TO service_role;
-- Authenticated users can read their own row (RLS enforces this)
GRANT SELECT ON public.user_credits TO authenticated;


-- ─── 3. TRIGGER: Auto-assign 15 credits on new user ─────────────────────────
-- Fires AFTER INSERT on auth.users.
-- admin.create_user() → triggers this → inserts user_credits row.
-- ON CONFLICT DO NOTHING makes it safe to call multiple times.

CREATE OR REPLACE FUNCTION public.handle_new_user_credits()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.user_credits (user_id, credits_remaining)
  VALUES (NEW.id, 15)
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Grant EXECUTE so the function can be called by the trigger system
GRANT EXECUTE ON FUNCTION public.handle_new_user_credits() TO service_role;

DROP TRIGGER IF EXISTS on_auth_user_created_credits ON auth.users;

CREATE TRIGGER on_auth_user_created_credits
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user_credits();


-- ─── 4. DEDUCT_CREDIT RPC ────────────────────────────────────────────────────
-- Backend calls: supa.rpc("deduct_credit", {"p_user_id": user_id})
-- Atomically decrements by 1. Never goes below 0.
-- Returns new credits_remaining value.
-- SECURITY DEFINER = runs as postgres superuser, bypasses RLS.

CREATE OR REPLACE FUNCTION public.deduct_credit(p_user_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  new_credits INTEGER;
BEGIN
  UPDATE public.user_credits
  SET
    credits_remaining = GREATEST(credits_remaining - 1, 0),
    updated_at        = NOW()
  WHERE user_id = p_user_id
    AND credits_remaining > 0
  RETURNING credits_remaining INTO new_credits;

  -- Row not updated means either credits = 0 or row missing
  IF NOT FOUND THEN
    SELECT credits_remaining INTO new_credits
    FROM public.user_credits
    WHERE user_id = p_user_id;
    RETURN COALESCE(new_credits, 0);
  END IF;

  RETURN new_credits;
END;
$$;

-- Allow service_role and authenticated to call this RPC via PostgREST
GRANT EXECUTE ON FUNCTION public.deduct_credit(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.deduct_credit(UUID) TO authenticated;


-- ─── 5. AUDIT_LOG TABLE ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.audit_log (
  id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID        NOT NULL,
  akcija  VARCHAR(50),
  q_hash  VARCHAR(16),
  ts      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
GRANT INSERT ON public.audit_log TO service_role;


-- ─── 6. FEEDBACK TABLE ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.feedback (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID        NOT NULL,
  q_hash     VARCHAR(16),
  tip        VARCHAR(50),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'feedback' AND policyname = 'Korisnici upisuju feedback'
  ) THEN
    CREATE POLICY "Korisnici upisuju feedback"
      ON public.feedback FOR INSERT
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

GRANT INSERT ON public.feedback TO service_role;
GRANT INSERT ON public.feedback TO authenticated;


-- ─── 7. BACKFILL: Give 15 credits to existing users who have none ─────────────
-- Safe to run multiple times — ON CONFLICT DO NOTHING.
-- Run this AFTER the table and trigger are created.

INSERT INTO public.user_credits (user_id, credits_remaining)
SELECT id, 15
FROM auth.users
WHERE id NOT IN (SELECT user_id FROM public.user_credits)
ON CONFLICT (user_id) DO NOTHING;


-- ─── 8. VERIFICATION QUERIES ─────────────────────────────────────────────────
-- Run these in a separate query after the migration:
--
-- Check tables exist:
--   SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public' ORDER BY table_name;
--
-- Check trigger exists on auth.users:
--   SELECT trigger_name, event_manipulation, action_timing
--   FROM information_schema.triggers
--   WHERE event_object_schema = 'auth' AND event_object_table = 'users';
--
-- Check RPC functions exist:
--   SELECT routine_name FROM information_schema.routines
--   WHERE routine_schema = 'public' AND routine_type = 'FUNCTION';
--
-- Check all users have credits (should return 0 rows):
--   SELECT id FROM auth.users
--   WHERE id NOT IN (SELECT user_id FROM public.user_credits);
--
-- Inspect a specific user's credits (replace the UUID):
--   SELECT * FROM public.user_credits
--   WHERE user_id = '<your-user-uuid>';


-- ─── 9. RESPONSE_AUDIT TABLE (B1 legal audit log) ────────────────────────────
-- Write-only. Populated automatically by the API on every LLM response.
-- Stores no raw query or response text — only hashes, metadata, and latency.
-- Needed before beta launch (legal liability requirement).

CREATE TABLE IF NOT EXISTS public.response_audit (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_id   VARCHAR(32) NOT NULL,
    endpoint      VARCHAR(60) NOT NULL,
    tip           VARCHAR(20),
    query_hash    VARCHAR(16) NOT NULL,
    confidence    VARCHAR(10),
    top_score     FLOAT,
    top_article   TEXT,
    top_law       TEXT,
    response_len  INTEGER     NOT NULL DEFAULT 0,
    response_hash VARCHAR(32) NOT NULL,
    latency_ms    INTEGER     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ra_ts_idx    ON public.response_audit(ts DESC);
CREATE INDEX IF NOT EXISTS ra_qhash_idx ON public.response_audit(query_hash);

-- Service role (backend) may insert; nobody may update/delete
ALTER TABLE public.response_audit ENABLE ROW LEVEL SECURITY;
GRANT INSERT ON public.response_audit TO service_role;
