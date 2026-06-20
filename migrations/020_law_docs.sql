-- migrations/020_law_docs.sql
-- Law database expansion: tracking uploaded/ingested law PDFs.
-- Pokrenuti u Supabase SQL Editor. Bezbedno za ponovni pokretanje.

CREATE TABLE IF NOT EXISTS public.law_docs (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    naziv              TEXT         NOT NULL,
    broj_sl_glasnika   TEXT         NOT NULL DEFAULT '',
    filename           TEXT         NOT NULL,
    size_bytes         INTEGER,
    status             TEXT         NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','running','done','failed','obrisan')),
    vektori_upserted   INTEGER      NOT NULL DEFAULT 0,
    ukupno_chunkova    INTEGER      NOT NULL DEFAULT 0,
    uploaded_by        TEXT         NOT NULL,   -- user_id of uploader (admin)
    greska             TEXT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ingested_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_law_docs_status ON public.law_docs(status);
CREATE INDEX IF NOT EXISTS idx_law_docs_created ON public.law_docs(created_at DESC);

ALTER TABLE public.law_docs ENABLE ROW LEVEL SECURITY;

-- Samo service_role (backend) ima pristup — admini pristupaju via API
GRANT SELECT, INSERT, UPDATE, DELETE ON public.law_docs TO service_role;
