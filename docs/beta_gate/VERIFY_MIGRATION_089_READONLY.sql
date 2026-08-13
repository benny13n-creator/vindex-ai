-- ═══════════════════════════════════════════════════════════════════════════
-- READ-ONLY verifikacija migracije 089 (AI Provenance Extension).
-- Ništa ovde ne piše. Nema INSERT/UPDATE/DELETE/ALTER/CREATE/DROP.
-- Nalepite izlaz nazad.
--
-- ZAŠTO JE OVO JOŠ POTREBNO
--
-- Iz aplikacije je već DOKAZANO, bez ijednog pročitanog reda, da svih 19
-- kolona koje 089 dodaje postoje u produkciji: sonda `select(<kolona>).limit(0)`
-- prošla je za svih 19, plus svih 10 legacy kolona iz migracije 043. Runtime
-- (`security/ai_forensics.py::log_provenance_from_wrapper`) upisuje tačno tih
-- 29 kolona — dakle šema pokriva ono što runtime traži.
--
-- Utvrđeno je i da 089 JESTE jedini artefakt u repou koji te kolone dodaje na
-- `ai_forensics`: migracija 112 dodaje `predmet_id`/`correlation_id` na
-- `feature_usage_log` (druga tabela), 090 nema nijedan `ADD COLUMN`, a 043
-- kreira tabelu samo sa legacy skupom.
--
-- Ono što sonda iz aplikacije NE MOŽE da vidi:
--   1. indekse (PostgREST ih ne izlaže),
--   2. `UPDATE`-blokirajući trigger — njegova provera bi zahtevala UPDATE,
--      dakle mutaciju, što je u ovom sprintu zabranjeno,
--      3. tipove kolona i eventualne NOT NULL/DEFAULT razlike.
--
-- Q1–Q4 zatvaraju tačno to i samo to.
-- ═══════════════════════════════════════════════════════════════════════════

-- Q1 ── Kolone koje 089 dodaje, sa tipovima i nullability.
-- OČEKUJE se 19 redova. Svih 19 mora imati `is_nullable = YES` (089 ih dodaje
-- bez NOT NULL), jer runtime šalje `None` za nepopunjena polja.
-- PAD ako neka nedostaje ili je NOT NULL bez DEFAULT-a — tada bi širok upis
-- padao iz razloga koji NIJE „kolona ne postoji", pa runtime ne bi ni prešao
-- na legacy granu nego bi izgubio red u celosti.
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

-- Q2 ── Četiri indeksa koje 089 kreira.
-- OČEKUJE se tačno ova četiri:
--   idx_ai_forensics_correlation_id
--   idx_ai_forensics_predmet_id
--   idx_ai_forensics_module_name
--   idx_ai_forensics_status        (parcijalni, WHERE status = 'error')
-- Ako ih nema, kolone postoje ali su ih dodali ručno — a ne 089.
-- To je razlika između SCHEMA CAPABILITY i MIGRATION STATUS.
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename  = 'ai_forensics'
ORDER BY indexname;

-- Q3 ── Trigger za nepromenljivost (immutability).
-- OČEKUJE se `trg_protect_ai_forensics_update`, BEFORE UPDATE, koji zove
-- `protect_ai_forensics_from_update()`.
-- NAMERNO ne blokira DELETE — `services/retention_service.py` legitimno briše
-- redove starije od retencionog roka (GDPR storage limitation).
-- PAD ako ga nema: provenance red se tada može TIHO PREPISATI, čime prestaje
-- da bude upotrebljiv kao forenzički dokaz.
SELECT t.tgname,
       CASE t.tgtype & 2 WHEN 2 THEN 'BEFORE' ELSE 'AFTER' END AS timing,
       p.proname AS funkcija
FROM pg_trigger t
JOIN pg_class  c ON c.oid = t.tgrelid
JOIN pg_proc   p ON p.oid = t.tgfoid
WHERE c.relname = 'ai_forensics'
  AND NOT t.tgisinternal
ORDER BY t.tgname;

-- Q4 ── Telo funkcije koju trigger zove.
-- Postojanje trigera ne dokazuje da telo zaista odbija UPDATE.
-- OČEKUJE se `RAISE EXCEPTION` (ili ekvivalent) na svakoj UPDATE putanji.
SELECT p.proname, pg_get_functiondef(p.oid) AS telo
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname = 'protect_ai_forensics_from_update';

-- ═══════════════════════════════════════════════════════════════════════════
-- KAKO ČITATI REZULTAT
--
-- Q1 = 19 redova, svi nullable   → runtime dependency je ZADOVOLJEN.
--                                  Ovo je jedini uslov koji GT-001 traži.
-- Q2 = sva četiri indeksa        → 089 je izvršena onako kako je napisana.
--      manje od četiri           → kolone su dodate, ali NE ovom migracijom
--                                  (ručni `ALTER` ili delimično izvršavanje).
-- Q3 + Q4 potvrđuju nepromenljivost, koja je zaseban ugovor od GT-001.
--
-- Ako Q1 prođe a Q2 ne — to NIJE blocker za GT-001, ali jeste drift koji
-- treba imenovati: šema radi, ali njeno poreklo nije 089.
-- ═══════════════════════════════════════════════════════════════════════════
