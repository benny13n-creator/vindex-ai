-- ============================================================================
-- Migration 131 -- Atomic source invalidation (evidence/rociste/dokument)
--
-- RENUMBERED (Wave 2 mainline integration, 2026-09-20): authored and
-- production-applied as migration 130 on the isolated Wave 2 branch
-- (v1-wave2-case-evolution-integrity) -- see that branch's
-- V1-WAVE2-CASE-EVOLUTION-INTEGRITY-REPORT.md for the full review record.
-- Renumbered to 131 here only because migration number 129 (not 130) is
-- what actually collided with current main; 130 was free, but shifted by
-- one to keep this migration immediately after the also-renumbered
-- events_outbox_metrics fix (130) for a clean, readable sequence. SQL body
-- byte-identical to the original 130 (including the search_path hardening
-- already applied during the Wave 2 production gate); already applied to
-- production under that number -- CREATE OR REPLACE FUNCTION is
-- idempotent, so re-running this file (now under 131) is a safe no-op
-- reconciliation, not a destructive recreate.
--
-- VINDEX AI V1, Wave 2, Task 2D corrective closure (VINDEX-V1-EXECUTION-
-- CONTRACT.md). Founder's own review of the original Task 2D report
-- correctly rejected it: routers/evidence.py::delete_dokaz, routers/
-- rocista.py::obrisi_rociste, and api.py's document-delete endpoint each
-- performed their relational mutation, THEN made a separate, best-effort
-- services/event_bus.py::emit_source_invalidated() call. A process crash
-- between those two network round-trips leaves the source deleted with NO
-- SOURCE_INVALIDATED event ever recorded -- permanently stale derived
-- state until some UNRELATED later event happens to touch the same
-- matter, which is not an integrity guarantee.
--
-- FIX: for the two DB-contained sources (evidence, rociste), the
-- relational mutation and the durable events-table insert now happen
-- inside ONE PL/pgSQL function -- one implicit transaction, same pattern
-- already established by enqueue_intake_job() (migration 073, "isti
-- obrazac kao deduct_credit()/deduct_n_credits()"). Either both commit or
-- neither does; there is no network round-trip between them for a crash
-- to land in.
--
-- For the document, per the founder's own explicit instruction: Postgres
-- and object storage cannot share one ACID transaction, so the
-- authoritative Case Evolution invalidation boundary is defined as the
-- RELATIONAL delete of predmet_dokumenti -- made atomic with the event
-- exactly like the other two. Vector (Pinecone) and object-storage
-- cleanup remain OUTSIDE this transaction, unchanged in their own
-- existing order and failure handling (api.py's own pre-existing
-- non-blocking storage_ishod reporting) -- this migration does not touch
-- them.
--
-- Idempotency: the caller supplies a deterministic event_id (uuid5 from a
-- fixed namespace + "source_type:source_id", services/event_bus.py::
-- _source_invalidation_event_id -- UNCHANGED from the original Task 2D
-- implementation). `ON CONFLICT (id) DO NOTHING` on the events table's
-- own PRIMARY KEY (migration 073) means a duplicate/retried call for the
-- SAME source is a safe no-op on the event -- concurrent/duplicate calls
-- cannot produce two logical invalidation events, regardless of how many
-- times the underlying mutation itself succeeds. The mutation's own
-- WHERE clause deliberately has NO "already invalidated" guard for
-- evidence (no `deleted_at IS NULL`) -- this preserves routers/
-- evidence.py's pre-existing contract that re-deleting an already-soft-
-- deleted dokaz still matches and stays a truthful success, not a
-- fabricated 404 (tests/test_v44_delete_dokaz_guard.py::test_5_repeated_
-- delete_stays_200_not_zero_row). For rociste/dokument, a repeat call
-- naturally finds nothing (the row is hard-deleted) and returns
-- invalidated=FALSE, matching each endpoint's pre-existing "already
-- absent -> 404" contract.
--
-- Security: SECURITY DEFINER on all three, matching every other RPC in
-- this file family (claim_intake_job's own migration-073 comment records
-- WHY this is required -- without it, UPDATE/DELETE ... RETURNING is
-- subject to the CALLING context's RLS SELECT policy and can silently
-- return no row even though the write itself succeeded). REVOKE ALL FROM
-- PUBLIC + GRANT EXECUTE TO service_role only, same as every existing RPC
-- -- these are called exclusively by backend code holding the service_role
-- key, never exposed to anon/authenticated directly. Ownership (user_id)
-- is still enforced INSIDE each function's own WHERE clause, exactly the
-- same predicate each endpoint already applied client-side -- authorization
-- is not weakened or moved to a client-supplied trust boundary.
--
-- SET search_path = '' (Wave 2 Task 2D production-gate review, 2026-09-20)
-- -- the standard Postgres/Supabase SECURITY DEFINER hardening this file's
-- own precedent (migration 073) did not carry, added here on review since
-- "same pattern as an existing RPC" is not itself proof of safety for a
-- NEW SECURITY DEFINER surface. Safe with an empty search_path because
-- every object reference in all 3 bodies is already schema-qualified
-- (public.predmet_dokazi/rocista/predmet_dokumenti/events) -- pg_catalog
-- (now(), jsonb_build_object()) is always implicitly searched regardless
-- of this setting, so no built-in call is affected. This closes the
-- classic SECURITY DEFINER search-path-hijack class (an object created in
-- a schema earlier in an attacker-influenced search_path silently
-- shadowing an unqualified reference) at zero behavior change.
--
-- Event identity, verified on this same review (not assumed): p_event_id
-- is a CALLER-supplied UUID (services/event_bus.py::
-- _source_invalidation_event_id, a deterministic uuid5 of the fixed
-- namespace + "source_type:source_id"), inserted verbatim as events.id --
-- never server-generated (no gen_random_uuid() call anywhere in this
-- file). Two concurrent calls invalidating the SAME logical source always
-- compute the identical event_id in Python before either reaches this
-- function, so they collide on events' own PRIMARY KEY and `ON CONFLICT
-- (id) DO NOTHING` correctly leaves exactly one event row -- this is
-- PRIMARY KEY (deterministic logical identity), not PRIMARY KEY (random
-- per-call uuid); the latter would NOT have deduplicated concurrent calls
-- and was the one shape that would have failed this review.
-- ============================================================================


CREATE OR REPLACE FUNCTION public.invalidate_dokaz_and_emit_event(
    p_dokaz_id       TEXT,
    p_user_id        TEXT,
    p_event_id       UUID,
    p_correlation_id TEXT DEFAULT NULL
) RETURNS TABLE(predmet_id TEXT, invalidated BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_predmet_id TEXT;
BEGIN
    -- No `deleted_at IS NULL` predicate, deliberately: routers/evidence.py's
    -- own pre-existing contract (tests/test_v44_delete_dokaz_guard.py::
    -- test_5_repeated_delete_stays_200_not_zero_row) is that re-deleting an
    -- already-soft-deleted dokaz still matches (id+user_id) and stays a
    -- truthful 200, not a fabricated 404 -- "already obrisan" is a true
    -- statement about end state, not a zero-row case. Preserving that
    -- UNCHANGED; only the transaction boundary is this task's own concern.
    -- Event-level idempotency (no duplicate recompute from a repeat call)
    -- is still guaranteed below by the deterministic event_id + ON
    -- CONFLICT DO NOTHING, independent of this predicate.
    UPDATE public.predmet_dokazi AS pd
        SET deleted_at = now()
        WHERE pd.id = p_dokaz_id
          AND pd.user_id = p_user_id
        RETURNING pd.predmet_id INTO v_predmet_id;

    IF v_predmet_id IS NULL THEN
        RETURN QUERY SELECT NULL::TEXT, FALSE;
        RETURN;
    END IF;

    INSERT INTO public.events (id, event_type, user_id, predmet_id, payload, correlation_id)
    VALUES (
        p_event_id, 'SourceInvalidated', p_user_id, v_predmet_id,
        jsonb_build_object('source_type', 'dokaz', 'source_id', p_dokaz_id, 'correlation_id', p_correlation_id),
        p_correlation_id
    )
    ON CONFLICT (id) DO NOTHING;

    RETURN QUERY SELECT v_predmet_id, TRUE;
END;
$$;

COMMENT ON FUNCTION public.invalidate_dokaz_and_emit_event IS
    'Wave 2 Task 2D corrective closure -- atomic soft-delete of predmet_dokazi + durable SourceInvalidated event, one transaction. Same pattern as enqueue_intake_job() (migration 073).';


CREATE OR REPLACE FUNCTION public.invalidate_rociste_and_emit_event(
    p_rociste_id     TEXT,
    p_user_id        TEXT,
    p_event_id       UUID,
    p_correlation_id TEXT DEFAULT NULL
) RETURNS TABLE(predmet_id TEXT, invalidated BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_predmet_id TEXT;
BEGIN
    DELETE FROM public.rocista AS r
        WHERE r.id = p_rociste_id
          AND r.user_id = p_user_id
        RETURNING r.predmet_id INTO v_predmet_id;

    IF v_predmet_id IS NULL THEN
        RETURN QUERY SELECT NULL::TEXT, FALSE;
        RETURN;
    END IF;

    INSERT INTO public.events (id, event_type, user_id, predmet_id, payload, correlation_id)
    VALUES (
        p_event_id, 'SourceInvalidated', p_user_id, v_predmet_id,
        jsonb_build_object('source_type', 'rociste', 'source_id', p_rociste_id, 'correlation_id', p_correlation_id),
        p_correlation_id
    )
    ON CONFLICT (id) DO NOTHING;

    RETURN QUERY SELECT v_predmet_id, TRUE;
END;
$$;

COMMENT ON FUNCTION public.invalidate_rociste_and_emit_event IS
    'Wave 2 Task 2D corrective closure -- atomic delete of rocista + durable SourceInvalidated event, one transaction.';


CREATE OR REPLACE FUNCTION public.invalidate_dokument_relational_and_emit_event(
    p_dokument_id    TEXT,
    p_predmet_id     TEXT,
    p_user_id        TEXT,
    p_event_id       UUID,
    p_correlation_id TEXT DEFAULT NULL
) RETURNS TABLE(invalidated BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_deleted_id TEXT;
BEGIN
    DELETE FROM public.predmet_dokumenti AS pdoc
        WHERE pdoc.id = p_dokument_id
          AND pdoc.predmet_id = p_predmet_id
          AND pdoc.user_id = p_user_id
        RETURNING pdoc.id INTO v_deleted_id;

    IF v_deleted_id IS NULL THEN
        RETURN QUERY SELECT FALSE;
        RETURN;
    END IF;

    INSERT INTO public.events (id, event_type, user_id, predmet_id, payload, correlation_id)
    VALUES (
        p_event_id, 'SourceInvalidated', p_user_id, p_predmet_id,
        jsonb_build_object('source_type', 'dokument', 'source_id', p_dokument_id, 'correlation_id', p_correlation_id),
        p_correlation_id
    )
    ON CONFLICT (id) DO NOTHING;

    RETURN QUERY SELECT TRUE;
END;
$$;

COMMENT ON FUNCTION public.invalidate_dokument_relational_and_emit_event IS
    'Wave 2 Task 2D corrective closure -- atomic RELATIONAL delete of predmet_dokumenti + durable SourceInvalidated event, one transaction. This is the Case Evolution authoritative domain-invalidation boundary; vector/object-storage cleanup are separate, non-atomic concerns handled by the caller before/after this call, unchanged by this migration.';


REVOKE ALL ON FUNCTION public.invalidate_dokaz_and_emit_event(TEXT, TEXT, UUID, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.invalidate_rociste_and_emit_event(TEXT, TEXT, UUID, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.invalidate_dokument_relational_and_emit_event(TEXT, TEXT, TEXT, UUID, TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.invalidate_dokaz_and_emit_event(TEXT, TEXT, UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.invalidate_rociste_and_emit_event(TEXT, TEXT, UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.invalidate_dokument_relational_and_emit_event(TEXT, TEXT, TEXT, UUID, TEXT) TO service_role;
