-- Vindex AI — migration 095: Intake Finalization Bulletproofing (Program Intake Sprint 007)
--
-- Closes the 3 remaining debts Sprint 006 named and deferred (INTAKE-018,
-- INTAKE-019, INTAKE-020). After this migration, Intake is a closed,
-- bulletproof subsystem: the same document can be uploaded any number of
-- times, processing can be interrupted at any point, the caller can retry
-- any number of times, and the system always ends with exactly one correct
-- document, one correct case, one lineage chain, one audit/provenance
-- record — never lost, never duplicated.

-- ─── Debt 1 (Cross-upload duplicate detection) + Debt 2 (Partial Failure
-- Retry) share ONE mechanism: a deterministic content identity for every
-- case-file document, checked before every insert. Debt 1 asks "was this
-- exact content already assimilated anywhere" (never filename/size/date);
-- Debt 2 asks "did THIS segment's own insert already happen, so a retry
-- must not repeat it" — both are the same question, answered by the same
-- lookup, scoped differently (same predmet_id = idempotent retry no-op;
-- different predmet_id = cross-case duplicate, routes to review).

ALTER TABLE public.predmet_dokumenti
    ADD COLUMN IF NOT EXISTS content_sha256 TEXT;

COMMENT ON COLUMN public.predmet_dokumenti.content_sha256 IS
    'Program Intake Sprint 007 — SHA-256 of the document''s own extracted text (never filename/size/upload-date, per the mission''s explicit instruction — those are not a deterministic document identity). Populated for every document assimilated from this sprint forward. Checked before every insert: a match under the SAME predmet_id is an idempotent retry no-op (no new document/lineage/audit/provenance); a match under a DIFFERENT predmet_id is a genuine cross-case duplicate, routed to review rather than guessed at.';

CREATE INDEX IF NOT EXISTS idx_predmet_dokumenti_content_sha256
    ON public.predmet_dokumenti(user_id, content_sha256)
    WHERE content_sha256 IS NOT NULL;

-- Generalizes Sprint 006's own `source_intake_job_segment_id` (segmented
-- jobs only) to EVERY document, segmented or not — closing Sprint 001's
-- original INTAKE-003 gap completely, and enabling crash recovery: if
-- finalize_intake_job crashes after creating case-file documents but
-- BEFORE writing intake_jobs.predmet_id (the durable completion marker,
-- deliberately written LAST — see migration 092's own claim_intake_finalize
-- rationale), a retried finalize call can recover the already-resolved
-- predmet_id from this column instead of creating a SECOND new case.
ALTER TABLE public.predmet_dokumenti
    ADD COLUMN IF NOT EXISTS source_intake_job_id UUID REFERENCES public.intake_jobs(id);

COMMENT ON COLUMN public.predmet_dokumenti.source_intake_job_id IS
    'Program Intake Sprint 007 — set for EVERY document assimilated via Smart Intake (Pipeline C), segmented or not (source_intake_job_segment_id, migration 094, is only ever set for Sprint-005-segmented jobs). Used by finalize_intake_job to recover an already-resolved predmet_id after a crash, before Ownership Resolution or predmet creation ever run again — the single mechanism that makes retrying an interrupted finalize call safe.';

CREATE INDEX IF NOT EXISTS idx_predmet_dokumenti_source_job
    ON public.predmet_dokumenti(source_intake_job_id)
    WHERE source_intake_job_id IS NOT NULL;

COMMENT ON TABLE public.predmet_dokumenti IS
    'Case-file documents. Program Intake Sprint 007: content_sha256 + source_intake_job_id together make document assimilation fully idempotent and crash-recoverable — see docs/architecture/RETRY_RELIABILITY_REPORT.md and DUPLICATE_DETECTION_REPORT.md.';

-- Debt 3 (Case Number Normalization) needs no schema change — predmeti.
-- broj_predmeta (migration 094) already exists; this sprint changes only
-- shared/case_assimilation.py::normalize_case_number() to a real canonical
-- parser (prefix + number + year, format-insensitive) instead of a
-- whitespace-collapse-only placeholder. See
-- docs/architecture/CASE_NUMBER_NORMALIZATION_SPECIFICATION.md.


-- ─── Debt 2 continued: a job whose finalize call completed WITHOUT a hard
-- crash, but with one or more documents genuinely failing to link (a soft
-- partial failure — e.g. transient DB errors, not a process crash), still
-- durably writes intake_jobs.predmet_id at the end (Sprint 006's own
-- honest-reporting fix already logs this, but does not prevent the write).
-- Before this migration, claim_intake_finalize's own WHERE clause
-- (`predmet_id IS NULL`, migration 092) treated ANY set predmet_id as "this
-- job is permanently done" — meaning a retry could NEVER resume a job with
-- some documents still unlinked, only a job that crashed before predmet_id
-- was written at all. This closes that gap: a job is only truly done once
-- assimilation_complete is explicitly true (set by finalize_intake_job only
-- when every one of its documents ended up linked), so claim_intake_finalize
-- can now correctly reclaim BOTH kinds of interruption — hard crash
-- (predmet_id still NULL) and soft partial failure (predmet_id set,
-- assimilation_complete still false).

ALTER TABLE public.intake_jobs
    ADD COLUMN IF NOT EXISTS assimilation_complete BOOLEAN NOT NULL DEFAULT false;

-- One-time backfill: any job finalized by pre-Sprint-007 code already has
-- ALL of its (pre-Sprint-005, always-exactly-one) documents linked by
-- definition -- there was no partial-failure concept before this sprint,
-- so a set predmet_id from that era is trustworthy as "fully done." Only
-- relevant if this migration runs against a database with pre-existing
-- finalized jobs; a no-op otherwise. Without this backfill, every
-- already-finalized job would default to assimilation_complete=false and
-- become spuriously reclaimable by claim_intake_finalize below.
UPDATE public.intake_jobs SET assimilation_complete = true WHERE predmet_id IS NOT NULL;

COMMENT ON COLUMN public.intake_jobs.assimilation_complete IS
    'Program Intake Sprint 007 — true only once finalize_intake_job confirms EVERY document it produced (Sprint 005 segments, or the single common-case document) is linked into predmet_dokumenti. False (the default) means retryable, whether the job never got a predmet_id at all (hard crash) or got one but some documents are still unlinked (soft partial failure) — claim_intake_finalize below treats both as reclaimable.';

CREATE OR REPLACE FUNCTION public.claim_intake_finalize(
    p_job_id              UUID,
    p_stale_after_seconds INTEGER DEFAULT 120
) RETURNS SETOF public.intake_jobs
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.intake_jobs
    SET finalizing_at = now()
    WHERE id = (
        SELECT id FROM public.intake_jobs
        WHERE id = p_job_id
          AND assimilation_complete = false
          AND (finalizing_at IS NULL
               OR finalizing_at < now() - (p_stale_after_seconds || ' seconds')::interval)
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;

COMMENT ON FUNCTION public.claim_intake_finalize IS
    'Program Intake Sprint 007 — WHERE clause changed from `predmet_id IS NULL` (migration 092) to `assimilation_complete = false`, so a job that durably wrote predmet_id but still has unlinked documents (a soft partial failure, not just a hard crash) remains reclaimable. Same SELECT...FOR UPDATE SKIP LOCKED shape, unchanged.';

REVOKE ALL ON FUNCTION public.claim_intake_finalize(UUID, INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_intake_finalize(UUID, INTEGER) TO service_role;
