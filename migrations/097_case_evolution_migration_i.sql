-- ============================================================================
-- Vindex AI — Migration 097: Canonical Event Migration I (Program Delta,
-- Sprint 002, 2026-08-05)
--
-- REVIEW_REJECTED did not exist as a first-class outcome before this sprint
-- (Program Intake Sprint 004's own INTAKE-012, previously blocked on a
-- founder decision). This sprint's own charter requires ONE canonical
-- definition instead of leaving it undefined: rejecting a low-confidence
-- AI extraction/classification must NEVER let intake_jobs.status advance to
-- 'completed' (the same status finalize's own claim RPC gates on) — a
-- distinct terminal value is required so the CHECK constraint itself
-- enforces "rejected never silently becomes completed", not just app code.
--
-- Purely additive — widens the existing status CHECK constraint by one
-- value, does not touch any existing row or any other column. Located
-- dynamically via pg_constraint (not a hardcoded default-generated name)
-- so this migration is safe regardless of how Postgres actually named the
-- original inline CHECK from migration 073.
-- ============================================================================

DO $$
DECLARE
    con_name text;
BEGIN
    SELECT conname INTO con_name
    FROM pg_constraint
    WHERE conrelid = 'public.intake_jobs'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%status%IN%awaiting_review%';

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.intake_jobs DROP CONSTRAINT %I', con_name);
    END IF;
END $$;

ALTER TABLE public.intake_jobs
    ADD CONSTRAINT intake_jobs_status_check
    CHECK (status IN (
        'received', 'preprocessing', 'classifying', 'extracting',
        'matching', 'dedup_check', 'awaiting_review', 'completed', 'failed',
        'rejected'
    ));

COMMENT ON CONSTRAINT intake_jobs_status_check ON public.intake_jobs IS
    'rejected dodato u Program Delta Sprint 002 (2026-08-05) — REVIEW_REJECTED-ova kanonska definicija: covekovo odbijanje niske-pouzdanosti AI ekstrakcije/klasifikacije nikad ne sme preci u completed (finalize-ov status gate ostaje trajno zatvoren), razlicito od failed (tehnicki neuspeh obrade).';
