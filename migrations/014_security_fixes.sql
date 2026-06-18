-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 014 — Security fixes
-- Pokrenuti u Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

-- Fix 1: predmet_klijenti — ENABLE ROW LEVEL SECURITY (bila je jedina tabela bez RLS)
-- Bez ovoga, anon ključ (vidljiv u index.html) daje pristup svim vezama klijent↔predmet
ALTER TABLE public.predmet_klijenti ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pk_owner_all" ON public.predmet_klijenti;
CREATE POLICY "pk_owner_all" ON public.predmet_klijenti
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.predmeti
            WHERE id = predmet_klijenti.predmet_id
              AND user_id = auth.uid()
        )
    );

-- Fix 2: predmet_klijenti — dodaj uloga_klijenta i napomena kolone ako nedostaju
-- (migration 002 ih dodaje, ovo je idempotentno)
ALTER TABLE public.predmet_klijenti
    ADD COLUMN IF NOT EXISTS uloga_klijenta TEXT NOT NULL DEFAULT 'stranka',
    ADD COLUMN IF NOT EXISTS napomena TEXT,
    ADD COLUMN IF NOT EXISTS kreirano TIMESTAMPTZ NOT NULL DEFAULT now();
