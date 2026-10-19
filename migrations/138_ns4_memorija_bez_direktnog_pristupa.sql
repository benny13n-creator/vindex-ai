-- ============================================================================
-- Vindex AI — Migracija 138: poverljiva memorija kancelarije bez direktnog Data API pristupa (NS4 O1)
-- ============================================================================
-- PROBLEM (dokazano čitanjem produkcije 2026-10-19, samo čitanje):
--   • `anon` i `authenticated` imaju SELECT nad dole navedenim tabelama (PostgREST vraća 200 [] za anon,
--     ne „permission denied") — pristup posreduje ISKLJUČIVO RLS.
--   • RLS politike iz 045/046/047/059 imaju dve grane:
--       (a) članstvo `status = 'aktivan'` — posle 067 (`aktivan` → `ACTIVE`) ne odgovara nijednom redu (mrtva);
--       (b) `kancelarija_id IN (SELECT id FROM kancelarije WHERE admin_uid = auth.uid())` — ŽIVA.
--     Grana (b) daje administratoru kancelarije, preko sopstvenog JWT-a i direktnog Data API-ja, SVE redove
--     kancelarije: beleške uz tuđe predmete i klijente, profil tuđeg klijenta, veze grafa sa ishodom tuđeg
--     predmeta, tok rada tuđeg predmeta — mimo kanonske autorizacije predmeta (`shared/rag_acl`,
--     `shared/memorija_vidljivost`). Kancelariju može da napravi svaki prijavljen korisnik
--     (POST /api/kancelarija/kreiraj).
--
-- ZAŠTO NE ZAMENA 'aktivan' → 'ACTIVE':
--   RLS ovih tabela ne zna za predmet/klijenta; oživljavanje grane (a) bi SVAKOM članu otvorilo sve beleške
--   kancelarije (širenje pristupa). Politike se zato NE menjaju.
--
-- POTROŠAČI (dokazano grep-om, NS4 izveštaj §O1):
--   • frontend (static/, frontend-v2-ng/) direktno čita samo `conversations`, `profiles`, `reported_errors`;
--   • backend koristi isključivo `service_role` (shared/deps.py, api.py) — REVOKE ga ne dotiče;
--   • nijedna od ovih tabela nema drugog potrošača sa korisničkim JWT-om.
--
-- REŠENJE (najmanje): oduzeti direktan pristup `anon`/`authenticated` SAMO tabelama poverljive memorije i
-- tokova vezanih za predmet. Ponašanje backend-a se ne menja. Namerno NIJE uključeno:
--   • `zadaci` — žive grane su samo kreirao/dodeljen (sopstveni zadaci), grana članstva je mrtva;
--   • `workflow_templates` — sistemski i kancelarijski šabloni, bez sadržaja predmeta.
--
-- Zaključavanje: REVOKE uzima kratku ACCESS EXCLUSIVE bravu po tabeli; bez prepisivanja podataka.
-- Idempotentno: ponovljen REVOKE nad već oduzetim pravom nije greška.
-- ============================================================================

BEGIN;

REVOKE ALL ON TABLE
    public.memory_entries,
    public.memory_graph_edges,
    public.client_memory,
    public.partner_profiles,
    public.judge_patterns,
    public.firm_style_profile,
    public.workflow_instances,
    public.workflow_steps
FROM anon, authenticated;

COMMIT;

-- ─── Provera posle primene (očekivano: 0 redova) ─────────────────────────────
-- SELECT table_name, grantee, privilege_type
--   FROM information_schema.role_table_grants
--  WHERE table_schema = 'public'
--    AND grantee IN ('anon', 'authenticated')
--    AND table_name IN ('memory_entries','memory_graph_edges','client_memory','partner_profiles',
--                       'judge_patterns','firm_style_profile','workflow_instances','workflow_steps');
--
-- ─── Povratak (SAMO ako se dokaže potrošač sa korisničkim JWT-om; vraća i rupu iz grane (b)) ─────────────
-- Pre primene sačuvati izlaz upita iznad bez filtera `grantee` i vratiti TAČNO te dozvole, npr.:
-- GRANT SELECT ON TABLE public.memory_entries TO authenticated;
