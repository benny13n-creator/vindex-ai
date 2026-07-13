-- ============================================================================
-- Vindex AI — Migracija 061: HITNO — 5 kolona na profiles nikad nije kreirano
-- ============================================================================
-- Pokrenuti ODMAH u Supabase Dashboard → SQL Editor.
--
-- ROOT CAUSE (potvrđeno direktnim upitom nad produkcijskom bazom
-- 2026-07-13): profiles tabela NEMA kolone is_pro, plan, trial_kraj,
-- onboarding_done, full_name — iako ih kod svuda očekuje. Stvarne kolone
-- su samo: id, email, credits_remaining, created_at, registered_at,
-- briefing_aktivan.
--
-- supabase_setup.sql i supabase_migration.sql sadrže is_pro, ali oba
-- koriste "CREATE TABLE IF NOT EXISTS public.profiles" — pošto je profiles
-- tabela već postojala (kreirana pre tih skripti, van njih), taj CREATE je
-- tiho preskočen i is_pro NIKAD nije stvarno dodata u bazu. plan/trial_kraj/
-- onboarding_done/full_name nemaju NIJEDNU migraciju u celom repou — kod ih
-- koristi, ali nikad nisu ni bile definisane u SQL-u.
--
-- POSLEDICE (2 nivoa ozbiljnosti):
--   1. is_pro nedostaje → shared/deps.py _ensure_profile() tiho vraća
--      is_pro=false za SVAKOG korisnika. PRO funkcije rade samo za founder
--      naloge (FOUNDER_EMAILS env allowlist zaobilazi bazu). Svaki STVARNI
--      plaćajući PRO korisnik van te liste je verovatno bio odbijan na
--      funkcijama koje plaća.
--   2. full_name nedostaje → GET /api/gdpr/export (routers/gdpr.py:130)
--      NEMA try/except oko tog upita — endpoint SE RUŠI (500) za svakog
--      korisnika. Ovo je pravo na prenosivost podataka po GDPR čl. 20 /
--      ZZPL čl. 24 — trenutno potpuno neupotrebljivo.
--   3. plan/trial_kraj/onboarding_done nedostaju → GET /api/auth/trial/status
--      (api.py:2147) ima try/except i tiho degradira na hardkodovan default
--      (uvek prikazuje "trial aktivan, 30 dana") — ne ruši ništa, ali je
--      trial/onboarding UI trenutno neupotrebljiv za sve korisnike.
-- ============================================================================

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_pro BOOLEAN NOT NULL DEFAULT FALSE;

-- full_name — nullable, bez defaulta (nemamo prava imena za backfill;
-- postojeći kod već ima fallback na email prefiks gde god se koristi).
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS full_name TEXT;

-- plan — default 'trial' prati postojeći Python fallback (r.data.get("plan", "trial")).
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'trial';

-- trial_kraj — nullable, bez backfill-a (ne znamo stvarne datume početka
-- triala postojećih korisnika; kod već ispravno rukuje NULL vrednošću).
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS trial_kraj TIMESTAMPTZ;

-- onboarding_done — default FALSE za NOVE korisnike (ispravno ponašanje
-- idući napred), ali odmah ispod backfill-ujemo SVE postojeće redove na
-- TRUE da aktivni korisnici ne vide iznenada onboarding koji su već prošli.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS onboarding_done BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE public.profiles SET onboarding_done = TRUE;

-- Konzistentnost baze sa FOUNDER_EMAILS env varijablom (ionako već rade
-- preko allowlist-a, ovo je samo da baza odražava isto stanje):
UPDATE public.profiles
SET is_pro = TRUE
WHERE email IN (
  'benny13.n@gmail.com',
  'kristina.stojanovic@dsa.rs',
  'kristinap93@hotmail.com'
);

-- Pomoćna funkcija (CREATE OR REPLACE — bezbedno i ako već postoji, i ako
-- je ranije kreirana dok is_pro kolona nije postojala pa je bila neispravna):
CREATE OR REPLACE FUNCTION public.set_user_pro(p_email TEXT, p_is_pro BOOLEAN DEFAULT TRUE)
RETURNS VOID AS $$
BEGIN
  UPDATE public.profiles SET is_pro = p_is_pro WHERE email = p_email;
  IF NOT FOUND THEN
    RAISE NOTICE 'Korisnik sa emailom % nije pronađen u profiles tabeli.', p_email;
  END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- KRITIČNO — RUČNA PROVERA POSLE OVE MIGRACIJE:
--
-- Ako imaš STVARNE plaćajuće PRO korisnike van gornje liste (npr. preko
-- Stripe/ručne uplate/dogovora), oni NISU u ovoj bazi kao is_pro=true —
-- ova migracija ne može da pogodi ko su, samo popravlja mehanizam.
-- Za svakog takvog korisnika pokreni:
--
--   SELECT set_user_pro('email@korisnika.com', true);
--
-- Provera stanja posle migracije:
--   SELECT email, is_pro FROM public.profiles WHERE is_pro = true;
-- ============================================================================
