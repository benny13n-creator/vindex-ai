-- Program Lambda, Certification 002 (Ownership & IDOR Certification, 2026-08-06)
-- Addendum -- CRITICAL finding from the Database & RLS Auditor fork that the
-- sprint's own final triage pass missed closing (RLS_CERTIFICATION.md and
-- migration 102 addressed the 5 RPC-privilege bugs but never mentioned this
-- one; caught on manual re-review of the sprint's own findings against what
-- was actually shipped).
--
-- supabase_setup.sql:38-41 (public.profiles UPDATE policy):
--   CREATE POLICY "Korisnici azuriraju sopstveni profil"
--     ON public.profiles FOR UPDATE
--     USING (auth.uid() = id);
--
-- RLS restricts which ROW a user may update, not which COLUMNS. This policy
-- has no WITH CHECK and no column scope, so any authenticated user updating
-- their OWN row (a request RLS always allows) can set ANY column on it --
-- including is_pro, plan, and trial_kraj (all added by migration 061), which
-- directly gate paid PRO features (see shared/deps.py::_is_pro(),
-- routers/plan_status equivalents). Since the browser holds a public anon key
-- and talks to Supabase directly for this exact table (static/vindex.js:702,
-- confirmed the ONLY frontend write path today, and it only ever sends
-- full_name), a user can open devtools and run:
--   supabase.from('profiles').update({is_pro: true}).eq('id', session.user.id)
-- and get permanent free PRO with zero payment and zero backend involvement --
-- the same monetary-impact shape as the set_user_pro RPC bug fixed in
-- migration 102, through a different door RLS alone cannot close.
--
-- Fix: Postgres/PostgREST column-level GRANT, the standard mechanism for
-- "this role may UPDATE this row, but only these columns" -- RLS policies
-- cannot express column scope, so this must be done at the GRANT layer, in
-- addition to (not instead of) the existing row-scoping UPDATE policy above.
-- full_name is the only column the frontend actually needs direct write
-- access to (grep confirmed: static/vindex.js has exactly one profiles
-- .update() call, {full_name: fullName}); is_pro/plan/trial_kraj/onboarding_done
-- are all backend-only writes (payment webhook, trial-expiry job, onboarding
-- endpoint in api.py), already made via the service-role client, which this
-- REVOKE does not affect.

REVOKE UPDATE ON public.profiles FROM authenticated;
REVOKE UPDATE ON public.profiles FROM anon;
GRANT UPDATE (full_name) ON public.profiles TO authenticated;

-- service_role keeps full access (unaffected by the REVOKE above, but explicit
-- for the same reason supabase_setup.sql:45 already is):
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles TO service_role;

-- KRITIČNO -- RUČNA PROVERA POSLE OVE MIGRACIJE (isti obrazac kao migracija 102):
-- Ovo je SQL koji korisnik (founder) mora sam pokrenuti u Supabase SQL Editor-u.
-- Posle pokretanja, potvrdi u browser konzoli (test nalog, ne produkcioni klijent):
--   supabase.from('profiles').update({is_pro: true}).eq('id', '<test-uid>')
-- mora vratiti permission-denied/column-privilege grešku, ne uspeh -- i potvrdi
-- da normalno menjanje imena (Podešavanja -> ime) i dalje radi bez greške.
