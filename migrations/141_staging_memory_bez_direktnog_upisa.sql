-- ============================================================================
-- Vindex AI — Migracija 141: nacrti na pregledu (`staging_memory`) bez direktnog Data API pristupa
-- MIR001 FINAL RELEASE GATES, TASK-R2. NE PRIMENJUJE SE AUTOMATSKI — primenjuje osnivač, posle preflight-a.
-- ============================================================================
-- PROBLEM (osnivač, read-only provera produkcije):
--   • politika `staging_memory_sopstveni` (088) je `FOR ALL USING/WITH CHECK (auth.uid()::text = user_id)`;
--   • `authenticated` (i `anon`, Supabase podrazumevana prava) ima INSERT/UPDATE/DELETE/TRUNCATE nad tabelom;
--   • nema okidača. RLS ne ograničava KOLONE: vlasnik svojim JWT-om preko Data API-ja može sam da postavi
--     `status='approved'`, `is_lawyer_approved`, `approved_by`, `quality_detail.usvajanje.odobreno`, da ubaci već
--     „odobren" red ili da obriše zapis — mimo serverske granice usvajanja (MIR001 C3b: `/api/staging/{id}/approve`
--     traži sha + reviziju + 8 procesnih odluka). Za TRUNCATE RLS uopšte ne važi.
--
-- POTROŠAČI (dokazano grep-om, MIR001 FINAL RELEASE ledger, TASK-R2):
--   • backend pristupa ISKLJUČIVO kao `service_role` (`shared/deps._get_supa`, SUPABASE_SERVICE_KEY; BYPASSRLS) —
--     sve rute pregleda/usvajanja/odobrenja/izvoza, `services/law_brain*`, `shared/predmet_deletion`, RPC iz 140
--     (SECURITY INVOKER, EXECUTE samo `service_role`). REVOKE ga ne dotiče;
--   • frontend (static/, frontend-v2-ng/) NE čita i NE piše tabelu direktno — samo kroz `/api/staging/*`;
--   • nema pogleda, okidača ni funkcija sa korisničkim JWT-om nad ovom tabelom.
--
-- REŠENJE (najmanje; isti obrazac kao 138):
--   1. oduzeti SVA prava `anon`, `authenticated` i PUBLIC (uključujući TRUNCATE, REFERENCES, TRIGGER);
--   2. politiku `FOR ALL` zameniti politikom SAMO ZA ČITANJE sopstvenih redova. Danas je uspavana (SELECT je
--      oduzet, pa vlasnik ne čita ništa direktno — frontend tabelu ne čita); ako bi neka buduća migracija ili
--      podrazumevano pravo ponovo dodelilo prava, upis (INSERT/UPDATE/DELETE) i dalje ne prolazi RLS, a čitanje ostaje
--      ograničeno na sopstvene redove (odbrana u dubini). TRUNCATE RLS NE pokriva — zato se pravo oduzima (1); posle
--      svake buduće dodele prava nad šemom ponoviti postflight (a).
--   Ponašanje backend-a se ne menja. Podaci se ne menjaju.
--
-- Zaključavanje: REVOKE/DROP/CREATE POLICY uzimaju kratku ACCESS EXCLUSIVE bravu; bez prepisivanja podataka.
-- Idempotentno: REVOKE nad oduzetim pravom nije greška; politike se brišu sa IF EXISTS pre kreiranja.
-- ============================================================================

-- ─── PREFLIGHT (samo čitanje; sačuvati izlaz — on je osnov za povratak) ───────────────────────────────────────
-- Pokrenuti kao `postgres` (SQL editor), da `information_schema` i katalog prikažu sva prava.
-- (a) prava nad tabelom i kolonama po ulozi (kolonska prava `role_table_grants` NE prikazuje):
-- SELECT r.rolname,
--        has_table_privilege(r.rolname, 'public.staging_memory', 'SELECT')   AS sel,
--        has_table_privilege(r.rolname, 'public.staging_memory', 'INSERT')   AS ins,
--        has_table_privilege(r.rolname, 'public.staging_memory', 'UPDATE')   AS upd,
--        has_table_privilege(r.rolname, 'public.staging_memory', 'DELETE')   AS del,
--        has_table_privilege(r.rolname, 'public.staging_memory', 'TRUNCATE') AS trunc,
--        has_any_column_privilege(r.rolname, 'public.staging_memory', 'SELECT,INSERT,UPDATE') AS kolone
--   FROM pg_roles r WHERE r.rolname IN ('anon', 'authenticated', 'service_role');
-- (b) tačan ACL (i ko je dao pravo) i vlasnik:
-- SELECT relowner::regrole AS vlasnik, relrowsecurity, relforcerowsecurity, relacl FROM pg_class
--  WHERE oid = 'public.staging_memory'::regclass;
-- SELECT attname, attacl FROM pg_attribute WHERE attrelid = 'public.staging_memory'::regclass AND attacl IS NOT NULL;
-- (c) politike i okidači:
-- SELECT policyname, cmd, roles, qual, with_check FROM pg_policies
--  WHERE schemaname = 'public' AND tablename = 'staging_memory';
-- SELECT tgname FROM pg_trigger WHERE tgrelid = 'public.staging_memory'::regclass AND NOT tgisinternal;
-- (d) funkcije i pogledi koji pominju tabelu (očekivano: samo dve funkcije iz 140, SECURITY INVOKER):
-- SELECT p.oid::regprocedure, p.prosecdef, p.proacl FROM pg_proc p WHERE p.prosrc ILIKE '%staging_memory%';
-- SELECT schemaname, viewname FROM pg_views WHERE definition ILIKE '%staging_memory%';
-- STOP ako: postoji pogled ili SECURITY DEFINER funkcija nad tabelom; `service_role` NEMA sva prava; RLS je isključen.

BEGIN;

REVOKE ALL ON TABLE public.staging_memory FROM PUBLIC, anon, authenticated;

DROP POLICY IF EXISTS "staging_memory_sopstveni" ON public.staging_memory;
DROP POLICY IF EXISTS "staging_memory_sopstveni_citanje" ON public.staging_memory;
CREATE POLICY "staging_memory_sopstveni_citanje" ON public.staging_memory
    FOR SELECT TO authenticated USING (auth.uid()::text = user_id);

COMMIT;

-- ─── POSTFLIGHT (samo čitanje) ───────────────────────────────────────────────────────────────────────────────
-- 1) prava: preflight (a) — za anon i authenticated SVE kolone `false`; za service_role sve `true`.
--    preflight (b) — `attacl` prazan; `relacl` bez anon/authenticated/PUBLIC.
-- 2) politike: tačno `staging_memory_sopstveni_citanje` (SELECT, authenticated) i `staging_memory_service_role` (ALL)
-- SELECT policyname, cmd, roles FROM pg_policies WHERE schemaname = 'public' AND tablename = 'staging_memory';
-- 3) service_role i dalje ima sva prava: očekivano INSERT, SELECT, UPDATE, DELETE (i ostala)
-- SELECT privilege_type FROM information_schema.role_table_grants
--  WHERE table_schema = 'public' AND table_name = 'staging_memory' AND grantee = 'service_role';
-- 4) aplikacija (kontrolisani QA): otvoriti nacrt, usvojiti stavku, odobriti, izvesti DOCX — mora raditi
--    (backend = service_role).
--
-- ─── POVRATAK (samo ako se dokaže potrošač sa korisničkim JWT-om; VRAĆA RUPU iz opisa) ─────────────────────────
-- BEGIN;
-- DROP POLICY IF EXISTS "staging_memory_sopstveni_citanje" ON public.staging_memory;
-- CREATE POLICY "staging_memory_sopstveni" ON public.staging_memory
--     FOR ALL USING (auth.uid()::text = user_id) WITH CHECK (auth.uid()::text = user_id);
-- -- vratiti TAČNO prava iz preflight izlaza, npr.:
-- -- GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.staging_memory TO authenticated;
-- COMMIT;
