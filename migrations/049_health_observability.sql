-- ============================================================================
-- Vindex AI — Migracija 049: Beta Readiness & Production Hardening Sprint
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 048.
--
-- Kreira / proširuje (dodavano fazno tokom sprinta — videti sekcije ispod):
--   Faza 3 — APR & Portal health:
--     1. portal_status_log — ALTER: result_kind, response_ms
--     2. praceni_predmeti  — ALTER: consecutive_failures (per-predmet backoff)
--   Faza 4 — Admin dashboard (Notification Center, Beta Users, feedback):
--     3. notification_log  — ALTER: message_text (za retry)
--     4. support_tickets   — CREATE (nikad ranije migrirana!) + rating/kontekst
--     5. beta_users        — CREATE
-- ============================================================================

-- ─── Faza 3.1 — Portal status log: podaci za health metrike ─────────────────

ALTER TABLE public.portal_status_log
    ADD COLUMN IF NOT EXISTS result_kind text
        CHECK (result_kind IN ('ok','unavailable','error')),
    ADD COLUMN IF NOT EXISTS response_ms int;

CREATE INDEX IF NOT EXISTS idx_status_log_kind_time
    ON public.portal_status_log (result_kind, created_at DESC);

-- ─── Faza 3.2 — Praćeni predmeti: per-predmet exponential backoff ────────────

ALTER TABLE public.praceni_predmeti
    ADD COLUMN IF NOT EXISTS consecutive_failures int NOT NULL DEFAULT 0;

-- ─── Faza 4.1 — Notification log: message_text za retry ─────────────────────

ALTER TABLE public.notification_log
    ADD COLUMN IF NOT EXISTS message_text text;

-- ─── Faza 4.2 — Support tickets (nikad ranije migrirana — isti gap kao Viber) ─

CREATE TABLE IF NOT EXISTS public.support_tickets (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        REFERENCES auth.users(id) ON DELETE CASCADE,
    email       text,
    kategorija  text        NOT NULL DEFAULT 'ostalo',
    poruka      text        NOT NULL,
    rating      smallint    CHECK (rating BETWEEN 1 AND 5),
    kontekst    text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_user ON public.support_tickets (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_kat ON public.support_tickets (kategorija, created_at DESC);

ALTER TABLE public.support_tickets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "support_tickets_sopstveni" ON public.support_tickets
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "support_tickets_service_role" ON public.support_tickets
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ─── Faza 4.3 — Beta users — jednostavan founder-vodjen spisak ───────────────

CREATE TABLE IF NOT EXISTS public.beta_users (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text        NOT NULL UNIQUE,
    naziv_firme text,
    status      text        NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited','active','churned')),
    invited_at  timestamptz NOT NULL DEFAULT now(),
    napomena    text
);

ALTER TABLE public.beta_users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "beta_users_service_role" ON public.beta_users
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- Provera (opciono)
-- SELECT result_kind, count(*) FROM public.portal_status_log
--   WHERE created_at > now() - interval '24 hours' GROUP BY 1;
-- SELECT id, consecutive_failures, current_status FROM public.praceni_predmeti
--   ORDER BY consecutive_failures DESC LIMIT 10;
-- SELECT * FROM public.beta_users ORDER BY invited_at DESC;
-- ============================================================================
