-- ============================================================================
-- Migration 133 -- Fix UUID/TEXT type contract on the 3 atomic source-
-- invalidation RPCs (migration 131)
--
-- VINDEX AI V1, Wave 2, P0/P1 production defect fix (2026-09-20).
--
-- PROVEN IN PRODUCTION (live canary, real app path, not a direct DB probe):
--   DELETE /api/evidence/predmeti/{id}/dokaz/{id} on release f7945040
--   returned HTTP 500 three times, deterministically (distinct rndr-id/
--   CF-RAY per attempt -- not a caching artifact). Direct probing of
--   public.invalidate_dokaz_and_emit_event(text,text,uuid,text) confirmed
--   the exact cause:
--
--     ERROR 42883: operator does not exist: uuid = text
--     WHERE pd.id = p_dokaz_id AND pd.user_id = p_user_id
--
--   predmet_dokazi.id/user_id/predmet_id are `uuid` columns; migration 131
--   declared p_dokaz_id/p_user_id as TEXT. Postgres does not have an
--   implicit `uuid = text` equality operator, so every call fails at
--   query-plan time -- 100% of calls, not an edge case. The identical
--   structural mismatch exists in the other two RPCs from the same
--   migration: invalidate_rociste_and_emit_event (rocista.id/user_id/
--   predmet_id are uuid, params were TEXT) and
--   invalidate_dokument_relational_and_emit_event (predmet_dokumenti.id/
--   predmet_id/user_id are uuid, params were TEXT). One shared contract
--   defect across all three RPCs migration 131 introduced -- none of them
--   ever successfully executed in production since that migration was
--   applied.
--
-- WHY NOT p_event_id: that parameter was already declared UUID in
-- migration 131 and is only ever used as an INSERT VALUES literal into
-- events.id (uuid) and as a RETURNING-INTO source into a local TEXT
-- variable -- both are Postgres *assignment casts* (uuid<->text), which
-- exist and are permissive, unlike the *equality operator* uuid = text
-- used in a WHERE clause, which does not exist. This is exactly why the
-- failure was 100% reproducible on the WHERE-clause identity columns and
-- nowhere else in the same functions.
--
-- FIX: change every identity-column-comparison parameter (the dokaz/
-- rociste/dokument/predmet/user ids compared directly against a `uuid`
-- column) to UUID. p_correlation_id stays TEXT -- it is never compared
-- against a uuid column, only stored/returned as free text, matching
-- events.correlation_id's own column type. Local variables and RETURNS
-- TABLE output types are left exactly as migration 131 declared them
-- (TEXT) -- RETURNING ... INTO a TEXT variable from a uuid column, and
-- RETURN QUERY SELECT of a uuid value into a TEXT output column, both go
-- through the same permissive assignment cast that never failed; changing
-- them is not required by this fix and would be scope creep against the
-- "preserve existing return contract semantics" instruction.
--
-- CREATE OR REPLACE cannot change a function's argument types in place --
-- it only replaces a function whose signature (name + exact parameter
-- types) already matches. Declaring these 3 functions with UUID
-- parameters therefore creates 3 NEW, DISTINCT overloads alongside the
-- old TEXT-typed ones; it does not touch them. Leaving both signatures
-- live would not be a harmless no-op: PostgREST's RPC endpoint resolves
-- an overload by parameter NAME (all identical here -- p_dokaz_id,
-- p_user_id, etc., across both signatures) and JSON-argument count, and
-- with two same-named/same-arity overloads present it cannot always
-- disambiguate purely from a JSON string payload -- the exact ambiguity
-- PostgREST reports as "Could not choose the best candidate function."
-- Besides that functional risk, the old signatures are also still a
-- SECURITY DEFINER surface (only closed for anon/authenticated by
-- migration 132's EXECUTE lockdown, never actually removed as objects).
-- Both reasons -- not just cleanliness -- are why explicitly DROPping the
-- exact old TEXT signatures is required, not optional, in this same
-- migration.
--
-- DEPENDENCY CHECK (repo-level, this session's only available evidence --
-- no direct production catalog access this session): grepped every file
-- under migrations/ for the 3 old function names. Only 131 (creates them)
-- and 132 (GRANT/REVOKE on them, already applied, not a live dependency)
-- reference them -- no view, trigger, or other migration depends on the
-- old signatures. No dependency found in application code either (see
-- services/event_bus.py -- callers pass values by parameter NAME through
-- supabase-py's .rpc(), never touching a signature directly). Because the
-- old signatures have NEVER successfully executed in production (100%
-- failure since migration 131), dropping them carries zero risk of
-- breaking a currently-working call path.
--
-- APPLICATION COMPATIBILITY: no application code change required.
-- services/event_bus.py's _invalidate_atomic() (and the dokument-specific
-- caller) send plain Python `str` values -- which are already
-- well-formed UUID strings for every identity field (Supabase auth user
-- ids and every predmet_dokazi/rocista/predmet_dokumenti primary/foreign
-- key are UUIDs end to end; only ever represented as `str` in Python).
-- PostgREST/Supabase coerces a JSON string argument to whatever type the
-- resolved function's parameter declares -- a UUID-shaped string coerces
-- to `uuid` exactly as readily as it coerced to `text` before. p_event_id
-- was already UUID and worked; p_correlation_id stays TEXT and is
-- unaffected. No caller anywhere sends a non-UUID-shaped value for any of
-- the changed parameters.
--
-- Everything else is preserved byte-for-byte from migration 131's
-- reasoning: SECURITY DEFINER, SET search_path = '' (still safe -- every
-- object reference remains schema-qualified), the single-transaction
-- mutation+event-insert body, the caller-supplied deterministic
-- p_event_id + `ON CONFLICT (id) DO NOTHING` idempotency, the dokaz
-- function's deliberate absence of a `deleted_at IS NULL` guard
-- (preserves the existing repeat-delete-stays-200 contract), and the
-- authorization predicate (ownership still enforced inside each
-- function's own WHERE/DELETE clause, not moved to a client-trusted
-- boundary).
--
-- AUTHORIZATION: migration 131 originally left EXECUTE grantable to
-- anon/authenticated by not revoking those specific grantees (only
-- `PUBLIC`), a gap migration 132 closed as a hotfix afterward. Applying
-- that same two-step pattern to a brand-new function would recreate the
-- identical exposure window for however long a follow-up migration takes
-- to land, so this migration grants the fully-hardened state directly on
-- creation: REVOKE FROM PUBLIC, anon, authenticated + GRANT TO
-- service_role only, in one step, for the 3 new UUID signatures.
-- ============================================================================


CREATE OR REPLACE FUNCTION public.invalidate_dokaz_and_emit_event(
    p_dokaz_id       UUID,
    p_user_id        UUID,
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
    -- No `deleted_at IS NULL` predicate, deliberately -- unchanged from
    -- migration 131 (tests/test_v44_delete_dokaz_guard.py::
    -- test_5_repeated_delete_stays_200_not_zero_row).
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

COMMENT ON FUNCTION public.invalidate_dokaz_and_emit_event(UUID, UUID, UUID, TEXT) IS
    'Wave 2 P0/P1 fix (migration 133) -- UUID-typed identity parameters (predmet_dokazi.id/user_id are uuid columns; migration 131''s TEXT parameters made every call fail with "operator does not exist: uuid = text", proven via a live production canary, 2026-09-20). Same atomic soft-delete + durable SourceInvalidated event, one transaction, as migration 131. Old TEXT-signature overload dropped by this same migration.';


CREATE OR REPLACE FUNCTION public.invalidate_rociste_and_emit_event(
    p_rociste_id     UUID,
    p_user_id        UUID,
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

COMMENT ON FUNCTION public.invalidate_rociste_and_emit_event(UUID, UUID, UUID, TEXT) IS
    'Wave 2 P0/P1 fix (migration 133) -- UUID-typed identity parameters (rocista.id/user_id are uuid columns; migration 131''s TEXT parameters made every call fail with "operator does not exist: uuid = text", proven via a live production canary, 2026-09-20). Same atomic delete + durable SourceInvalidated event, one transaction, as migration 131. Old TEXT-signature overload dropped by this same migration.';


CREATE OR REPLACE FUNCTION public.invalidate_dokument_relational_and_emit_event(
    p_dokument_id    UUID,
    p_predmet_id     UUID,
    p_user_id        UUID,
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

COMMENT ON FUNCTION public.invalidate_dokument_relational_and_emit_event(UUID, UUID, UUID, UUID, TEXT) IS
    'Wave 2 P0/P1 fix (migration 133) -- UUID-typed identity parameters (predmet_dokumenti.id/predmet_id/user_id are uuid columns; migration 131''s TEXT parameters made every call fail with "operator does not exist: uuid = text", proven via a live production canary, 2026-09-20). Same atomic RELATIONAL delete + durable SourceInvalidated event, one transaction, as migration 131; vector/object-storage cleanup remain the caller''s own separate, non-atomic concern, unchanged. Old TEXT-signature overload dropped by this same migration.';


-- Drop the obsolete TEXT-signature overloads. These never successfully
-- executed in production (100% failure since migration 131 -- proven by
-- this session's live canary), so this removes zero working call paths.
-- Leaving them would (a) risk PostgREST overload-resolution ambiguity
-- against the new same-named UUID overloads, and (b) leave a dead but
-- still-privileged SECURITY DEFINER surface live.
DROP FUNCTION IF EXISTS public.invalidate_dokaz_and_emit_event(TEXT, TEXT, UUID, TEXT);
DROP FUNCTION IF EXISTS public.invalidate_rociste_and_emit_event(TEXT, TEXT, UUID, TEXT);
DROP FUNCTION IF EXISTS public.invalidate_dokument_relational_and_emit_event(TEXT, TEXT, TEXT, UUID, TEXT);


-- Fully-hardened grant applied directly on the new signatures (see the
-- file header's AUTHORIZATION note for why this is done in one step here
-- instead of repeating migration 131's REVOKE-ALL-FROM-PUBLIC-only
-- pattern and relying on a follow-up hotfix).
REVOKE EXECUTE ON FUNCTION public.invalidate_dokaz_and_emit_event(UUID, UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.invalidate_rociste_and_emit_event(UUID, UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.invalidate_dokument_relational_and_emit_event(UUID, UUID, UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.invalidate_dokaz_and_emit_event(UUID, UUID, UUID, TEXT)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.invalidate_rociste_and_emit_event(UUID, UUID, UUID, TEXT)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.invalidate_dokument_relational_and_emit_event(UUID, UUID, UUID, UUID, TEXT)
    TO service_role;
