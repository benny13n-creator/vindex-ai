-- ============================================================================
-- Vindex AI — Migration 106: unique document-sequence-number constraint
-- Program Phoenix, Mission 011 (2026-08-08)
--
-- LIVINGSYS-DEBT-044: routers/smart_intake.py's finalize() computes the next
-- redni_broj (document sequence number, used in AI-generated DOK-NN citations)
-- via a plain SELECT MAX+1 in Python with no locking, fetched once before its
-- document loop and incremented only in-process. Correct within a single
-- finalize call, but two concurrent finalize calls to the SAME predmet_id
-- (two jobs, or a retried request landing on a different gunicorn worker --
-- this app runs 4, see gunicorn.conf.py) can both compute the same next
-- number, producing two documents that cite as the same DOK-NN -- a citation-
-- ambiguity risk in AI-generated legal analysis, not data loss.
--
-- This migration makes the invariant the application code already assumes
-- ("redni_broj is unique per case") a real, DB-enforced guarantee, so the
-- paired application fix in routers/smart_intake.py (retry-on-conflict, same
-- idiom as migration 104's billing.py fix) has something to actually conflict
-- against. redni_broj is nullable (ADD COLUMN IF NOT EXISTS in migration 105)
-- -- a plain unique index permits multiple NULLs under standard Postgres
-- semantics, so rows predating this column's introduction are unaffected.
--
-- Per this repository's standing convention, this migration is DRAFTED and
-- committed but NOT applied automatically — the founder runs it manually in
-- the Supabase SQL editor, same as migrations 089/102/103/104 before it.
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS predmet_dokumenti_predmet_redni_unique
    ON public.predmet_dokumenti (predmet_id, redni_broj);
