-- ============================================================================
-- Vindex AI -- Migracija 054: predmet_delegiranja (Enterprise delegacija predmeta)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 053.
--
-- routers/enterprise.py (POST /api/enterprise/predmet/delegiraj,
-- GET /api/enterprise/predmet/delegiranja) -- jedina dva endpointa u tom
-- fajlu koja nemaju ekvivalent u routers/kancelarija.py (delegiranje
-- konkretnog predmeta konkretnom advokatu u firmi). Tabela nikad nije
-- migrirana.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.predmet_delegiranja (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id  uuid        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    od_user_id  uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    na_user_id  uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    napomena    text,
    status      text        NOT NULL DEFAULT 'aktivno' CHECK (status IN ('aktivno', 'zavrseno', 'otkazano')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_delegiranja_od ON public.predmet_delegiranja(od_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_delegiranja_na ON public.predmet_delegiranja(na_user_id, created_at DESC);

ALTER TABLE public.predmet_delegiranja ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Korisnik vidi delegacije koje je poslao ili primio" ON public.predmet_delegiranja
    FOR SELECT USING (od_user_id = auth.uid() OR na_user_id = auth.uid());

CREATE POLICY "Korisnik kreira delegacije za svoje predmete" ON public.predmet_delegiranja
    FOR INSERT WITH CHECK (od_user_id = auth.uid());
