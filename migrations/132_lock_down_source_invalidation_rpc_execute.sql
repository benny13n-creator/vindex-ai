-- ============================================================================
-- Migration 132 -- Lock down EXECUTE on the 3 source-invalidation RPCs
--
-- RENUMBERED (Wave 2 mainline integration, 2026-09-20): authored and
-- production-applied as migration 131 on the isolated Wave 2 branch;
-- renumbered to 132 here because the atomic-invalidation migration it
-- depends on (originally 130) is renumbered to 131 in this integration
-- (see that file's own renumbering note -- migration 129 collided with an
-- unrelated current-main migration, shifting this whole 3-file sequence
-- up by one). SQL body byte-identical to the original 131; already
-- applied to production (as an emergency manual statement, then formalized
-- under the original number 131) -- REVOKE/GRANT are idempotent, so
-- re-running this file (now under 132) is a safe no-op reconciliation.
--
-- VINDEX AI V1, Wave 2, Task 2D — P0 authorization hotfix (production gate,
-- 2026-09-20). Narrow, permanent fix only. Does not touch function bodies,
-- SECURITY DEFINER, search_path, parameters, or event semantics.
--
-- PROVEN (production catalog, this session): after migration 131 (then
-- numbered 130) applied, `information_schema.routine_privileges` showed
-- EXECUTE granted to `anon` and `authenticated` (in addition to
-- `service_role`/`postgres`) on all 3 new SECURITY DEFINER functions --
-- that migration's own `REVOKE ALL ... FROM PUBLIC` did not produce a
-- service-role-only boundary in the real Supabase catalog. `PUBLIC` and
-- the `anon`/`authenticated` roles are NOT the same grantee in Postgres --
-- revoking from `PUBLIC` never touches a grant made directly to a named
-- role.
--
-- PROVEN: an emergency manual REVOKE (PUBLIC, anon, authenticated) + GRANT
-- (service_role) already applied directly in production during this
-- incident produced the required live state (anon=false,
-- authenticated=false, service_role=true for all 3 functions) -- verified
-- via effective-privilege queries this same session. LIVE EXPOSURE CLOSED
-- before this migration file existed.
--
-- INFERRED, NOT PROVEN, NOT REQUIRED HERE: Supabase project-level default
-- privileges on the `public` schema are the likely mechanism that granted
-- EXECUTE to `anon`/`authenticated` on these functions at CREATE time.
-- Not confirmed against `pg_default_acl` this session, and out of this
-- hotfix's scope either way (see the migration's own scope list below) --
-- changing `ALTER DEFAULT PRIVILEGES` is a broader schema-security policy
-- decision, not this narrow fix.
--
-- THIS MIGRATION'S PURPOSE: make the already-live emergency mitigation
-- DURABLE and REPRODUCIBLE from the migration history itself, so a future
-- schema rebuild/restore (or another Supabase project applying this same
-- migration sequence) does not silently reintroduce the anon/authenticated
-- exposure that migration 131 (the atomic-invalidation migration) alone left open. Idempotent -- safe to run
-- whether or not the emergency manual mitigation already applied.
--
-- SCOPE (explicit, matching the incident's own hotfix order):
--   1. modifies ONLY EXECUTE privileges on these exact 3 functions;
--   2. no data mutation, no schema mutation, no function body change;
--   3. no change to SECURITY DEFINER, search_path, or parameters;
--   4. no change to event semantics or deterministic event-ID behavior;
--   5. no change to ALTER DEFAULT PRIVILEGES or any other global grant;
--   6. no dynamic SQL.
-- ============================================================================

REVOKE EXECUTE ON FUNCTION public.invalidate_dokaz_and_emit_event(TEXT, TEXT, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION public.invalidate_rociste_and_emit_event(TEXT, TEXT, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION public.invalidate_dokument_relational_and_emit_event(TEXT, TEXT, TEXT, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.invalidate_dokaz_and_emit_event(TEXT, TEXT, UUID, TEXT)
    TO service_role;

GRANT EXECUTE ON FUNCTION public.invalidate_rociste_and_emit_event(TEXT, TEXT, UUID, TEXT)
    TO service_role;

GRANT EXECUTE ON FUNCTION public.invalidate_dokument_relational_and_emit_event(TEXT, TEXT, TEXT, UUID, TEXT)
    TO service_role;

COMMENT ON FUNCTION public.invalidate_dokaz_and_emit_event IS
    'Wave 2 Task 2D corrective closure -- atomic soft-delete of predmet_dokazi + durable SourceInvalidated event, one transaction. Same pattern as enqueue_intake_job() (migration 073). EXECUTE locked to service_role only (migration 132 -- migration 131''s own REVOKE ALL FROM PUBLIC did not revoke anon/authenticated''s separate grant; P0 production finding, 2026-09-20).';

COMMENT ON FUNCTION public.invalidate_rociste_and_emit_event IS
    'Wave 2 Task 2D corrective closure -- atomic delete of rocista + durable SourceInvalidated event, one transaction. EXECUTE locked to service_role only (migration 132 -- see invalidate_dokaz_and_emit_event''s own comment for the full incident).';

COMMENT ON FUNCTION public.invalidate_dokument_relational_and_emit_event IS
    'Wave 2 Task 2D corrective closure -- atomic RELATIONAL delete of predmet_dokumenti + durable SourceInvalidated event, one transaction. This is the Case Evolution authoritative domain-invalidation boundary; vector/object-storage cleanup are separate, non-atomic concerns handled by the caller before/after this call. EXECUTE locked to service_role only (migration 132 -- see invalidate_dokaz_and_emit_event''s own comment for the full incident).';
