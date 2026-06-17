-- migrations/007_ingest_jobs.sql
-- Phase 5.2: Batch ingest job tracking table.
-- Safe to re-run (IF NOT EXISTS everywhere).
-- Run in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by    TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending',
    namespace     TEXT        NOT NULL DEFAULT 'sudska_praksa',
    source        TEXT,
    total_docs    INTEGER     NOT NULL DEFAULT 0,
    processed     INTEGER     NOT NULL DEFAULT 0,
    failed_docs   INTEGER     NOT NULL DEFAULT 0,
    error_msg     TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    CONSTRAINT ingest_jobs_status_check
        CHECK (status IN ('pending','running','done','failed'))
);

ALTER TABLE ingest_jobs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'ingest_jobs'
          AND policyname = 'service_role_ingest_jobs'
    ) THEN
        CREATE POLICY "service_role_ingest_jobs" ON ingest_jobs
            USING (true)
            WITH CHECK (true);
    END IF;
END$$;
