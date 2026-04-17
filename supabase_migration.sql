-- ─── Vindex AI — Supabase migracija ────────────────────────────────────────
-- Pokrenite ovu skriptu u Supabase SQL editoru (SQL Editor > New query)

-- 1. PROFILES tabela
CREATE TABLE IF NOT EXISTS public.profiles (
  id                UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email             TEXT,
  credits_remaining INTEGER NOT NULL DEFAULT 15,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Row Level Security (RLS)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Korisnik čita samo sopstveni profil
CREATE POLICY "profiles_select_own" ON public.profiles
  FOR SELECT USING (auth.uid() = id);

-- Service role (backend) može sve
CREATE POLICY "profiles_service_all" ON public.profiles
  USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role')
  WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- 3. Trigger — kreira profil sa 15 kredita pri registraciji
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, credits_remaining)
  VALUES (NEW.id, NEW.email, 15)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 4. FEEDBACK tabela
CREATE TABLE IF NOT EXISTS public.feedback (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  pitanje    TEXT,
  odgovor    TEXT,
  tip        TEXT DEFAULT 'greska',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "feedback_insert_own" ON public.feedback
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "feedback_service_all" ON public.feedback
  USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role')
  WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- 5. RPC funkcija za atomično oduzimanje jednog kredita
CREATE OR REPLACE FUNCTION public.deduct_credit(p_user_id UUID)
RETURNS INTEGER AS $$
DECLARE
  new_credits INTEGER;
BEGIN
  UPDATE public.profiles
  SET credits_remaining = GREATEST(credits_remaining - 1, 0)
  WHERE id = p_user_id
    AND credits_remaining > 0
  RETURNING credits_remaining INTO new_credits;
  RETURN COALESCE(new_credits, -1);  -- -1 znači: krediti su već bili 0
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
