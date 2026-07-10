-- ============================================================
-- Migracija 045 — Portal.sud.rs monitoring (praćenje statusa predmeta)
-- Pokrenuti u Supabase Dashboard → SQL Editor
-- ============================================================

-- Tabela praćenih predmeta
CREATE TABLE IF NOT EXISTS public.praceni_predmeti (
  id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  predmet_id              text        NOT NULL,
  naziv                   text        NOT NULL DEFAULT '',
  broj_predmeta           text        NOT NULL,
  sud_naziv               text        NOT NULL,
  sud_kod                 text        NOT NULL DEFAULT '',
  poslednji_status        text        NOT NULL DEFAULT '',
  poslednji_status_datum  text        NOT NULL DEFAULT '',
  poslednja_provera       timestamptz,
  aktivan                 boolean     NOT NULL DEFAULT true,
  created_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_praceni_user_predmet UNIQUE (user_id, predmet_id)
);

CREATE INDEX IF NOT EXISTS idx_praceni_user
  ON public.praceni_predmeti (user_id);

CREATE INDEX IF NOT EXISTS idx_praceni_aktivan
  ON public.praceni_predmeti (aktivan);

ALTER TABLE public.praceni_predmeti ENABLE ROW LEVEL SECURITY;

CREATE POLICY "praceni_sopstveni" ON public.praceni_predmeti
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "praceni_service_role" ON public.praceni_predmeti
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Tabela istorije statusa
CREATE TABLE IF NOT EXISTS public.portal_status_log (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  praceni_predmet_id  uuid        NOT NULL REFERENCES public.praceni_predmeti(id) ON DELETE CASCADE,
  user_id             uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status_tekst        text        NOT NULL DEFAULT '',
  status_datum        text        NOT NULL DEFAULT '',
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_status_log_pp
  ON public.portal_status_log (praceni_predmet_id);

CREATE INDEX IF NOT EXISTS idx_status_log_user
  ON public.portal_status_log (user_id);

ALTER TABLE public.portal_status_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "status_log_sopstveni" ON public.portal_status_log
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "status_log_service_role" ON public.portal_status_log
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================
-- Provera (opciono)
-- SELECT * FROM public.praceni_predmeti LIMIT 5;
-- SELECT * FROM public.portal_status_log LIMIT 5;
-- ============================================================
