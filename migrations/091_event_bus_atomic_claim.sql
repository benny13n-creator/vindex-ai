-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 091 — Event Bus Atomic Claim (Mission Keystone, 2026-08-04)
-- ═══════════════════════════════════════════════════════════════════════════
--
-- FINDING (Keystone Phase 1 + Phase 4 investigation, 2026-08-04): production
-- runs gunicorn with 4 worker processes by default (gunicorn.conf.py:
-- `workers = int(os.getenv("WEB_CONCURRENCY", 4))`), and EACH worker process
-- runs its own independent services/event_bus.py::DispatchLoop polling the
-- SAME 'events' table every 3s via a plain, unclaimed
-- `SELECT * FROM events WHERE dispatched_at IS NULL ORDER BY created_at LIMIT n`.
--
-- Project Phoenix (2026-08-03) fixed handler-failure DETECTION (re-raise +
-- dead-letter cap) but implicitly assumed a single dispatch-loop instance —
-- it never examined multi-worker concurrency. With 4 workers, the same
-- undispatched row can be selected by 2+ workers in the same 3s tick, each
-- independently re-running non-idempotent handlers (on_rok_kritican,
-- on_health_score_promenjen, on_document_job_failed, on_genome_updated all
-- unconditionally INSERT a new row on every call) — duplicate
-- proactive_alerts rows or duplicate audit_immutable entries for one real
-- business event. Same root cause Smart Intake already solved for
-- intake_jobs (migration 073's claim_intake_job): PostgREST (the Supabase
-- client library) does not expose SELECT ... FOR UPDATE SKIP LOCKED directly,
-- so the safe claim has to happen inside a SECURITY DEFINER RPC.
--
-- This migration mirrors that exact, already-proven pattern for 'events'.
--
-- Application-side (services/event_bus.py::dispatch_pending_events): tries
-- this RPC first; if it's not yet deployed (migration not run), falls back
-- to the pre-existing plain-SELECT behavior unchanged (same "try new path,
-- graceful fallback on missing function" convention already used throughout
-- this engagement for schema-dependent features) — so application behavior
-- is identical to before until this migration is actually run.
--
-- Per standing project convention: this migration is DRAFTED, NOT applied.
-- The founder runs migrations himself.
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE public.events ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;

COMMENT ON COLUMN public.events.claimed_at IS
    'Set by claim_pending_events() RPC at claim time, cleared back to NULL on a non-exhausted retry (so the existing ~3s fast-retry cadence is unchanged) — distinct from dispatched_at, which means "done, one way or another" (success or dead-letter). A row stuck with a non-NULL claimed_at and NULL dispatched_at for longer than p_stale_claim_seconds is reclaimable again (a worker that crashed mid-dispatch, mirroring intake_jobs'' reaper concept, kept intentionally simple here — no separate reaper process, the claim query itself re-includes stale claims).';

CREATE INDEX IF NOT EXISTS idx_events_claimable
    ON public.events(created_at) WHERE dispatched_at IS NULL;

-- ── claim_pending_events — SELECT FOR UPDATE SKIP LOCKED preko RPC ─────────
CREATE OR REPLACE FUNCTION public.claim_pending_events(
    p_batch_size          INT DEFAULT 25,
    p_stale_claim_seconds INT DEFAULT 30
) RETURNS SETOF public.events
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.events
    SET claimed_at = now()
    WHERE id IN (
        SELECT id FROM public.events
        WHERE dispatched_at IS NULL
          AND (claimed_at IS NULL OR claimed_at < now() - make_interval(secs => p_stale_claim_seconds))
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT p_batch_size
    )
    RETURNING *;
END;
$$;

COMMENT ON FUNCTION public.claim_pending_events IS
    'Mission Keystone (2026-08-04) -- atomic multi-row claim for the durable Event Bus outbox, same rationale as migration 073''s claim_intake_job: SELECT ... FOR UPDATE SKIP LOCKED is the only safe way for N concurrent gunicorn workers'' independent DispatchLoops to split one batch of undispatched events without double-processing a row.';

REVOKE ALL ON FUNCTION public.claim_pending_events(INT, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_pending_events(INT, INT) TO service_role;
