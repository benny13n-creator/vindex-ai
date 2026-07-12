-- ============================================================================
-- Vindex AI -- Migracija 057: 9 tabela koje AKTIVNO pozvani endpoint-i
-- ocekuju, a nikad nisu migrirane
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 056.
--
-- Za razliku od prethodnih nalaza (uglavnom nepovezane/mrtve funkcije),
-- ove tabele koristi kod koji se STVARNO poziva iz frontend-a ili iz
-- dash_load() (zakljucani "Pregled dana" -- ova migracija ne dira taj
-- kod, samo popunjava tabelu koju vec poziva):
--
--   - commander_jutarnji  -- "AI Command Center jutarnji brifing", u kodu
--     doslovno opisan kao "srce platforme". Pocetni SELECT (cache-provera)
--     NIJE bio u try/except, pa je ceo /api/commander/jutarnji verovatno
--     bacao 500 pri svakom pozivu -- poziva se sa dashboard-a
--     (_ccCaricaAiAnaliza, koji je sam graceful, pa dashboard vizuelno
--     ne puca, samo tiho ne prikazuje AI nalaze sekciju)
--   - commander_analize, evidence_grafovi, predmet_genome_history,
--     predictor_analize, hearing_briefovi -- svi upisi su vec
--     try/except-ovani (non-fatal), ali bez tabele se istorija/keš
--     nikad ne cuva
--   - push_subscriptions -- Web Push (VAPID) pretplate
--   - uploaded_documents -- samo se cita (routers/search.py), nigde se ne
--     upisuje u kodu -- verovatno mrtva grana pretrage (dokumenti idu u
--     predmet_dokumenti), ali dodata za konzistentnost i da ne baca 500
--   - user_webhooks -- korisnicki webhook-ovi (routers/integracije.py)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.commander_jutarnji (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    datum      date        NOT NULL,
    brifing    jsonb        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, datum)
);
ALTER TABLE public.commander_jutarnji ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim jutarnjim brifingom" ON public.commander_jutarnji;
CREATE POLICY "Korisnik upravlja svojim jutarnjim brifingom" ON public.commander_jutarnji
    FOR ALL USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.commander_analize (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    predmet_id uuid        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    analiza    text        NOT NULL,
    tip        text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_commander_analize_predmet ON public.commander_analize(predmet_id, created_at DESC);
ALTER TABLE public.commander_analize ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi svoje commander analize" ON public.commander_analize;
CREATE POLICY "Korisnik vidi svoje commander analize" ON public.commander_analize
    FOR SELECT USING (user_id = auth.uid());
DROP POLICY IF EXISTS "Korisnik upisuje svoje commander analize" ON public.commander_analize;
CREATE POLICY "Korisnik upisuje svoje commander analize" ON public.commander_analize
    FOR INSERT WITH CHECK (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.evidence_grafovi (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id uuid        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    podaci     jsonb       NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evidence_grafovi_predmet ON public.evidence_grafovi(predmet_id, created_at DESC);
ALTER TABLE public.evidence_grafovi ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim evidence grafovima" ON public.evidence_grafovi;
CREATE POLICY "Korisnik upravlja svojim evidence grafovima" ON public.evidence_grafovi
    FOR ALL USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.predmet_genome_history (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id     uuid        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    user_id        uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    verzija        int         NOT NULL DEFAULT 1,
    genome_data    jsonb,
    snaga_procent  int,
    trigger_event  text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_genome_history_predmet ON public.predmet_genome_history(predmet_id, created_at DESC);
ALTER TABLE public.predmet_genome_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi istoriju genoma svojih predmeta" ON public.predmet_genome_history;
CREATE POLICY "Korisnik vidi istoriju genoma svojih predmeta" ON public.predmet_genome_history
    FOR SELECT USING (user_id = auth.uid());
DROP POLICY IF EXISTS "Korisnik upisuje istoriju genoma svojih predmeta" ON public.predmet_genome_history;
CREATE POLICY "Korisnik upisuje istoriju genoma svojih predmeta" ON public.predmet_genome_history
    FOR INSERT WITH CHECK (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.predictor_analize (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    predmet_id    uuid        REFERENCES public.predmeti(id) ON DELETE SET NULL,
    tip_postupka  text,
    tip_analize   text,
    opis          text,
    analiza       text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_predictor_analize_user ON public.predictor_analize(user_id, created_at DESC);
ALTER TABLE public.predictor_analize ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi svoje predictor analize" ON public.predictor_analize;
CREATE POLICY "Korisnik vidi svoje predictor analize" ON public.predictor_analize
    FOR SELECT USING (user_id = auth.uid());
DROP POLICY IF EXISTS "Korisnik upisuje svoje predictor analize" ON public.predictor_analize;
CREATE POLICY "Korisnik upisuje svoje predictor analize" ON public.predictor_analize
    FOR INSERT WITH CHECK (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.hearing_briefovi (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    predmet_id    uuid        REFERENCES public.predmeti(id) ON DELETE SET NULL,
    rociste_naziv text,
    datum         date,
    brief         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.hearing_briefovi ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim hearing briefovima" ON public.hearing_briefovi;
CREATE POLICY "Korisnik upravlja svojim hearing briefovima" ON public.hearing_briefovi
    FOR ALL USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.push_subscriptions (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    endpoint   text        NOT NULL UNIQUE,
    p256dh     text        NOT NULL,
    auth       text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_push_subs_user ON public.push_subscriptions(user_id);
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim push pretplatama" ON public.push_subscriptions;
CREATE POLICY "Korisnik upravlja svojim push pretplatama" ON public.push_subscriptions
    FOR ALL USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.uploaded_documents (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    predmet_id     uuid        REFERENCES public.predmeti(id) ON DELETE SET NULL,
    naziv_fajla    text,
    tip_fajla      text,
    extracted_text text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_uploaded_documents_user ON public.uploaded_documents(user_id);
ALTER TABLE public.uploaded_documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi svoje uploadovane dokumente" ON public.uploaded_documents;
CREATE POLICY "Korisnik vidi svoje uploadovane dokumente" ON public.uploaded_documents
    FOR SELECT USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.user_webhooks (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    naziv      text,
    url        text        NOT NULL,
    secret     text,
    events     jsonb       DEFAULT '[]',
    aktivan    boolean     NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_webhooks_user ON public.user_webhooks(user_id);
ALTER TABLE public.user_webhooks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim webhook-ovima" ON public.user_webhooks;
CREATE POLICY "Korisnik upravlja svojim webhook-ovima" ON public.user_webhooks
    FOR ALL USING (user_id = auth.uid());
