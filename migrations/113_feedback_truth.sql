-- ============================================================================
-- STATUS: PRIMENJENA. Potvrdjeno read-only sondama 2026-08-14
-- (BETA-NIGHT-STABILIZATION, TASK 1):
--     feedback?select=q_hash&limit=0     400/42703    -> 200
--     reported_errors?select=id&limit=0  404/PGRST205 -> 200 (0 redova)
--     reported_errors ima user_id, original_prompt, ai_response, timestamp
--
-- NEPROVERENO: ponasanje RLS politika (nema `SUPABASE_ANON_KEY` u okruzenju).
-- Politike su deklarisane ispod; njihov EFEKAT nije izmeren.
--
-- Fajl se zadrzava kao istorijski artefakt i kao izvor istine za test
-- `test_migracija_113_deklarise_q_hash_i_reported_errors`. Idempotentan je
-- (sve `IF NOT EXISTS`), pa ponovno pokretanje ne radi nista.
-- ============================================================================
-- Migracija 113 — PRIJAVA NETACNOG PRAVNOG ODGOVORA (BETA-P1-FEEDBACK-TRUTH)
--
-- PROBLEM (mereno protiv produkcije 2026-08-14, samo citanjem)
--
-- Dva kanala postoje u kodu da advokat prijavi netacan pravni odgovor. Oba su
-- mrtva jer im skladiste ne postoji:
--
--   1. `reported_errors` — NE POSTOJI medju 166 tabela u `public`.
--      PostgREST: PGRST205, "Could not find the table 'public.reported_errors'
--      in the schema cache". Ovo je JEDINO mesto u celoj bazi gde bi se cuvao
--      TEKST pogresnog odgovora; nijedna druga tabela ga ne cuva.
--
--   2. `feedback.q_hash` — kolona NE POSTOJI. Produkciona tabela ima tacno
--      `id, user_id, tip, created_at` (dokaz: `?select=q_hash&limit=0` vraca
--      400/42703, OpenAI koren ne prijavljuje kolonu). `routers/drafting.py`
--      upisuje `q_hash` na svaki poziv, pa svaki poziv pada.
--
-- ZASTO POSTOJE DVE NEUSKLADJENE DEKLARACIJE
-- `supabase_migration.sql:45` deklarise `feedback(pitanje, odgovor)`, a
-- `supabase_setup.sql:186` deklarise `feedback(q_hash)`. Obe koriste
-- `CREATE TABLE IF NOT EXISTS`, pa je ona koja je pokrenuta druga TIHO nista
-- uradila. Produkcija nema nijedan od ta dva oblika u celini -- ima presek bez
-- ijedne kolone sadrzaja. Zato se ovde nista ne "vraca na deklarisano stanje"
-- nego se izricito dodaje ono sto kod stvarno pise.
--
-- ODLUKA O MINIMIZACIJI (ZZPL cl. 5(1)(c))
-- `feedback` ostaje BEZ SADRZAJA -- samo hes. `reported_errors` sadrzaj cuva,
-- ali samo kad ga korisnik SVESNO posalje pritiskom na "Prijavi netacan
-- odgovor". To je postojeca politika proizvoda, ne nova.
--
-- ZASTO JE BEZBEDNA
--   * `feedback.q_hash` je NULLABLE i bez DEFAULT -- cisto metapodatkovna
--     izmena, bez prepisa tabele. Postojeci red (1 u produkciji) ostaje
--     netaknut sa NULL vrednoscu.
--   * `reported_errors` se tek kreira -- nema podataka koji bi se izgubili.
--   * Nijedan postojeci objekat se ne menja niti brise.
--
-- ZASTO JE IDEMPOTENTNA
-- Sve je `IF NOT EXISTS` / uslovno u `DO $$` bloku.
-- ============================================================================

-- ─── 1. feedback.q_hash ──────────────────────────────────────────────────────
-- Sirina 16 znakova prati `shared/deps.py::_q_hash` — SHA-256 skracen na 16
-- heksadecimalnih znakova. VARCHAR(16) bi tiho ODBIO duzu vrednost, pa je
-- namerno TEXT: heš nikad ne sme da obori upis prijave.

ALTER TABLE public.feedback
  ADD COLUMN IF NOT EXISTS q_hash TEXT;

COMMENT ON COLUMN public.feedback.q_hash IS
  'SHA-256 pitanja skracen na 16 hex znakova (shared/deps.py::_q_hash). '
  'Bez sadrzaja pitanja -- ZZPL cl. 5(1)(c) minimizacija.';

-- ─── 2. reported_errors ──────────────────────────────────────────────────────
-- Oblik kolona je preuzet DOSLOVNO iz jedinog pisca, `static/vindex.js`
-- (`sendFeedback`): user_id, original_prompt, ai_response, timestamp.
-- Ne izmisljaju se dodatne kolone koje niko ne pise.

CREATE TABLE IF NOT EXISTS public.reported_errors (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  original_prompt TEXT,
  ai_response     TEXT,
  timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.reported_errors ENABLE ROW LEVEL SECURITY;

-- Korisnik SME da upisuje samo svoju prijavu i NE SME da cita nijednu --
-- ni svoju. Citanje je iskljucivo service_role (interni pregled kvaliteta).
-- Prijave sadrze tekst pravnog pitanja, dakle poverljiv sadrzaj predmeta.

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'reported_errors'
      AND policyname = 'reported_errors_insert_own'
  ) THEN
    CREATE POLICY "reported_errors_insert_own" ON public.reported_errors
      FOR INSERT WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'reported_errors'
      AND policyname = 'reported_errors_service_select'
  ) THEN
    CREATE POLICY "reported_errors_service_select" ON public.reported_errors
      FOR SELECT USING (
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS reported_errors_timestamp_idx
  ON public.reported_errors (timestamp DESC);

COMMENT ON TABLE public.reported_errors IS
  'Prijave netacnih pravnih odgovora. Jedino mesto u bazi gde se cuva TEKST '
  'spornog odgovora. Upisuje iskljucivo static/vindex.js::sendFeedback na '
  'svestan pritisak korisnika.';

-- ─── PROVERA POSLE POKRETANJA (samo citanje) ─────────────────────────────────
--
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'feedback'
--    ORDER BY ordinal_position;
--   -- ocekivano: id, user_id, tip, created_at, q_hash
--
--   SELECT to_regclass('public.reported_errors');
--   -- ocekivano: public.reported_errors (ne NULL)
--
--   SELECT policyname FROM pg_policies
--    WHERE schemaname = 'public' AND tablename = 'reported_errors';
--   -- ocekivano: reported_errors_insert_own, reported_errors_service_select
