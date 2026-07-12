-- ============================================================================
-- Vindex AI -- Migracija 056: tos_acceptances (HITNO -- compliance gap)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 055.
--
-- routers/tos.py (GET /api/tos/status, POST /api/tos/accept) je aktivno
-- pozivan (static/vindex.js tosCheck()/tosAccept()) ali tabela nikad nije
-- migrirana. GET /status namerno "fail-open"-uje na DB gresku (vraca
-- accepted=true da ne blokira korisnika na prolaznom DB problemu) -- sto
-- znaci da je efekat trajno nepostojece tabele da se ToS/AI-consent modal
-- NIKAD nije prikazao nijednom korisniku, i nijedno prihvatanje nije
-- ikad zabelezeno.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.tos_acceptances (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    version      text        NOT NULL,
    accepted_at  timestamptz NOT NULL DEFAULT now(),
    ai_consent   boolean     NOT NULL DEFAULT false,
    UNIQUE (user_id, version)
);

CREATE INDEX IF NOT EXISTS idx_tos_user ON public.tos_acceptances(user_id);

ALTER TABLE public.tos_acceptances ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Korisnik vidi svoja prihvatanja uslova" ON public.tos_acceptances;
CREATE POLICY "Korisnik vidi svoja prihvatanja uslova" ON public.tos_acceptances
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "Korisnik beleži svoje prihvatanje uslova" ON public.tos_acceptances;
CREATE POLICY "Korisnik beleži svoje prihvatanje uslova" ON public.tos_acceptances
    FOR INSERT WITH CHECK (user_id = auth.uid());
