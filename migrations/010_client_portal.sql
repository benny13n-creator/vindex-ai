-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 010 — Client Portal Tokens
-- Pokrenuti u Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.client_portal_tokens (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id    TEXT        NOT NULL,
    user_id       TEXT        NOT NULL,
    token_hash    TEXT        NOT NULL UNIQUE,
    klijent_email TEXT,
    is_active     BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cpt_predmet ON public.client_portal_tokens(predmet_id);
CREATE INDEX IF NOT EXISTS idx_cpt_user    ON public.client_portal_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_cpt_hash    ON public.client_portal_tokens(token_hash);

ALTER TABLE public.client_portal_tokens ENABLE ROW LEVEL SECURITY;

-- Advokat čita i upravlja samo sopstvenim tokenima
DROP POLICY IF EXISTS "cpt_select_own" ON public.client_portal_tokens;
CREATE POLICY "cpt_select_own" ON public.client_portal_tokens
    FOR SELECT USING (user_id = auth.uid()::text);

DROP POLICY IF EXISTS "cpt_update_own" ON public.client_portal_tokens;
CREATE POLICY "cpt_update_own" ON public.client_portal_tokens
    FOR UPDATE USING (user_id = auth.uid()::text);

-- Backend (service_role) ima pun pristup
GRANT SELECT, INSERT, UPDATE ON public.client_portal_tokens TO service_role;
