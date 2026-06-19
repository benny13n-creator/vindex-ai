-- Migration 016: Evidence Vault — klasifikacija dokumenata
-- Run in Supabase SQL Editor

-- Extend predmet_dokumenti with AI classification fields
ALTER TABLE public.predmet_dokumenti
  ADD COLUMN IF NOT EXISTS tip_dokaza        TEXT,
  ADD COLUMN IF NOT EXISTS pravni_elementi   TEXT[],
  ADD COLUMN IF NOT EXISTS ai_tags           JSONB,
  ADD COLUMN IF NOT EXISTS klasifikovan_at   TIMESTAMPTZ;

-- Index for filtering by document type
CREATE INDEX IF NOT EXISTS idx_pdok_tip ON public.predmet_dokumenti (tip_dokaza)
  WHERE deleted_at IS NULL;

-- Evidence items — specific facts/claims extracted from documents
CREATE TABLE IF NOT EXISTS public.predmet_dokazi (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  predmet_id      UUID NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
  dokument_id     UUID REFERENCES public.predmet_dokumenti(id) ON DELETE SET NULL,
  user_id         UUID NOT NULL REFERENCES auth.users(id),
  tvrdnja         TEXT NOT NULL,
  kategorija      TEXT NOT NULL CHECK (kategorija IN ('cinjenica','dokaz','svedok','vestacenje','pravni_osnov','ostalo')),
  snaga           TEXT NOT NULL DEFAULT 'srednja' CHECK (snaga IN ('jaka','srednja','slaba')),
  pravni_element  TEXT,
  napomena        TEXT,
  created_at      TIMESTAMPTZ DEFAULT now(),
  deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dokaz_predmet ON public.predmet_dokazi (predmet_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_dokaz_kategorija ON public.predmet_dokazi (predmet_id, kategorija);

ALTER TABLE public.predmet_dokazi ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "dokazi_user_isolation" ON public.predmet_dokazi;
CREATE POLICY "dokazi_user_isolation" ON public.predmet_dokazi
  FOR ALL USING (user_id = auth.uid());

GRANT ALL ON public.predmet_dokazi TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.predmet_dokazi TO authenticated;
