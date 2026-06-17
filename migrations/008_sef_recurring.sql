-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 008 — SEF e-faktura + Ponavljajuće fakture
-- Pokrenuti u Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. SEF konfiguracija (API key po korisniku, AES-256 enkripcija API key-a preporučena)
CREATE TABLE IF NOT EXISTS public.sef_podesavanja (
    user_id       UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    api_key       TEXT NOT NULL,
    seller_pib    VARCHAR(9) NOT NULL,
    seller_naziv  TEXT NOT NULL,
    seller_adresa TEXT DEFAULT '',
    seller_mesto  TEXT DEFAULT 'Beograd',
    updated_at    TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.sef_podesavanja ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sef_own" ON public.sef_podesavanja;
CREATE POLICY "sef_own" ON public.sef_podesavanja
    USING (user_id = auth.uid());

-- 2. SEF log slanja (jedna faktura može biti poslata više puta)
CREATE TABLE IF NOT EXISTS public.sef_log (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    faktura_id  UUID NOT NULL,
    sef_id      BIGINT,
    sef_status  VARCHAR(50) DEFAULT 'pending'
                CHECK (sef_status IN ('pending', 'poslato', 'greska', 'odbijeno', 'primljeno')),
    greska      TEXT,
    xml_bytes   INT,
    poslato_at  TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.sef_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "sef_log_own" ON public.sef_log;
CREATE POLICY "sef_log_own" ON public.sef_log
    USING (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS sef_log_faktura_idx ON public.sef_log (faktura_id, poslato_at DESC);

-- 3. Recurring invoice templates (mesecne/kvartalne/godisnje fakture)
CREATE TABLE IF NOT EXISTS public.recurring_templates (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    klijent_id      UUID REFERENCES public.klijenti(id) ON DELETE SET NULL,
    predmet_id      UUID REFERENCES public.predmeti(id)  ON DELETE SET NULL,
    naziv           TEXT NOT NULL CHECK (length(trim(naziv)) >= 2),
    ucestalost      VARCHAR(20) NOT NULL
                    CHECK (ucestalost IN ('mesecno', 'kvartalno', 'godisnje')),
    iznos_rsd       NUMERIC(12, 2) NOT NULL CHECK (iznos_rsd > 0),
    opis            TEXT NOT NULL,
    pdv_procenat    NUMERIC(5, 2) DEFAULT 0 CHECK (pdv_procenat >= 0),
    aktivan         BOOLEAN DEFAULT TRUE,
    sledeci_datum   DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.recurring_templates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "recur_own" ON public.recurring_templates;
CREATE POLICY "recur_own" ON public.recurring_templates
    USING (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS recurring_user_aktivan_idx
    ON public.recurring_templates (user_id, aktivan, sledeci_datum);

-- 4. Email log (praćenje slanja faktura emailom)
CREATE TABLE IF NOT EXISTS public.email_log (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    faktura_id  UUID NOT NULL,
    poslato_na  TEXT NOT NULL,
    status      VARCHAR(20) DEFAULT 'poslato'
                CHECK (status IN ('poslato', 'greska', 'bounce')),
    greska      TEXT,
    poslato_at  TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE public.email_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "email_log_own" ON public.email_log;
CREATE POLICY "email_log_own" ON public.email_log
    USING (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS email_log_faktura_idx ON public.email_log (faktura_id, poslato_at DESC);
