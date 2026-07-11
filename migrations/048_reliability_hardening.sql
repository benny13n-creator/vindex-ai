-- ============================================================================
-- Vindex AI — Migracija 048: Reliability & UX Hardening Sprint
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor
-- Redosled: posle 047 (migrations/) — napomena: postoji i odvojen
--           supabase_migrations/ direktorijum (044-045) korišćen u par
--           poslednjih sesija; ova migracija namerno ide u migrations/047+.
--
-- Kreira / proširuje:
--   1. apr_lookup_log        — log svakog APR pokušaja (uspeh/neuspeh, trajanje)
--   2. praceni_predmeti      — ALTER: current_status, last_successful_check_at, last_error
--   3. portal_status_log     — ALTER: old_status, new_status, source, run_id
--   4. korisnik_viber_profil — CREATE (nikad ranije migrirana!) + quiet hours + critical override
--   5. korisnik_sms_profil   — ALTER: quiet hours + critical override
--   6. notification_log      — log svakog Viber/SMS slanja (audit)
--   7. cron_runs             — istorija izvršavanja /api/cron/daily
-- Sve IF NOT EXISTS / ADD COLUMN IF NOT EXISTS — sigurno za ponovno pokretanje.
-- ============================================================================

-- ─── 1. APR lookup log ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.apr_lookup_log (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID        REFERENCES auth.users(id) ON DELETE CASCADE,
    maticni_broj   TEXT        NOT NULL,
    success        BOOLEAN     NOT NULL,
    lookup_method  TEXT        NOT NULL DEFAULT 'html_search',
    response_ms    INT,
    greska         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_apr_log_created ON public.apr_lookup_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apr_log_success ON public.apr_lookup_log (success, created_at DESC);

ALTER TABLE public.apr_lookup_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "apr_log_sopstveni" ON public.apr_lookup_log
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "apr_log_service_role" ON public.apr_lookup_log
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── 2. Praćeni predmeti — status model ──────────────────────────────────────

ALTER TABLE public.praceni_predmeti
    ADD COLUMN IF NOT EXISTS current_status text NOT NULL DEFAULT 'tracked'
        CHECK (current_status IN ('tracked','changed','unchanged','unavailable','error')),
    ADD COLUMN IF NOT EXISTS last_successful_check_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_error text;

CREATE INDEX IF NOT EXISTS idx_praceni_current_status ON public.praceni_predmeti (current_status);

-- ─── 3. Portal status log — audit trail za SVAKU proveru ─────────────────────

ALTER TABLE public.portal_status_log
    ADD COLUMN IF NOT EXISTS old_status text,
    ADD COLUMN IF NOT EXISTS new_status text,
    ADD COLUMN IF NOT EXISTS source     text NOT NULL DEFAULT 'cron'
        CHECK (source IN ('cron','manual')),
    ADD COLUMN IF NOT EXISTS run_id     text;

CREATE INDEX IF NOT EXISTS idx_status_log_run ON public.portal_status_log (run_id);

-- ─── 4/5. Quiet hours — Viber i SMS profili ──────────────────────────────────

-- korisnik_viber_profil nikad nije kreirana migracijom (routers/viber.py je
-- referencirao tabelu koja ne postoji — Viber notifikacije su bile neispravne).
-- Kreiramo je ovde pre ALTER-a. user_id je nullable jer webhook upisuje red
-- pre nego sto je Viber nalog povezan sa Vindex korisnikom.
CREATE TABLE IF NOT EXISTS public.korisnik_viber_profil (
    id             uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id        uuid        REFERENCES auth.users(id) ON DELETE CASCADE,
    viber_user_id  text        NOT NULL UNIQUE,
    viber_name     text        DEFAULT '',
    aktivan        boolean     NOT NULL DEFAULT true,
    created_at     timestamptz DEFAULT now(),
    updated_at     timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_viber_profil_user
    ON public.korisnik_viber_profil (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_viber_profil_user ON public.korisnik_viber_profil (user_id);

ALTER TABLE public.korisnik_viber_profil ENABLE ROW LEVEL SECURITY;

CREATE POLICY "viber_profil_sopstveni_select" ON public.korisnik_viber_profil
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "viber_profil_sopstveni_update" ON public.korisnik_viber_profil
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "viber_profil_service_role" ON public.korisnik_viber_profil
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE public.korisnik_viber_profil
    ADD COLUMN IF NOT EXISTS quiet_start smallint CHECK (quiet_start BETWEEN 0 AND 23),
    ADD COLUMN IF NOT EXISTS quiet_end   smallint CHECK (quiet_end   BETWEEN 0 AND 23),
    ADD COLUMN IF NOT EXISTS allow_critical_override boolean NOT NULL DEFAULT true;

ALTER TABLE public.korisnik_sms_profil
    ADD COLUMN IF NOT EXISTS quiet_start smallint CHECK (quiet_start BETWEEN 0 AND 23),
    ADD COLUMN IF NOT EXISTS quiet_end   smallint CHECK (quiet_end   BETWEEN 0 AND 23),
    ADD COLUMN IF NOT EXISTS allow_critical_override boolean NOT NULL DEFAULT true;

-- ─── 6. Notification log — audit svakog Viber/SMS slanja ────────────────────

CREATE TABLE IF NOT EXISTS public.notification_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        REFERENCES auth.users(id) ON DELETE CASCADE,
    channel         TEXT        NOT NULL CHECK (channel IN ('viber','sms','whatsapp')),
    tip             TEXT        NOT NULL DEFAULT 'ostalo',
    ref_id          TEXT,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivery_status TEXT        NOT NULL CHECK (delivery_status IN ('sent','failed','deferred_quiet_hours')),
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_notif_log_user ON public.notification_log (user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_log_status ON public.notification_log (delivery_status, sent_at DESC);

ALTER TABLE public.notification_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notif_log_sopstveni" ON public.notification_log
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "notif_log_service_role" ON public.notification_log
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── 7. Cron runs — istorija izvršavanja /api/cron/daily ─────────────────────

CREATE TABLE IF NOT EXISTS public.cron_runs (
    run_id          TEXT        PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    duration_ms     INT,
    status          TEXT        NOT NULL DEFAULT 'running'
        CHECK (status IN ('running','ok','partial','failed')),
    processed_items INT         NOT NULL DEFAULT 0,
    errors_count    INT         NOT NULL DEFAULT 0,
    moduli          JSONB       DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_cron_runs_started ON public.cron_runs (started_at DESC);

ALTER TABLE public.cron_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "cron_runs_service_role" ON public.cron_runs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- Provera (opciono)
-- SELECT * FROM public.apr_lookup_log ORDER BY created_at DESC LIMIT 5;
-- SELECT * FROM public.cron_runs ORDER BY started_at DESC LIMIT 5;
-- SELECT current_status, count(*) FROM public.praceni_predmeti GROUP BY 1;
-- ============================================================================
