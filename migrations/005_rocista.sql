-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 005: rocista (court hearings) table
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.rocista (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  predmet_id          UUID        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
  user_id             UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  sud                 TEXT        NOT NULL,
  broj_predmeta_suda  TEXT,
  datum               DATE        NOT NULL,
  vreme               TIME,
  sudnica             TEXT,
  status              TEXT        NOT NULL DEFAULT 'zakazano'
                      CHECK (status IN ('zakazano','odrzano','odlozeno','otkazano')),
  napomena            TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rocista_predmet_id ON public.rocista(predmet_id);
CREATE INDEX IF NOT EXISTS idx_rocista_datum      ON public.rocista(datum);
CREATE INDEX IF NOT EXISTS idx_rocista_user_datum ON public.rocista(user_id, datum);

ALTER TABLE public.rocista ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='rocista' AND policyname='Korisnici citaju sopstvena rocista'
  ) THEN
    CREATE POLICY "Korisnici citaju sopstvena rocista"
      ON public.rocista FOR SELECT USING (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='rocista' AND policyname='Korisnici kreiraju sopstvena rocista'
  ) THEN
    CREATE POLICY "Korisnici kreiraju sopstvena rocista"
      ON public.rocista FOR INSERT WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='rocista' AND policyname='Korisnici menjaju sopstvena rocista'
  ) THEN
    CREATE POLICY "Korisnici menjaju sopstvena rocista"
      ON public.rocista FOR UPDATE USING (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='rocista' AND policyname='Korisnici brisu sopstvena rocista'
  ) THEN
    CREATE POLICY "Korisnici brisu sopstvena rocista"
      ON public.rocista FOR DELETE USING (auth.uid() = user_id);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rocista TO service_role;
