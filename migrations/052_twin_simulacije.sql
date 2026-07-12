-- ============================================================================
-- Vindex AI — Migracija 052: twin_simulacije (Digital Twin predmeta)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 051.
--
-- routers/digital_twin.py (POST /api/twin/simulacija, POST /api/twin/sta-ako,
-- GET /api/twin/{predmet_id}) ima ovu shemu upisanu kao komentar u samom
-- fajlu ("SQL migracija -- primeni rucno u Supabase Dashboard") ali nikad
-- nije stigla do jedne stvarne migracije u repo-u -- svaki poziv je vracao
-- 500 jer tabela ne postoji.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.twin_simulacije (
    id                    uuid         DEFAULT gen_random_uuid() PRIMARY KEY,
    predmet_id            uuid         NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    user_id               uuid         NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    scenariji             jsonb        DEFAULT '[]',
    kljucne_tacke         jsonb        DEFAULT '[]',
    optimalna_strategija  text,
    hipoteza              text,
    tip                   text         DEFAULT 'simulacija',
    created_at            timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_twin_predmet
    ON public.twin_simulacije(predmet_id, created_at DESC);

ALTER TABLE public.twin_simulacije ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Korisnik vidi svoje twin simulacije" ON public.twin_simulacije;
CREATE POLICY "Korisnik vidi svoje twin simulacije" ON public.twin_simulacije
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "Korisnik upisuje svoje twin simulacije" ON public.twin_simulacije;
CREATE POLICY "Korisnik upisuje svoje twin simulacije" ON public.twin_simulacije
    FOR INSERT WITH CHECK (user_id = auth.uid());
