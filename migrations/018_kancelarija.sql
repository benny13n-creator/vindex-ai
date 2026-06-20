-- migrations/018_kancelarija.sql
-- Phase 5.4: Multi-user firm account + role management
-- Pokrenuti u Supabase SQL Editor. Bezbedno za ponovni pokretanje (IF NOT EXISTS).

-- ─── kancelarije: law firm entity ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.kancelarije (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    naziv        TEXT        NOT NULL,
    admin_uid    TEXT        NOT NULL,   -- user_id of the firm admin
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kancelarije_admin ON public.kancelarije(admin_uid);
ALTER TABLE public.kancelarije ENABLE ROW LEVEL SECURITY;

-- Admin reads/updates own firm
DROP POLICY IF EXISTS "kancelrarija_admin_all" ON public.kancelarije;
CREATE POLICY "kancelrarija_admin_all" ON public.kancelarije
    USING (admin_uid = auth.uid()::text)
    WITH CHECK (admin_uid = auth.uid()::text);

-- Members can read their firm (via kancelarija_clanovi join — handled in backend)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.kancelarije TO service_role;


-- ─── kancelarija_clanovi: membership + invitations ───────────────────────────

CREATE TABLE IF NOT EXISTS public.kancelarija_clanovi (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kancelarija_id   UUID        NOT NULL REFERENCES public.kancelarije(id) ON DELETE CASCADE,
    email            TEXT        NOT NULL,
    user_id          TEXT,                   -- NULL until invitation accepted
    uloga            TEXT        NOT NULL DEFAULT 'saradnik'
                     CHECK (uloga IN ('admin', 'partner', 'saradnik', 'citanje')),
    status           TEXT        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'aktivan', 'odbijen')),
    invited_by       TEXT        NOT NULL,   -- user_id of inviter
    invited_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    joined_at        TIMESTAMPTZ,
    UNIQUE(kancelarija_id, email)
);

CREATE INDEX IF NOT EXISTS idx_kc_kancelarija ON public.kancelarija_clanovi(kancelarija_id);
CREATE INDEX IF NOT EXISTS idx_kc_email       ON public.kancelarija_clanovi(email);
CREATE INDEX IF NOT EXISTS idx_kc_user_id     ON public.kancelarija_clanovi(user_id);

ALTER TABLE public.kancelarija_clanovi ENABLE ROW LEVEL SECURITY;

-- Backend has full access
GRANT SELECT, INSERT, UPDATE, DELETE ON public.kancelarija_clanovi TO service_role;
