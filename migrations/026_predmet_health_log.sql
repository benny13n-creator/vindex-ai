-- Migration 026: Trend zdravlja predmeta (health score istorija)
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS public.predmet_health_log (
    id          uuid          DEFAULT gen_random_uuid() PRIMARY KEY,
    predmet_id  uuid          NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    health_score integer      NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    rizik_label text,
    logged_at   timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_phl_predmet_logged
    ON public.predmet_health_log(predmet_id, logged_at DESC);

-- RLS: korisnik vidi samo logove svojih predmeta
ALTER TABLE public.predmet_health_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Korisnik vidi zdravlje svojih predmeta" ON public.predmet_health_log
    FOR SELECT USING (
        predmet_id IN (
            SELECT id FROM public.predmeti WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Korisnik upisuje zdravlje svojih predmeta" ON public.predmet_health_log
    FOR INSERT WITH CHECK (
        predmet_id IN (
            SELECT id FROM public.predmeti WHERE user_id = auth.uid()
        )
    );
