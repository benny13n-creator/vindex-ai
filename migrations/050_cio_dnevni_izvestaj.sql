-- ============================================================================
-- Vindex AI — Migracija 050: CIO dnevni izveštaj (keš tabela)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 049.
--
-- routers/cio.py (GET /api/cio/daily, POST /api/cio/run, GET /api/cio/history)
-- upisuje/čita iz ove tabele otkako je feature napisan, ali migracija za nju
-- nikad nije postojala u repo-u — svaki poziv na /api/cio/daily je vraćao 500
-- jer tabela ne postoji u bazi.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.cio_dnevni_izvestaj (
    id                    uuid         DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id               uuid         NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    datum                 date         NOT NULL,
    izvestaj              jsonb        NOT NULL,
    predmeta_analizirano  integer      NOT NULL DEFAULT 0,
    created_at            timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (user_id, datum)
);

CREATE INDEX IF NOT EXISTS idx_cio_izvestaj_user_datum
    ON public.cio_dnevni_izvestaj(user_id, datum DESC);

ALTER TABLE public.cio_dnevni_izvestaj ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Korisnik vidi svoje CIO izvestaje" ON public.cio_dnevni_izvestaj
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Korisnik upisuje svoje CIO izvestaje" ON public.cio_dnevni_izvestaj
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY "Korisnik azurira svoje CIO izvestaje" ON public.cio_dnevni_izvestaj
    FOR UPDATE USING (user_id = auth.uid());
