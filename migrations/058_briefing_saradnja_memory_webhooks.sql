-- ============================================================================
-- Vindex AI -- Migracija 058: 7 dodatnih tabela koje aktivno pozvani
-- endpoint-i ocekuju, a nikad nisu migrirane (drugi prolaz audita, posle 057)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 057.
--
--   - briefing_istorija   -- Morning Briefing cache/istorija (routers/morning_briefing.py).
--     Pocetni cache-check SELECT i finalni upsert NISU bili u try/except na
--     svim mestima -- bez tabele, /api/briefing/daily je verovatno bacao 500.
--   - integracije         -- Google Calendar OAuth token storage
--     (routers/integrations.py gcal_auth_url/gcal_callback/gcal_sync_rokovi).
--   - privremeni_pristup  -- "Podeli privremeni link" na predmetu
--     (routers/saradnja.py POST /api/saradnja/privremeni-pristup). Insert JE
--     u try/except, ali except grana baca HTTPException 500 (nije graceful) --
--     svaki pokusaj deljenja privremenog linka je pucao.
--   - saradnja_audit      -- audit log za multi-lawyer saradnju
--     (routers/saradnja.py). I insert i select su vec try/except-ovani
--     (non-fatal), ali bez tabele se nijedna akcija nikad nije belezila.
--   - status_incidents    -- javna status stranica, lista incidenata
--     (routers/status_page.py /api/status/public, /incidents). Vec
--     try/except-ovano na GET, ali POST /incidents (admin kreira incident)
--     nije bio zasticen -- bacao bi 500.
--   - vindex_memory       -- "institucionalna inteligencija kancelarije"
--     (routers/vindex_memory.py). DB insert je u try/except (non-fatal, samo
--     upozorenje u log), ali bez tabele /api/memory/statistike i
--     /api/memory/pretraga (SELECT bez try/except na nekim mestima) su
--     verovatno pucali.
--   - webhooks            -- Integration Hub webhook registracija
--     (routers/integrations.py). Nijedan poziv nije u try/except -- svaki
--     poziv na /api/integrations/webhook/* je bacao 500.
--
-- Kao i u 057: sva RLS poredjenja kastuju obe strane na text
-- (user_id::text = auth.uid()::text) da bi migracija radila bez obzira da li
-- neka od ovih tabela vec postoji rucno kreirana sa TEXT-tipizovanom kolonom.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.briefing_istorija (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid        NOT NULL,
    datum        date        NOT NULL,
    ai_briefing  text,
    statistike   jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, datum)
);
ALTER TABLE public.briefing_istorija ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim briefinzima" ON public.briefing_istorija;
CREATE POLICY "Korisnik upravlja svojim briefinzima" ON public.briefing_istorija
    FOR ALL USING (user_id::text = auth.uid()::text);


CREATE TABLE IF NOT EXISTS public.integracije (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid        NOT NULL,
    tip            text        NOT NULL,
    access_token   text,
    refresh_token  text,
    aktivan        boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, tip)
);
ALTER TABLE public.integracije ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim integracijama" ON public.integracije;
CREATE POLICY "Korisnik upravlja svojim integracijama" ON public.integracije
    FOR ALL USING (user_id::text = auth.uid()::text);


CREATE TABLE IF NOT EXISTS public.privremeni_pristup (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id       uuid        NOT NULL,
    vlasnik_user_id  uuid        NOT NULL,
    email_saradnika  text        NOT NULL,
    token            text        NOT NULL UNIQUE,
    dozvole          jsonb       NOT NULL DEFAULT '["citanje"]',
    istice_u         timestamptz NOT NULL,
    iskoriscen       boolean     NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_privremeni_pristup_vlasnik ON public.privremeni_pristup(vlasnik_user_id);
ALTER TABLE public.privremeni_pristup ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Vlasnik upravlja svojim privremenim pristupima" ON public.privremeni_pristup;
CREATE POLICY "Vlasnik upravlja svojim privremenim pristupima" ON public.privremeni_pristup
    FOR ALL USING (vlasnik_user_id::text = auth.uid()::text);


CREATE TABLE IF NOT EXISTS public.saradnja_audit (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id  uuid        NOT NULL,
    user_id     uuid        NOT NULL,
    akcija      text        NOT NULL,
    detalji     jsonb       DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_saradnja_audit_predmet ON public.saradnja_audit(predmet_id, created_at DESC);
ALTER TABLE public.saradnja_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi audit log svojih akcija" ON public.saradnja_audit;
CREATE POLICY "Korisnik vidi audit log svojih akcija" ON public.saradnja_audit
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje svoje akcije u audit log" ON public.saradnja_audit;
CREATE POLICY "Korisnik upisuje svoje akcije u audit log" ON public.saradnja_audit
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);


CREATE TABLE IF NOT EXISTS public.status_incidents (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    title        text        NOT NULL,
    description  text,
    severity     text        NOT NULL DEFAULT 'minor',
    started_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz
);
ALTER TABLE public.status_incidents ENABLE ROW LEVEL SECURITY;
-- Backend uvek koristi service key (shared/deps.py _get_supa), zato RLS ovde
-- je samo defense-in-depth; javno citanje/pisanje ide preko API-ja, ne direktno.
DROP POLICY IF EXISTS "service_only" ON public.status_incidents;
CREATE POLICY "service_only" ON public.status_incidents USING (false);


CREATE TABLE IF NOT EXISTS public.vindex_memory (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid        NOT NULL,
    firma_id     uuid,
    tip          text        NOT NULL,
    sadrzaj      text        NOT NULL,
    predmet_tip  text,
    ishod        text,
    tagovi       jsonb       DEFAULT '[]',
    predmet_id   uuid,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vindex_memory_user ON public.vindex_memory(user_id, created_at DESC);
ALTER TABLE public.vindex_memory ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojom memorijom" ON public.vindex_memory;
CREATE POLICY "Korisnik upravlja svojom memorijom" ON public.vindex_memory
    FOR ALL USING (user_id::text = auth.uid()::text);


CREATE TABLE IF NOT EXISTS public.webhooks (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL,
    url        text        NOT NULL,
    eventi     jsonb       NOT NULL DEFAULT '["sve"]',
    naziv      text,
    secret     text        NOT NULL,
    aktivan    boolean     NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhooks_user ON public.webhooks(user_id);
ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik upravlja svojim webhook-ovima" ON public.webhooks;
CREATE POLICY "Korisnik upravlja svojim webhook-ovima" ON public.webhooks
    FOR ALL USING (user_id::text = auth.uid()::text);
