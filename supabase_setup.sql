-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Supabase database migration
-- Run in: Supabase Dashboard → SQL Editor → New query → Run
-- Order matters: run this file top to bottom in one shot.
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── 1. PROFILES TABLE ───────────────────────────────────────────────────────
-- Stores user metadata and PRO subscription status.
-- credits_remaining is intentionally NOT here — it lives in user_credits.

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
    WHERE tablename = 'profiles' AND policyname = 'Korisnici čitaju sopstveni profil'
  ) THEN
    CREATE POLICY "Korisnici čitaju sopstveni profil"
      ON public.profiles FOR SELECT
      USING (auth.uid() = id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'profiles' AND policyname = 'Korisnici ažuriraju sopstveni profil'
  ) THEN
    CREATE POLICY "Korisnici ažuriraju sopstveni profil"
      ON public.profiles FOR UPDATE
      USING (auth.uid() = id);
  END IF;
END $$;


-- ─── 2. USER_CREDITS TABLE ───────────────────────────────────────────────────
-- One row per user. credits_remaining starts at 15 for every new registration.
-- Backend uses service role to decrement — users can only READ their own row.

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
    WHERE tablename = 'user_credits' AND policyname = 'Korisnici čitaju sopstvene kredite'
  ) THEN
    CREATE POLICY "Korisnici čitaju sopstvene kredite"
      ON public.user_credits FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;

-- Deduction is done server-side via service role / SECURITY DEFINER function —
-- no client UPDATE policy needed. Service role bypasses RLS automatically.


-- ─── 3. TRIGGER: Auto-assign 15 credits on new user ─────────────────────────
-- Fires after every INSERT on auth.users (triggered by admin.create_user).
-- ON CONFLICT DO NOTHING keeps it idempotent if the row already exists.

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

DROP TRIGGER IF EXISTS on_auth_user_created_credits ON auth.users;

CREATE TRIGGER on_auth_user_created_credits
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user_credits();


-- ─── 4. DEDUCT_CREDIT RPC ────────────────────────────────────────────────────
-- Called by backend: _get_supa().rpc("deduct_credit", {"p_user_id": user_id})
-- Atomically decrements by 1, never goes below 0.
-- Returns the new credits_remaining value.

CREATE OR REPLACE FUNCTION public.deduct_credit(p_user_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  new_credits INTEGER;
BEGIN
  -- Only decrement when credits > 0 (prevents race to negative)
  UPDATE public.user_credits
  SET
    credits_remaining = GREATEST(credits_remaining - 1, 0),
    updated_at        = NOW()
  WHERE user_id = p_user_id
    AND credits_remaining > 0
  RETURNING credits_remaining INTO new_credits;

  -- If no row was updated (already 0 or row missing), return current value
  IF NOT FOUND THEN
    SELECT credits_remaining INTO new_credits
    FROM public.user_credits
    WHERE user_id = p_user_id;
    RETURN COALESCE(new_credits, 0);
  END IF;

  RETURN new_credits;
END;
$$;


-- ─── 5. AUDIT_LOG TABLE ──────────────────────────────────────────────────────
-- Stores only who queried + when + hash of the query (no content).
-- ZZPL čl. 5(1)(f) — data minimization.

CREATE TABLE IF NOT EXISTS public.audit_log (
  id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID        NOT NULL,
  akcija  VARCHAR(50),
  q_hash  VARCHAR(16),
  ts      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
-- No user-level read policy — only service role can read audit logs.


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


-- ─── 7. VERIFICATION QUERIES ─────────────────────────────────────────────────
-- Run these after the migration to confirm everything is in place:
--
--   SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public'
--   ORDER BY table_name;
--
--   SELECT routine_name FROM information_schema.routines
--   WHERE routine_schema = 'public' AND routine_type = 'FUNCTION';
--
--   SELECT trigger_name FROM information_schema.triggers
--   WHERE event_object_schema = 'auth' AND event_object_table = 'users';
