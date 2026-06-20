-- migrations/021_email_notif.sql
-- Email notifikacije za kritične rokove.
-- Pokrenuti u Supabase SQL Editor. Bezbedno za ponovni pokretanje.

CREATE TABLE IF NOT EXISTS public.korisnik_email_notif (
    user_id     TEXT        PRIMARY KEY,
    aktivan     BOOLEAN     NOT NULL DEFAULT true,
    dan_7       BOOLEAN     NOT NULL DEFAULT true,   -- podsetnik 7 dana pre
    dan_3       BOOLEAN     NOT NULL DEFAULT true,   -- podsetnik 3 dana pre
    dan_1       BOOLEAN     NOT NULL DEFAULT true,   -- podsetnik 1 dan pre
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.korisnik_email_notif ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "email_notif_own" ON public.korisnik_email_notif;
CREATE POLICY "email_notif_own" ON public.korisnik_email_notif
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.korisnik_email_notif TO service_role;

-- Tracking sent emails (sprečava duplikate)
CREATE TABLE IF NOT EXISTS public.email_notif_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL,
    predmet_id  TEXT        NOT NULL,
    datum_roka  DATE        NOT NULL,
    dana_pre    SMALLINT    NOT NULL,   -- 7, 3 ili 1
    poslato_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, predmet_id, datum_roka, dana_pre)
);

CREATE INDEX IF NOT EXISTS idx_email_log_user ON public.email_notif_log(user_id, poslato_at DESC);
ALTER TABLE public.email_notif_log ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON public.email_notif_log TO service_role;
