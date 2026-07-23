-- ============================================================================
-- Vindex AI -- Migracija 078: SEC-034 -- klijenti + predmet_komentari RLS policies
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor.
--
-- KONTEKST: scripts/sec034_live_completeness_check.sql (2026-07-23) je
-- pokrenut protiv produkcije i otkrio da tabele "klijenti" i
-- "predmet_komentari" imaju RLS UKLJUCEN ali NIJEDAN aktivan policy u
-- pg_policies -- iako supabase_setup.sql (legacy root-level fajl, van
-- migrations/ foldera, zato ga originalna SEC-034 staticka revizija nije
-- ni skenirala) definise po 4 policy-ja za obe tabele. Nijedna kasnija
-- migracija ih ne dropuje -- najverovatnije supabase_setup.sql nikad nije
-- u potpunosti izvrsen protiv produkcije, ili su policy-ji naknadno
-- uklonjeni van pracene istorije. Ovo je isti rizik-obrazac kao SEC-031/
-- SEC-034 (54, 056): definicija postoji u repo-u, live stanje se ne
-- poklapa, bez ikakve greske koja bi to signalizirala.
--
-- Backend koristi SUPABASE_SERVICE_KEY (shared/deps.py) koji zaobilazi RLS
-- u potpunosti (SEC-004, poznata arhitekturna cinjenica) -- app-nivo
-- autorizacija vec filtrira po user_id u routers/*.py, tako da ovo NIJE
-- aktivan BOLA proboj kroz aplikaciju. Ovo je defense-in-depth: bez ovih
-- policy-ja, "klijenti" (osnovni klijentski podaci) i "predmet_komentari"
-- nemaju drugu liniju odbrane ako ikad postoji direktan client-side
-- Supabase poziv ili procuri anon kljuc.
--
-- Definicije ispod su doslovno prekopirane iz supabase_setup.sql:575-608
-- (klijenti) i supabase_setup.sql:534-562 (predmet_komentari), samo
-- preimenovane u migracioni fajl -- nista nije promenjeno u logici ili
-- uslovima. Obe su vec idempotentno omotane (DO $$ ... IF NOT EXISTS ...)
-- u originalu, sto znaci da se ovaj fajl moze bezbedno ponovo pokrenuti.
--
-- Ovo NE dira nijedan FK ni auth.users -- samo ENABLE RLS (vec ukljucen,
-- ali IF NOT EXISTS ekvivalent nema za ALTER TABLE ENABLE RLS, pa je
-- naredba i dalje bezbedna da se ponovi -- Postgres je prihvata bez greske
-- cak i ako je RLS vec ukljucen) i CREATE POLICY. Nema ACCESS EXCLUSIVE
-- lock-a na deljenu tabelu, nema NOT VALID/VALIDATE koraka potrebnog --
-- bezbedno u jednoj transakciji.
-- ============================================================================

BEGIN;

-- ── klijenti ──────────────────────────────────────────────────────────────
ALTER TABLE public.klijenti ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='klijenti' AND policyname='klijenti_select') THEN
    CREATE POLICY "klijenti_select" ON public.klijenti FOR SELECT USING (auth.uid()::text = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='klijenti' AND policyname='klijenti_insert') THEN
    CREATE POLICY "klijenti_insert" ON public.klijenti FOR INSERT WITH CHECK (auth.uid()::text = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='klijenti' AND policyname='klijenti_update') THEN
    CREATE POLICY "klijenti_update" ON public.klijenti FOR UPDATE USING (auth.uid()::text = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='klijenti' AND policyname='klijenti_delete') THEN
    CREATE POLICY "klijenti_delete" ON public.klijenti FOR DELETE USING (auth.uid()::text = user_id);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.klijenti TO service_role;

-- ── predmet_komentari ────────────────────────────────────────────────────
ALTER TABLE public.predmet_komentari ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='predmet_komentari' AND policyname='komentari_select') THEN
    CREATE POLICY "komentari_select" ON public.predmet_komentari FOR SELECT USING (auth.uid()::text = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='predmet_komentari' AND policyname='komentari_insert') THEN
    CREATE POLICY "komentari_insert" ON public.predmet_komentari FOR INSERT WITH CHECK (auth.uid()::text = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='predmet_komentari' AND policyname='komentari_update') THEN
    CREATE POLICY "komentari_update" ON public.predmet_komentari FOR UPDATE USING (auth.uid()::text = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='predmet_komentari' AND policyname='komentari_delete') THEN
    CREATE POLICY "komentari_delete" ON public.predmet_komentari FOR DELETE USING (auth.uid()::text = user_id);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.predmet_komentari TO service_role;

COMMIT;

-- ============================================================================
-- VERIFIKACIJA POSLE POKRETANJA (read-only, pokreni odvojeno):
--
-- SELECT tablename, policyname, cmd
-- FROM pg_policies
-- WHERE tablename IN ('klijenti', 'predmet_komentari')
-- ORDER BY tablename, policyname;
--
-- Ocekivano: 8 redova (4 za svaku tabelu) -- select/insert/update/delete.
-- ============================================================================

-- ============================================================================
-- ROLLBACK (ne pokretati automatski -- samo ako se ispostavi problem):
--
-- BEGIN;
-- DROP POLICY IF EXISTS "klijenti_select" ON public.klijenti;
-- DROP POLICY IF EXISTS "klijenti_insert" ON public.klijenti;
-- DROP POLICY IF EXISTS "klijenti_update" ON public.klijenti;
-- DROP POLICY IF EXISTS "klijenti_delete" ON public.klijenti;
-- DROP POLICY IF EXISTS "komentari_select" ON public.predmet_komentari;
-- DROP POLICY IF EXISTS "komentari_insert" ON public.predmet_komentari;
-- DROP POLICY IF EXISTS "komentari_update" ON public.predmet_komentari;
-- DROP POLICY IF EXISTS "komentari_delete" ON public.predmet_komentari;
-- COMMIT;
-- ============================================================================
