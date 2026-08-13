-- ═══════════════════════════════════════════════════════════════════════════
-- READ-ONLY verifikacija migracije 089 (AI Provenance Extension).
--
-- NIŠTA OVDE NE PIŠE. Nema INSERT/UPDATE/DELETE/ALTER/CREATE/DROP/TRUNCATE.
-- Samo `SELECT` nad sistemskim katalogom. Nema dinamičkog SQL-a.
-- Nalepite izlaz nazad.
--
-- ŠTA JE VEĆ DOKAZANO BEZ BAZE
-- Sonda iz aplikacije (`select(<kolona>).limit(0)`, nijedan red pročitan)
-- potvrdila je da svih 19 kolona iz 089 i svih 10 legacy kolona iz 043 postoje
-- na `ai_forensics` — tačno onih 29 koje runtime upisuje. Runtime zavisnost je
-- time zadovoljena i uska legacy grana se u produkciji ne aktivira.
--
-- ŠTA SONDA NE MOŽE
--   · indekse (PostgREST ih ne izlaže)
--   · trigger — provera bi tražila `UPDATE`, dakle mutaciju
--   · tipove/nullability
--   · poreklo šeme: kolone može da doda i ručni `ALTER`
--
-- Q1–Q6 zatvaraju tačno to.
--
-- KLJUČNO ZA TUMAČENJE: `ai_forensics` dodiruju DVE migracije.
--   043 — kreira tabelu, 10 kolona, 4 indeksa, BEZ trigera, svoj komentar
--   089 — dodaje 19 kolona, 4 DRUGA indeksa, trigger, prepisuje komentar
-- Zato se poreklo može razlikovati: 043-ovi i 089-ovi artefakti su disjunktni.
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
-- Q1 ── Kolone koje 089 dodaje: tipovi i nullability.
-- CILJNI OBJEKAT: public.ai_forensics (tabela u koju runtime STVARNO upisuje —
--   `security/ai_forensics.py::log_provenance_from_wrapper` radi
--   `supa.table("ai_forensics").insert(...)`; nijedna druga tabela).
-- OČEKUJE: 19 redova, svih 19 `is_nullable = YES` (089 ih dodaje bez NOT NULL,
--   a runtime šalje `None` za nepopunjena polja).
-- ───────────────────────────────────────────────────────────────────────────
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name  = 'ai_forensics'
  AND column_name IN (
      'tenant_id','predmet_id','document_id','module_name','operation_name',
      'model_provider','model_version','system_prompt_hash','user_prompt_hash',
      'retrieved_context_ids','knowledge_sources','retrieval_query',
      'confidence_score','hallucination_check_result','parent_event_id',
      'correlation_id','audit_reference','status','error_message'
  )
ORDER BY column_name;


-- ───────────────────────────────────────────────────────────────────────────
-- Q2 ── SVI indeksi na ai_forensics, sa punom definicijom.
-- CILJNI OBJEKAT: public.ai_forensics.
-- Ovo je GLAVNI test porekla, jer su skupovi indeksa iz 043 i 089 disjunktni.
--
-- 089 očekuje (sva četiri jednokolonska):
--   idx_ai_forensics_correlation_id  ON (correlation_id)
--   idx_ai_forensics_predmet_id      ON (predmet_id)
--   idx_ai_forensics_module_name     ON (module_name)
--   idx_ai_forensics_status          ON (status) WHERE status = 'error'   ← parcijalni
--
-- 043 je ranije napravila (očekuje se da i one postoje, nisu predmet ovog testa):
--   idx_ai_forensics_user_id, _started_at, _endpoint, _risk_score
-- ───────────────────────────────────────────────────────────────────────────
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename  = 'ai_forensics'
ORDER BY indexname;


-- ───────────────────────────────────────────────────────────────────────────
-- Q3 ── Trigger za nepromenljivost.
-- CILJNI OBJEKAT: trigeri VEZANI ZA public.ai_forensics (`c.relname`), ne
--   trigeri istog imena bilo gde — zato join na `pg_class`.
-- OČEKUJE: `trg_protect_ai_forensics_update`, BEFORE, ROW,
--   funkcija `protect_ai_forensics_from_update`.
-- 043 NIJE pravila nijedan trigger na ovoj tabeli — svaki nađeni trigger je
--   dakle 089-ov artefakt.
-- NAMERNO ne blokira DELETE: `services/retention_service.py` legitimno briše
--   redove starije od `AI_FORENSICS_RETENTION_DAYS` (GDPR storage limitation).
-- ───────────────────────────────────────────────────────────────────────────
SELECT t.tgname,
       CASE WHEN (t.tgtype & 2) = 2 THEN 'BEFORE' ELSE 'AFTER' END AS timing,
       CASE WHEN (t.tgtype & 1) = 1 THEN 'ROW'    ELSE 'STATEMENT' END AS nivo,
       CASE WHEN (t.tgtype & 16) = 16 THEN 'UPDATE' ELSE '' END AS na_update,
       CASE WHEN (t.tgtype & 8)  = 8  THEN 'DELETE' ELSE '' END AS na_delete,
       t.tgenabled,
       p.proname AS funkcija
FROM pg_trigger t
JOIN pg_class  c ON c.oid = t.tgrelid
JOIN pg_proc   p ON p.oid = t.tgfoid
WHERE c.relname = 'ai_forensics'
  AND NOT t.tgisinternal
ORDER BY t.tgname;


-- ───────────────────────────────────────────────────────────────────────────
-- Q4 ── Telo funkcije koju trigger zove.
-- CILJNI OBJEKAT: public.protect_ai_forensics_from_update().
-- Postojanje trigera NE dokazuje da telo odbija UPDATE — moglo bi biti
--   `RETURN NEW` i tiho propuštati izmene.
-- OČEKUJE: `RAISE EXCEPTION`, `LANGUAGE plpgsql`, `SECURITY DEFINER`.
-- `pg_get_functiondef` je čista katalog funkcija — bez sporednih efekata.
-- ───────────────────────────────────────────────────────────────────────────
SELECT p.proname,
       p.prosecdef AS security_definer,
       l.lanname   AS jezik,
       pg_get_functiondef(p.oid) AS telo
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language  l ON l.oid = p.prolang
WHERE n.nspname = 'public'
  AND p.proname = 'protect_ai_forensics_from_update';


-- ───────────────────────────────────────────────────────────────────────────
-- Q5 ── Komentar na tabeli — ARTEFAKT PORREKLA.
-- CILJNI OBJEKAT: public.ai_forensics.
-- I 043 i 089 postavljaju `COMMENT ON TABLE ai_forensics`, i 089 prepisuje
--   043-ov. Tekst je zato potpis one migracije koja je poslednja izvršena:
--     089 → počinje sa 'AI Provenance & Decision Traceability (Mission Atlas...'
--     043 → počinje sa 'Forenzički zapis svakog AI poziva...'
-- Ručni `ALTER TABLE ... ADD COLUMN` ne menja komentar. Ovo je najbliže
--   dokazu izvršenja koje ova baza uopšte poseduje.
-- ───────────────────────────────────────────────────────────────────────────
SELECT obj_description('public.ai_forensics'::regclass, 'pg_class') AS komentar_tabele;


-- ───────────────────────────────────────────────────────────────────────────
-- Q6 ── Postoji li IJEDAN artefakt istorije migracija u OVOJ bazi?
-- Forenzika repoa je pokazala da mehanizam praćenja ne postoji (nema runnera u
--   `Procfile`/`Dockerfile`, nema Supabase CLI konfiguracije, nijedan workflow
--   ne primenjuje migracije). Ovaj upit to proverava sa DRUGE strane — iz same
--   baze — da zaključak ne bi počivao samo na odsustvu u repou.
-- OČEKUJE: 0 redova. Ako vrati red, istorija POSTOJI i treba je pročitati
--   umesto zaključivanja iz artefakata.
-- ───────────────────────────────────────────────────────────────────────────
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name ILIKE '%migration%'
   OR table_name ILIKE '%schema_version%'
ORDER BY table_schema, table_name;


-- ═══════════════════════════════════════════════════════════════════════════
-- KAKO ČITATI REZULTAT
--
-- Q1  19 redova, svi nullable        → runtime zavisnost ZADOVOLJENA.
--                                      (Već potvrđeno sondom; ovo je kontrola.)
--
-- Q2  sva 4 089-indeksa prisutna     → SCHEMA MATCH za indekse.
--     nijedan 089-indeks             → kolone su dodate MIMO 089 (ručni ALTER).
--     neki da, neki ne               → delimično izvršavanje — imenovati kao drift.
--     (Kolonski redosled nije primenjiv: sva četiri su jednokolonska.
--      Kod `idx_ai_forensics_status` mora postojati i `WHERE status = 'error'`;
--      bez toga je indeks pun, ne parcijalni — različit objekat.)
--
-- Q3  trigger prisutan, BEFORE/ROW, na UPDATE, `tgenabled = 'O'`
--                                    → nepromenljivost je ožičena.
--     nema ga                        → provenance red se može TIHO PREPISATI i
--                                      prestaje da bude upotrebljiv kao dokaz.
--     postoji ali `tgenabled = 'D'`  → onemogućen; isto kao da ga nema.
--     vezan za drugu tabelu          → ne bi se ni pojavio ovde (filter je
--                                      `c.relname = 'ai_forensics'`).
--
-- Q4  telo sadrži `RAISE EXCEPTION`  → trigger stvarno odbija UPDATE.
--     telo `RETURN NEW`              → trigger postoji ali NE štiti ništa.
--
-- Q5  komentar = 'AI Provenance & Decision Traceability (Mission Atlas…'
--                                    → 089 je izvršena (prepisala je 043-ov).
--     komentar = 'Forenzički zapis svakog AI poziva…'
--                                    → 089 NIJE izvršena do kraja.
--
-- Q6  0 redova                       → istorija migracija ne postoji ni u bazi;
--                                      poreklo se može zaključivati SAMO iz
--                                      artefakata (Q2/Q3/Q5).
--     ≥1 red                         → istorija postoji; pročitati je.
--
-- GRANICA KOJU OVAJ PROLAZ NE PRELAZI
-- Čak i kad Q2+Q3+Q4+Q5 prođu, ispravan zaključak je:
--     SCHEMA MATCH = VERIFIED
--     MIGRATION EXECUTION HISTORY = UNVERIFIABLE (osim ako Q6 nađe artefakt)
-- Stanje šeme odgovara očekivanom stanju posle 089. To nije isto što i dokaz
-- da je izvršen baš taj fajl.
-- ═══════════════════════════════════════════════════════════════════════════
