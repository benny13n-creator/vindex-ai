-- ─── Vindex AI — Supabase migracija ────────────────────────────────────────
-- Pokrenite ovu skriptu u Supabase SQL editoru (SQL Editor > New query)

-- 1. PROFILES tabela
CREATE TABLE IF NOT EXISTS public.profiles (
  id                UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email             TEXT,
  credits_remaining INTEGER NOT NULL DEFAULT 15,
  is_pro            BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 1b. Ako tabela već postoji — dodaj kolonu is_pro (idempotentno)
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_pro BOOLEAN NOT NULL DEFAULT FALSE;

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

-- ─── 6. CONVERSATIONS tabela (istorija četa po sesijama) ──────────────────────
CREATE TABLE IF NOT EXISTS public.conversations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id  UUID NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content     TEXT NOT NULL,
  tab         TEXT NOT NULL DEFAULT 'q',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Brz pristup po korisniku i sesiji
CREATE INDEX IF NOT EXISTS conversations_user_session_idx
  ON public.conversations(user_id, session_id, created_at);

-- RLS: svaki korisnik vidi SAMO svoje redove
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "conversations_own" ON public.conversations
  FOR ALL USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ─── 7. REPORTED_ERRORS tabela (prijave netačnih odgovora) ────────────────────
CREATE TABLE IF NOT EXISTS public.reported_errors (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  original_prompt TEXT,
  ai_response     TEXT,
  timestamp       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.reported_errors ENABLE ROW LEVEL SECURITY;

-- Korisnik može samo da upisuje (ne čita tuđe prijave)
CREATE POLICY "reported_errors_insert_own" ON public.reported_errors
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Admin (service_role) čita sve
CREATE POLICY "reported_errors_service_select" ON public.reported_errors
  FOR SELECT USING (
    current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
  );

-- ─── 8. PRO korisnici — admin postavljanje ────────────────────────────────────
-- Pokrenite ovo da dodelite PRO status developerima i testerima.
-- NAPOMENA: FOUNDER_EMAILS u api.py automatski dobijaju PRO status bez ove SQL komande.
-- Ova tabela se koristi za plaćene korisnike koji nisu u env varijablama.

-- Postavi is_pro = true za poznate emailove (zameni sa pravim email adresama)
UPDATE public.profiles
SET is_pro = TRUE
WHERE email IN (
  'benny13.n@gmail.com',          -- developer (admin)
  'kristina.stojanovic@dsa.rs',   -- founder
  'kristinap93@hotmail.com'       -- founder
  -- Dodaj email testera ovde: 'tester@email.com'
);

-- Pomoćna funkcija za brzo dodeljivanje PRO statusa po emailu
-- Primer upotrebe: SELECT set_user_pro('tester@email.com', true);
CREATE OR REPLACE FUNCTION public.set_user_pro(p_email TEXT, p_is_pro BOOLEAN DEFAULT TRUE)
RETURNS VOID AS $$
BEGIN
  UPDATE public.profiles SET is_pro = p_is_pro WHERE email = p_email;
  IF NOT FOUND THEN
    RAISE NOTICE 'Korisnik sa emailom % nije pronađen u profiles tabeli.', p_email;
  END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
