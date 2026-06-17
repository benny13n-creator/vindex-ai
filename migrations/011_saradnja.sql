-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 011 — Saradnja (multi-lawyer collaboration)
-- Pokrenuti u Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.predmet_saradnici (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id       TEXT        NOT NULL,
    owner_user_id    TEXT        NOT NULL,
    saradnik_user_id TEXT        NOT NULL,
    uloga            TEXT        NOT NULL DEFAULT 'citanje'
                     CHECK (uloga IN ('citanje', 'saradnja', 'vodenje')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(predmet_id, saradnik_user_id)
);

CREATE INDEX IF NOT EXISTS idx_ps_predmet  ON public.predmet_saradnici(predmet_id);
CREATE INDEX IF NOT EXISTS idx_ps_saradnik ON public.predmet_saradnici(saradnik_user_id);
CREATE INDEX IF NOT EXISTS idx_ps_owner    ON public.predmet_saradnici(owner_user_id);

ALTER TABLE public.predmet_saradnici ENABLE ROW LEVEL SECURITY;

-- Vlasnik čita i menja sopstvene saradnike
DROP POLICY IF EXISTS "ps_owner_select" ON public.predmet_saradnici;
CREATE POLICY "ps_owner_select" ON public.predmet_saradnici
    FOR SELECT USING (owner_user_id = auth.uid()::text);

DROP POLICY IF EXISTS "ps_owner_insert" ON public.predmet_saradnici;
CREATE POLICY "ps_owner_insert" ON public.predmet_saradnici
    FOR INSERT WITH CHECK (owner_user_id = auth.uid()::text);

DROP POLICY IF EXISTS "ps_owner_delete" ON public.predmet_saradnici;
CREATE POLICY "ps_owner_delete" ON public.predmet_saradnici
    FOR DELETE USING (owner_user_id = auth.uid()::text);

-- Saradnik čita red gde je on saradnik (za moji-predmeti endpoint)
DROP POLICY IF EXISTS "ps_saradnik_select" ON public.predmet_saradnici;
CREATE POLICY "ps_saradnik_select" ON public.predmet_saradnici
    FOR SELECT USING (saradnik_user_id = auth.uid()::text);

-- Backend (service_role) ima pun pristup
GRANT SELECT, INSERT, UPDATE, DELETE ON public.predmet_saradnici TO service_role;
