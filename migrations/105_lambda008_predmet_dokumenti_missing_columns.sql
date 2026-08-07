-- ============================================================================
-- Vindex AI — Migration 105: capture predmet_dokumenti's undocumented columns
-- Program Lambda, Final Certification 008 (2026-08-07)
--
-- LAMBDA008-SCHEMA-001: `redni_broj` (document sequence number, DOK-01/DOK-02..)
-- and `tekst_sadrzaj` (extracted document text, used for search/AI context) are
-- both load-bearing columns on predmet_dokumenti, read and written unconditionally
-- across api.py, routers/drafting.py, routers/smart_intake.py, routers/case_dna.py,
-- routers/copilot.py, routers/multi_agent.py — but neither is created by any
-- migration file or by supabase_setup.sql's own CREATE TABLE (supabase_setup.sql:
-- 336-346). They were added directly to live Supabase outside the tracked
-- migration system at some point; api.py:4359 even carries a comment referencing a
-- migration ("ALTER TABLE predmet_dokumenti ADD COLUMN tekst_sadrzaj TEXT") that
-- does not exist in this repo. A fresh environment built from migrations/ alone
-- would break document upload/citation numbering entirely.
--
-- IF NOT EXISTS makes this safe to run against the live database (which almost
-- certainly already has both columns, given the app functions today) — it exists
-- to make the schema reproducible from this repo, not to change live behavior.
-- ============================================================================

ALTER TABLE public.predmet_dokumenti
    ADD COLUMN IF NOT EXISTS redni_broj    INTEGER,
    ADD COLUMN IF NOT EXISTS tekst_sadrzaj TEXT;
