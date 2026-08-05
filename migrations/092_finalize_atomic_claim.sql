-- -*- coding: utf-8 -*-
-- Vindex AI — migrations/092_finalize_atomic_claim.sql
--
-- Program Intake Sprint 002 (2026-08-05) — "Atomic Document Lifecycle"
--
-- DRAFTED, NOT applied — founder runs migrations himself (standing project
-- convention). Do not auto-apply.
--
-- Fixes the sprint's single most severe, independently-confirmed-3x finding
-- (Sprint 002 Fork A §C-bonus, Fork B §3.4, Fork C Phase 5 #4):
-- routers/smart_intake.py::finalize_intake_job's own idempotency guard reads
-- intake_jobs.predmet_id, but that column is only WRITTEN as the LAST,
-- unwrapped statement in a 700-line function, after 6-8 other independently-
-- committed writes (predmet, client, deadline, document, Pinecone vectors)
-- have already run. Two finalize calls for the same job_id close enough
-- together (double-click, or a frontend timeout retry while the first call
-- is still running server-side) both read predmet_id=NULL, both pass, and
-- both run the ENTIRE body independently -- producing a silently duplicated,
-- fully-formed legal case with no intake_jobs row ever pointing back to the
-- loser's object graph. This is a strictly worse shape than the already-
-- tracked INTAKE-001/INTAKE-002 (those lose or mis-signal one artifact; this
-- silently creates one full duplicate case).
--
-- Fix mirrors the ALREADY-PROVEN pattern one file over in this exact
-- migration set: enqueue_intake_job's own idempotency-key check-and-insert
-- is atomic (migration 073); claim_intake_job's SELECT...FOR UPDATE SKIP
-- LOCKED is atomic (migration 073). Finalize never received the equivalent
-- treatment for its own completion marker -- this migration gives it one,
-- using the exact same RPC shape (PostgREST exposes no row-lock semantics
-- directly, hence RPC), not a new mechanism.

ALTER TABLE public.intake_jobs ADD COLUMN IF NOT EXISTS finalizing_at TIMESTAMPTZ;

COMMENT ON COLUMN public.intake_jobs.finalizing_at IS
    'Program Intake Sprint 002 -- set by claim_intake_finalize() RPC the instant a finalize call begins running the case-creation side effects, cleared (set back to NULL) is NOT required for correctness -- a stale claim (older than the staleness window passed to the RPC) is simply reclaimable again, same self-healing shape as claimed_at/reap_stale_jobs one column over. NULL means "no finalize attempt is currently in flight for this job."';

-- ── claim_intake_finalize — atomic check-and-claim for finalize's own
-- completion marker, mirrors claim_intake_job's SELECT...FOR UPDATE SKIP
-- LOCKED pattern exactly. Returns the claimed row (finalizing_at freshly
-- set) if this call won the claim; returns zero rows if:
--   (a) predmet_id is already set (this job was already finalized), or
--   (b) another finalize call's claim is still fresh (within
--       p_stale_after_seconds -- a genuinely-still-running concurrent call,
--       not a crashed one), or
--   (c) a concurrent transaction currently holds the row lock (SKIP LOCKED
--       -- another claim attempt is resolving literally right now).
-- The caller (routers/smart_intake.py) must re-fetch the job row on a
-- zero-row result to distinguish (a) "already finalized, return existing
-- predmet_id" from (b)/(c) "finalize in progress, ask the caller to retry
-- shortly" -- these are different, both-honest responses, not the same
-- outcome.

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
          AND predmet_id IS NULL
          AND (finalizing_at IS NULL
               OR finalizing_at < now() - (p_stale_after_seconds || ' seconds')::interval)
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;

COMMENT ON FUNCTION public.claim_intake_finalize IS
    'Program Intake Sprint 002 -- atomic check-and-claim for finalize_intake_job''s own completion marker, same SELECT...FOR UPDATE SKIP LOCKED shape as claim_intake_job (migration 073). Prevents the concurrent-retry duplicate-case defect (Fork A §C-bonus / Fork B §3.4 / Fork C Phase 5 #4, all 2026-08-05) by making "is a finalize already in flight for this job" an atomic question instead of a plain SELECT the caller could race against itself.';

REVOKE ALL ON FUNCTION public.claim_intake_finalize(UUID, INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_intake_finalize(UUID, INTEGER) TO service_role;
