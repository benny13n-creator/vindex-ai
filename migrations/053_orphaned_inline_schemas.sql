-- ============================================================================
-- Vindex AI -- Migracija 053: 5 tabela sa "SQL migracija" komentarom u kodu
-- koje nikad nisu postale stvarne migracije
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 052.
--
-- Isti bug-obrazac kao migracije 050/052: routers/*.py sadrze kompletnu SQL
-- semu upisanu kao komentar ("SQL migracija -- pokrenuti rucno u Supabase")
-- ali ta sema nikad nije stigla do jedne stvarne migracije u repo-u.
--
--   - onboarding_state    (routers/onboarding.py)     -- prati korak-po-korak
--     progres novog korisnika kroz onboarding wizard. Ako ova tabela ne
--     postoji, progres se ne cuva izmedju sesija.
--   - user_knowledge      (routers/knowledge_base.py)  -- licna baza znanja
--     korisnika (beleske sa auto-tagovanjem + Pinecone pretraga)
--   - simulator_partije   (routers/strategy_simulator.py) -- istorija
--     partija Litigation Simulatora po predmetu
--   - whatsapp_pretplate  (routers/whatsapp_notif.py)  -- WhatsApp/Viber
--     pretplata korisnika na notifikacije o rokovima
--   - whatsapp_send_log   (routers/whatsapp_notif.py)  -- log poslatih
--     WhatsApp poruka
--   - discovery_queue     (routers/auto_discovery.py)  -- admin-only red
--     cekanja za bulk ingestion pravnih izvora (nije user-facing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.onboarding_state (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid        UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    step_completed   int         DEFAULT 0,
    completed        boolean     DEFAULT false,
    tip_kancelarije  text,
    oblasti_prava    text[],
    broj_predmeta    text,
    ciljevi          text[],
    completed_at     timestamptz,
    created_at       timestamptz DEFAULT now(),
    updated_at       timestamptz DEFAULT now()
);
ALTER TABLE public.onboarding_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim onboarding stanjem" ON public.onboarding_state;
CREATE POLICY "Korisnik upravlja svojim onboarding stanjem" ON public.onboarding_state
    FOR ALL USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.user_knowledge (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    naslov     text        NOT NULL,
    sadrzaj    text        NOT NULL,
    tagovi     text[]      DEFAULT '{}',
    predmet_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_uk_user    ON public.user_knowledge(user_id);
CREATE INDEX IF NOT EXISTS idx_uk_predmet ON public.user_knowledge(predmet_id);
ALTER TABLE public.user_knowledge ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojom bazom znanja" ON public.user_knowledge;
CREATE POLICY "Korisnik upravlja svojom bazom znanja" ON public.user_knowledge
    FOR ALL USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.simulator_partije (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id uuid        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    istorija   jsonb       DEFAULT '[]',
    status     text        DEFAULT 'aktivna',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sim_predmet
    ON public.simulator_partije(predmet_id, created_at DESC);
ALTER TABLE public.simulator_partije ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi svoje simulator partije" ON public.simulator_partije;
CREATE POLICY "Korisnik vidi svoje simulator partije" ON public.simulator_partije
    FOR SELECT USING (user_id = auth.uid());
DROP POLICY IF EXISTS "Korisnik upisuje svoje simulator partije" ON public.simulator_partije;
CREATE POLICY "Korisnik upisuje svoje simulator partije" ON public.simulator_partije
    FOR INSERT WITH CHECK (user_id = auth.uid());
DROP POLICY IF EXISTS "Korisnik azurira svoje simulator partije" ON public.simulator_partije;
CREATE POLICY "Korisnik azurira svoje simulator partije" ON public.simulator_partije
    FOR UPDATE USING (user_id = auth.uid());


CREATE TABLE IF NOT EXISTS public.whatsapp_pretplate (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid        NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    telefon          text        NOT NULL,
    kanal            text        DEFAULT 'whatsapp',
    tip_notifikacija jsonb       DEFAULT '["rokovi_hitni","rocista"]',
    aktivan          boolean     DEFAULT true,
    created_at       timestamptz DEFAULT now()
);
ALTER TABLE public.whatsapp_pretplate ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojom whatsapp pretplatom" ON public.whatsapp_pretplate;
CREATE POLICY "Korisnik upravlja svojom whatsapp pretplatom" ON public.whatsapp_pretplate
    FOR ALL USING (user_id = auth.uid());

CREATE TABLE IF NOT EXISTS public.whatsapp_send_log (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    poslato_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wa_send_log_user
    ON public.whatsapp_send_log(user_id, poslato_at DESC);
ALTER TABLE public.whatsapp_send_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi svoj whatsapp log" ON public.whatsapp_send_log;
CREATE POLICY "Korisnik vidi svoj whatsapp log" ON public.whatsapp_send_log
    FOR SELECT USING (user_id = auth.uid());


-- discovery_queue -- admin-only bulk ingestion red cekanja, bez user_id kolone
-- po originalnoj semi (nema RLS po korisniku, pristup je vec gejtovan na
-- nivou endpointa preko _is_founder()/admin provere u routers/auto_discovery.py)
CREATE TABLE IF NOT EXISTS public.discovery_queue (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    url          text,
    tip          text        NOT NULL,
    zemlja       text        DEFAULT 'RS',
    namespace    text,
    metapodaci   jsonb       DEFAULT '{}',
    status       text        DEFAULT 'pending',
    greska       text,
    processed_at timestamptz,
    created_at   timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dq_status  ON public.discovery_queue(status);
CREATE INDEX IF NOT EXISTS idx_dq_created ON public.discovery_queue(created_at DESC);
ALTER TABLE public.discovery_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role upravlja discovery queue" ON public.discovery_queue;
CREATE POLICY "Service role upravlja discovery queue" ON public.discovery_queue
    FOR ALL USING (auth.role() = 'service_role');
