-- Program Lambda, Certification 002 (Ownership & IDOR Certification, 2026-08-06)
-- Database & RLS Auditor fork found 2 CONFIRMED, directly exploitable database-layer
-- ownership bypasses -- both reachable via PostgREST (/rest/v1/rpc/...) by ANY
-- authenticated user, completely independent of the FastAPI backend (no rate
-- limiting, no _is_founder guard, no billing check ever runs):
--
-- 1. deduct_credit(p_user_id UUID) -- SECURITY DEFINER, explicitly
--    `GRANT EXECUTE ... TO authenticated` (supabase_setup.sql:148), and the function
--    body trusts p_user_id with no `p_user_id = auth.uid()` check. Any logged-in
--    attacker can drain ANY other user's credits to 0 by calling
--    rpc("deduct_credit", {"p_user_id": "<victim uuid>"}) repeatedly -- a
--    cross-account denial-of-service with zero backend involvement.
--
-- 2. set_user_pro(p_email TEXT, p_is_pro BOOLEAN) -- SECURITY DEFINER, and (confirmed
--    by repo-wide grep) NEVER had any GRANT/REVOKE statement at all, anywhere.
--    Postgres's own default is EXECUTE granted to PUBLIC at creation time, which
--    Supabase's `authenticated`/`anon` roles inherit -- so this "founder SQL Editor
--    helper" (see its own comment in 061_fix_missing_profiles_columns.sql) has been
--    callable by every app user since it was created. Any authenticated user could
--    call rpc("set_user_pro", {"p_email": "<own email>", "p_is_pro": true}) for a
--    free permanent PRO upgrade with zero payment, or strip a victim's PRO status
--    by supplying their email with p_is_pro:false.
--
-- Both are fixed here with the SAME REVOKE-FROM-PUBLIC pattern this codebase
-- already established correctly for every RPC added since (see
-- migrations/073_intake_foundations.sql:345-350, 091_event_bus_atomic_claim.sql,
-- 092_finalize_atomic_claim.sql, 095_intake_bulletproofing.sql) -- migration 073's
-- own comment ("isti obrazac kao deduct_credit()/deduct_n_credits() -- nikad
-- izloženo anon/authenticated") shows a later author already BELIEVED these two
-- functions were locked down this way. They never were -- a "declared control ≠
-- enforced control" gap, not a newly-introduced regression.
--
-- Same audit fork also found 3 lower-severity instances of the identical
-- missing-REVOKE pattern (no explicit GRANT to authenticated/anon, but also no
-- REVOKE FROM PUBLIC, which is Postgres's own PUBLIC-executable default) --
-- locked down here as defense-in-depth even though none accept a caller-supplied
-- identity that leads to a confirmed live exploit today:
--   - deduct_n_credits(p_user_id, p_n)     -- same credit-drain shape as #1, at scale n.
--   - get_activity_averages(p_user_id)     -- reads another user's 30-day usage averages.
--   - get_next_broj_fakture(p_user_id)     -- reads another user's invoice count/sequence;
--                                              confirmed unused by the Python codebase
--                                              (grep for get_next_broj_fakture in *.py
--                                              returned zero hits) but still live in the DB.
--
-- Fix shape for all 5: REVOKE the PUBLIC-inherited execute grant, then GRANT
-- EXECUTE only to service_role (the only role the backend actually calls these
-- as, per shared/deps.py::_get_supa()). No function body was rewritten -- this is
-- a privilege fix, not a logic change, and does not alter any currently-correct
-- backend call path (every existing Python .rpc(...) call already runs under the
-- service-role key).

REVOKE ALL ON FUNCTION public.deduct_credit(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.deduct_credit(UUID) FROM anon;
REVOKE ALL ON FUNCTION public.deduct_credit(UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.deduct_credit(UUID) TO service_role;

REVOKE ALL ON FUNCTION public.set_user_pro(TEXT, BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.set_user_pro(TEXT, BOOLEAN) FROM anon;
REVOKE ALL ON FUNCTION public.set_user_pro(TEXT, BOOLEAN) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.set_user_pro(TEXT, BOOLEAN) TO service_role;

REVOKE ALL ON FUNCTION public.deduct_n_credits(UUID, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.deduct_n_credits(UUID, INTEGER) FROM anon;
REVOKE ALL ON FUNCTION public.deduct_n_credits(UUID, INTEGER) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.deduct_n_credits(UUID, INTEGER) TO service_role;

REVOKE ALL ON FUNCTION public.get_activity_averages(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_activity_averages(UUID) FROM anon;
REVOKE ALL ON FUNCTION public.get_activity_averages(UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_activity_averages(UUID) TO service_role;

REVOKE ALL ON FUNCTION public.get_next_broj_fakture(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_next_broj_fakture(UUID) FROM anon;
REVOKE ALL ON FUNCTION public.get_next_broj_fakture(UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_next_broj_fakture(UUID) TO service_role;

-- KRITIČNO -- RUČNA PROVERA POSLE OVE MIGRACIJE:
-- Ovo je SQL koji korisnik (founder) mora sam pokrenuti u Supabase SQL Editor-u
-- (standing rule ovog projekta -- migracije se nikad ne šalju/pokreću automatski).
-- Posle pokretanja, proveri u Supabase Dashboard-u da REVOKE stvarno zabranjuje
-- pristup: probaj (kao test, ne produkcija) da pozoveš
-- rpc("set_user_pro", {"p_email": "test@test.com"}) sa anon/authenticated ključem
-- i potvrdi da vraća permission-denied grešku, ne uspeh.
