-- migrations/017_scraper_state.sql
-- Phase 5.2: Auto-scraper state — tracking discovered court bilteni.
-- Safe to re-run (IF NOT EXISTS everywhere).
-- Run in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS discovered_bilteni (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url          TEXT        NOT NULL UNIQUE,
    court        TEXT        NOT NULL,           -- 'vks' | 'as_bg' | 'as_nis' | 'as_kg' ...
    filename     TEXT        NOT NULL,
    label        TEXT        NOT NULL,
    size_bytes   INTEGER,
    status       TEXT        NOT NULL DEFAULT 'discovered',
    ingest_job_id UUID       REFERENCES ingest_jobs(id) ON DELETE SET NULL,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingested_at  TIMESTAMPTZ,
    error_msg    TEXT,
    CONSTRAINT discovered_bilteni_status_check
        CHECK (status IN ('discovered','downloading','ingested','failed','skipped'))
);

CREATE INDEX IF NOT EXISTS idx_discovered_bilteni_status ON discovered_bilteni(status);
CREATE INDEX IF NOT EXISTS idx_discovered_bilteni_court  ON discovered_bilteni(court);

ALTER TABLE discovered_bilteni ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename  = 'discovered_bilteni'
          AND policyname = 'service_role_discovered_bilteni'
    ) THEN
        CREATE POLICY "service_role_discovered_bilteni" ON discovered_bilteni
            USING (true)
            WITH CHECK (true);
    END IF;
END$$;
