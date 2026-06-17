-- migrations/013_client_portal_uploads.sql
-- Vindex AI — Klijentski portal: upload dokumenata od strane klijenta
--
-- NAPOMENA: Pre pokretanja kreirajte Supabase Storage bucket:
--   Dashboard → Storage → New bucket → Ime: "portal-uploads" → Private
--
-- Pokrenuti jednom u Supabase SQL editor.

CREATE TABLE IF NOT EXISTS client_portal_uploads (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id      TEXT        NOT NULL,
    advokat_user_id TEXT        NOT NULL,
    token_hash      TEXT        NOT NULL,
    fajl_naziv      TEXT        NOT NULL,
    fajl_velicina   BIGINT      NOT NULL DEFAULT 0,
    content_type    TEXT,
    storage_path    TEXT,
    napomena        TEXT,
    pregledano      BOOLEAN     NOT NULL DEFAULT false,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cpu_predmet   ON client_portal_uploads(predmet_id);
CREATE INDEX IF NOT EXISTS idx_cpu_advokat   ON client_portal_uploads(advokat_user_id);
CREATE INDEX IF NOT EXISTS idx_cpu_token     ON client_portal_uploads(token_hash);
CREATE INDEX IF NOT EXISTS idx_cpu_uploaded  ON client_portal_uploads(uploaded_at DESC);

-- RLS: advokat vidi samo svoje uploadove
ALTER TABLE client_portal_uploads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "advokat_vidi_svoje_uploade" ON client_portal_uploads
    FOR SELECT USING (advokat_user_id = auth.uid()::text);

CREATE POLICY "advokat_brise_svoje_uploade" ON client_portal_uploads
    FOR DELETE USING (advokat_user_id = auth.uid()::text);

-- Klijent insert ide kroz service-role (backend bypasses RLS)
-- SELECT/DELETE za advokata idu kroz JWT → RLS
