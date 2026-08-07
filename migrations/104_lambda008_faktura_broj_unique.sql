-- ============================================================================
-- Vindex AI — Migration 104: unique invoice-number constraint
-- Program Lambda, Final Certification 008 (2026-08-07)
--
-- LAMBDA008-CONC-003: routers/billing.py::_sledeci_broj_fakture computes the
-- next invoice number via a plain SELECT MAX+1 in Python with no locking, and
-- `fakture` has never had a uniqueness guarantee on broj_fakture — two
-- concurrent invoice creations (double-click, or two browser tabs) can
-- silently produce two invoices with the identical broj_fakture, a Serbian
-- sequential-invoice-numbering compliance defect, not just a cosmetic bug.
--
-- A DB-side RPC (get_next_broj_fakture, migrations/003_billing.sql:107-119)
-- already existed for this but was confirmed dead code (never called from
-- Python — independently re-confirmed by this certification, RLS_CERTIFICATION
-- .md:61) and was itself non-atomic anyway (plain SELECT COUNT, no locking).
-- This migration does not attempt to fix that RPC; it instead makes the
-- invariant the application code already assumes ("broj_fakture is unique per
-- firm") a real, DB-enforced guarantee, so the paired application fix in
-- routers/billing.py (retry-on-conflict) has something to actually conflict
-- against.
--
-- Per this repository's standing convention, this migration is DRAFTED and
-- committed but NOT applied automatically — the founder runs it manually in
-- the Supabase SQL editor, same as migrations 089/102/103 before it.
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS fakture_user_broj_unique
    ON public.fakture (user_id, broj_fakture);
