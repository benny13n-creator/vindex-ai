-- migrations/019_api_kljucevi.sql
-- Phase 5.5: API ključevi za spoljne integracije (Clio, iManage, custom)
-- Bezbedno za ponovni pokretanje (IF NOT EXISTS).
-- Pokrenuti u Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS public.api_kljucevi (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT        NOT NULL,
    kljuc               TEXT        NOT NULL UNIQUE,
    naziv               TEXT        NOT NULL DEFAULT 'Default',
    aktivan             BOOLEAN     NOT NULL DEFAULT true,
    broj_poziva         INTEGER     NOT NULL DEFAULT 0,
    kreirano            TIMESTAMPTZ NOT NULL DEFAULT now(),
    poslednje_koriscenje TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_kljucevi_user   ON public.api_kljucevi(user_id);
CREATE INDEX IF NOT EXISTS idx_api_kljucevi_kljuc  ON public.api_kljucevi(kljuc);
CREATE INDEX IF NOT EXISTS idx_api_kljucevi_aktivan ON public.api_kljucevi(aktivan);

ALTER TABLE public.api_kljucevi ENABLE ROW LEVEL SECURITY;

-- Korisnik vidi i briše samo sopstvene ključeve
DROP POLICY IF EXISTS "api_kljucevi_owner" ON public.api_kljucevi;
CREATE POLICY "api_kljucevi_owner" ON public.api_kljucevi
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

-- Backend (service_role) ima pun pristup za validaciju ključeva
GRANT SELECT, INSERT, UPDATE, DELETE ON public.api_kljucevi TO service_role;
