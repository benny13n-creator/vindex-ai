-- ============================================================================
-- Migration 136 -- Autonomous work: durable work items + atomic cycle claim
--
-- NS007 Tasks 1-2 (2026-10-10). PAD-001 G (beta autonomy = A2 Prepare / A3
-- Organize). Evidence: docs/v2-recovery/NS007_OVERNIGHT_EVIDENCE.md, Task 0-2.
--
-- WHY A NEW OWNER (Task 0, proven): no existing table has the full contract.
--   * agent_recommendations (082): pending/accepted/rejected only; no claim,
--     lease, retry, result, provenance, failure or dead-letter state; closed
--     agent_type CHECK. It stays the legacy recommendation/notification
--     surface; a work item MAY reference one (recommendation_id).
--   * staging_memory (088): lawyer approval gate for promoting drafts into
--     the knowledge base -- a narrower, different responsibility.
--   * v2_mutation_idempotency (134): HTTP replay protection, not jobs.
--
-- WHAT THIS IS
--   autonomy_cycles      one row per scheduler window. claim = INSERT; the
--                        UNIQUE window_key decides the single owner (no
--                        SELECT-then-INSERT). A RUNNING cycle is NEVER stolen:
--                        a stale one is visible (claimed_at, no finished_at)
--                        and the next window proceeds. Recovery of interrupted
--                        work happens one level lower, on work items.
--   autonomy_work_items  one row per logical trigger (UNIQUE user_id +
--                        dedupe_key). Lifecycle:
--                          QUEUED -> RUNNING -> READY_FOR_REVIEW -> ACCEPTED | REJECTED
--                          RUNNING -> FAILED       (honest, non-retryable: context
--                                                   gate, source verification)
--                          RUNNING (lease expired, attempts exhausted) -> DEAD_LETTER
--                          QUEUED | READY_FOR_REVIEW -> SUPERSEDED (trigger changed)
--                        No other states: each one has a distinct lifecycle
--                        meaning (FAILED = do not retry, DEAD_LETTER = retries
--                        exhausted, SUPERSEDED = kept, no longer current).
--
-- CLAIM + BUDGET = ONE TRANSACTION (autonomy_claim_work_item)
--   * row lock (FOR UPDATE) -> claimable only if QUEUED, or RUNNING with an
--     EXPIRED lease (crashed worker); attempt_count < max_attempts, else
--     DEAD_LETTER.
--   * PAID work: per-organization advisory transaction lock, then the day's
--     reserved units are counted and the unit is reserved BEFORE any model
--     call. Concurrent claims for the same org serialize on the lock, so the
--     count cannot be stale (no TOCTOU). If this function cannot run (DB
--     down), nothing is claimed -> no model call: fail-closed by construction.
--   * Exactly-once model execution is NOT possible: a worker can crash after
--     the provider charged and before the result is stored. Bound: every
--     attempt reserves one unit and PAID items default to max_attempts = 2,
--     so one logical work item can cost at most 2 model executions, then
--     DEAD_LETTER (visible). Never an infinite retry.
--
-- COMPLETION: application-side conditional UPDATE ... WHERE status='RUNNING'
--   AND lease_owner = <own token> -- only the current lease owner can store a
--   result; result + READY_FOR_REVIEW are written in ONE statement, so a
--   stored result is never "persisted but not ready".
--
-- MATTER DELETION: predmet_id -> predmeti ON DELETE CASCADE, deliberately the
--   same policy as agent_recommendations (082) and the canonical deletion
--   contract (shared/predmet_deletion.py, P15: deleting a matter is an
--   explicit lawyer action behind a tombstone that purges ALL matter data,
--   incl. staging_memory). Work products are matter content, not audit
--   history; the immutable lifecycle trail (IDs + safe classifications) lives
--   in audit_immutable and is not deleted. NS007 Task 26 re-reviews this.
--
-- CONFIDENTIALITY: content_json holds AI-prepared legal work for review
--   (plaintext, like case_dna/predmet_dokazi). NO source documents are copied
--   (source_refs = identifiers only), NO prompts, NO secrets, NO provider
--   credentials. Size-capped. No automatic retention deletion (NS007 Task 27:
--   requires a founder-approved policy).
--
-- ACCESS: RLS enabled. authenticated may SELECT only its own rows; NO
--   INSERT/UPDATE/DELETE policy -- system writes are service-role only and
--   lawyer review goes through the authenticated API. Explicit REVOKE from
--   PUBLIC/anon/authenticated (Supabase default privileges grant ALL).
--
-- Additive only. No existing object is modified.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.autonomy_cycles (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    window_key       TEXT        NOT NULL UNIQUE CHECK (window_key ~ '^[A-Za-z0-9:_.-]{1,80}$'),
    run_id           TEXT        NOT NULL CHECK (run_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    status           TEXT        NOT NULL DEFAULT 'RUNNING'
                                 CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    claimed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    counts           JSONB       NOT NULL DEFAULT '{}'::jsonb
                                 CHECK (octet_length(counts::text) <= 8000),
    safe_error_code  TEXT        CHECK (safe_error_code IS NULL OR safe_error_code ~ '^[A-Z0-9_]{1,64}$'),
    CONSTRAINT autonomy_cycles_finish_consistent CHECK (
        (status = 'RUNNING' AND finished_at IS NULL) OR (status <> 'RUNNING' AND finished_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS autonomy_cycles_claimed_idx ON public.autonomy_cycles (claimed_at DESC);

CREATE TABLE IF NOT EXISTS public.autonomy_work_items (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID        NOT NULL,
    kancelarija_id     UUID,
    predmet_id         UUID        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    case_action_id     UUID,
    recommendation_id  UUID        REFERENCES public.agent_recommendations(id) ON DELETE SET NULL,

    agent_type         TEXT        NOT NULL CHECK (agent_type IN ('hearing_prep', 'precedents_radar', 'case_evolution')),
    work_type          TEXT        NOT NULL CHECK (work_type IN ('HEARING_PREP', 'PRECEDENT_IMPACT', 'CASE_CHANGE_BRIEF')),
    trigger_type       TEXT        NOT NULL CHECK (trigger_type IN ('ROCISTE', 'PRECEDENT', 'GENOME_VERSION')),
    trigger_ref        TEXT        NOT NULL CHECK (char_length(trigger_ref) BETWEEN 1 AND 200),
    source_version     INTEGER     CHECK (source_version IS NULL OR source_version >= 0),
    dedupe_key         TEXT        NOT NULL CHECK (char_length(dedupe_key) BETWEEN 1 AND 300),
    reason             TEXT        NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 500),

    cost_class         TEXT        NOT NULL CHECK (cost_class IN ('PAID', 'FREE')),
    budget_key         TEXT        NOT NULL CHECK (char_length(budget_key) BETWEEN 1 AND 120),
    budget_units       INTEGER     NOT NULL DEFAULT 0 CHECK (budget_units >= 0),
    reserved_day       DATE,

    status             TEXT        NOT NULL DEFAULT 'QUEUED' CHECK (status IN (
                                       'QUEUED', 'RUNNING', 'READY_FOR_REVIEW', 'ACCEPTED', 'REJECTED',
                                       'FAILED', 'DEAD_LETTER', 'SUPERSEDED')),
    queued_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at         TIMESTAMPTZ,
    lease_owner        UUID,
    lease_expires_at   TIMESTAMPTZ,
    ready_at           TIMESTAMPTZ,
    resolved_at        TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count      INTEGER     NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts       INTEGER     NOT NULL DEFAULT 2 CHECK (max_attempts BETWEEN 1 AND 5),

    title              TEXT        CHECK (title IS NULL OR char_length(title) <= 300),
    summary            TEXT        CHECK (summary IS NULL OR char_length(summary) <= 2000),
    content_json       JSONB       CHECK (content_json IS NULL OR octet_length(content_json::text) <= 200000),
    source_refs        JSONB       NOT NULL DEFAULT '[]'::jsonb
                                   CHECK (jsonb_typeof(source_refs) = 'array' AND octet_length(source_refs::text) <= 50000),
    quality_state      TEXT        CHECK (quality_state IS NULL OR quality_state IN ('AI_PREPARED_FOR_REVIEW', 'DETERMINISTIC')),
    safe_error_code    TEXT        CHECK (safe_error_code IS NULL OR safe_error_code ~ '^[A-Z0-9_]{1,64}$'),
    reviewed_by        UUID,
    review_note        TEXT        CHECK (review_note IS NULL OR char_length(review_note) <= 1000),

    UNIQUE (user_id, dedupe_key),
    CONSTRAINT autonomy_work_running_has_lease CHECK (
        status <> 'RUNNING' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL AND claimed_at IS NOT NULL)
    ),
    CONSTRAINT autonomy_work_ready_has_product CHECK (
        status NOT IN ('READY_FOR_REVIEW', 'ACCEPTED', 'REJECTED')
        OR (title IS NOT NULL AND summary IS NOT NULL AND content_json IS NOT NULL
            AND quality_state IS NOT NULL AND ready_at IS NOT NULL)
    ),
    CONSTRAINT autonomy_work_reviewed_consistent CHECK (
        (status IN ('ACCEPTED', 'REJECTED')) = (resolved_at IS NOT NULL AND reviewed_by IS NOT NULL)
    ),
    CONSTRAINT autonomy_work_paid_reservation CHECK (
        (budget_units = 0) OR (cost_class = 'PAID' AND reserved_day IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS autonomy_work_user_status_idx
    ON public.autonomy_work_items (user_id, status, ready_at DESC);
CREATE INDEX IF NOT EXISTS autonomy_work_predmet_idx
    ON public.autonomy_work_items (predmet_id, status);
CREATE INDEX IF NOT EXISTS autonomy_work_claimable_idx
    ON public.autonomy_work_items (status, lease_expires_at) WHERE status IN ('QUEUED', 'RUNNING');
CREATE INDEX IF NOT EXISTS autonomy_work_budget_idx
    ON public.autonomy_work_items (budget_key, reserved_day) WHERE budget_units > 0;

ALTER TABLE public.autonomy_cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.autonomy_work_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS autonomy_work_items_own_select ON public.autonomy_work_items;
CREATE POLICY autonomy_work_items_own_select ON public.autonomy_work_items
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

REVOKE ALL ON public.autonomy_cycles FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.autonomy_work_items FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.autonomy_work_items TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.autonomy_cycles TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.autonomy_work_items TO service_role;

-- ----------------------------------------------------------------------------
-- autonomy_claim_work_item -- the ONLY way a work item becomes RUNNING.
-- Returns jsonb {"ishod": CLAIMED | NOT_FOUND | NOT_CLAIMABLE | DEAD_LETTER |
--                         BUDGET_EXHAUSTED | BUDGET_UNKNOWN, "item": {...}?}
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.autonomy_claim_work_item(
    p_id            UUID,
    p_owner         UUID,
    p_lease_seconds INTEGER,
    p_budget_limit  INTEGER
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    r       public.autonomy_work_items%ROWTYPE;
    v_today DATE := (now() AT TIME ZONE 'UTC')::date;
    v_used  BIGINT;
BEGIN
    IF p_owner IS NULL OR p_lease_seconds IS NULL OR p_lease_seconds < 30 OR p_lease_seconds > 3600 THEN
        RAISE EXCEPTION 'autonomy_claim_work_item: invalid owner/lease' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO r FROM public.autonomy_work_items WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ishod', 'NOT_FOUND');
    END IF;

    IF NOT (r.status = 'QUEUED' OR (r.status = 'RUNNING' AND r.lease_expires_at < now())) THEN
        RETURN jsonb_build_object('ishod', 'NOT_CLAIMABLE', 'status', r.status);
    END IF;

    IF r.attempt_count >= r.max_attempts THEN
        UPDATE public.autonomy_work_items
           SET status = 'DEAD_LETTER', safe_error_code = 'ATTEMPTS_EXHAUSTED',
               lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
         WHERE id = p_id;
        RETURN jsonb_build_object('ishod', 'DEAD_LETTER');
    END IF;

    IF r.cost_class = 'PAID' THEN
        -- A missing/invalid limit is NOT "unlimited": fail closed.
        IF p_budget_limit IS NULL OR p_budget_limit < 0 THEN
            RETURN jsonb_build_object('ishod', 'BUDGET_UNKNOWN');
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('autonomy-budget:' || r.budget_key, 0));
        SELECT COALESCE(SUM(budget_units), 0) INTO v_used
          FROM public.autonomy_work_items
         WHERE budget_key = r.budget_key AND reserved_day = v_today AND budget_units > 0;
        IF v_used >= p_budget_limit THEN
            RETURN jsonb_build_object('ishod', 'BUDGET_EXHAUSTED', 'used', v_used, 'limit', p_budget_limit);
        END IF;
    END IF;

    UPDATE public.autonomy_work_items
       SET status           = 'RUNNING',
           claimed_at       = now(),
           lease_owner      = p_owner,
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           attempt_count    = attempt_count + 1,
           budget_units     = CASE WHEN cost_class = 'PAID'
                                   THEN (CASE WHEN reserved_day = v_today THEN budget_units ELSE 0 END) + 1
                                   ELSE budget_units END,
           reserved_day     = CASE WHEN cost_class = 'PAID' THEN v_today ELSE reserved_day END,
           safe_error_code  = NULL,
           updated_at       = now()
     WHERE id = p_id
    RETURNING * INTO r;

    RETURN jsonb_build_object('ishod', 'CLAIMED', 'item', to_jsonb(r));
END;
$$;

REVOKE ALL ON FUNCTION public.autonomy_claim_work_item(UUID, UUID, INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.autonomy_claim_work_item(UUID, UUID, INTEGER, INTEGER) TO service_role;

COMMENT ON TABLE public.autonomy_work_items IS
    'NS007: durable autonomous work (A2 Prepare / A3 Organize). One row per logical trigger. '
    'AI content is AI_PREPARED_FOR_REVIEW, never a verified fact. Accept/reject are review decisions only: '
    'no external act, no filing, no send, no Law Brain promotion.';
COMMENT ON TABLE public.autonomy_cycles IS
    'NS007: one row per scheduler window; INSERT is the atomic claim. A RUNNING cycle is never stolen.';
