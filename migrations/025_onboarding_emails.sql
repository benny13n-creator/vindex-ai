-- Migration 025: Onboarding email sekvenca
-- Tabela za praćenje poslanih onboarding emailova (dedup + analytics)

CREATE TABLE IF NOT EXISTS public.onboarding_email_log (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tip          TEXT NOT NULL,   -- 'welcome' | 'day1' | 'day3'
    poslato_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email        TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS onboarding_email_log_uq
    ON public.onboarding_email_log (user_id, tip);

ALTER TABLE public.onboarding_email_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "onboarding_log_founder_only" ON public.onboarding_email_log
    USING (FALSE);  -- samo service_role čita/piše

-- profiles tabela: dodaj registered_at ako ne postoji (fallback na created_at)
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS registered_at TIMESTAMPTZ DEFAULT NOW();
