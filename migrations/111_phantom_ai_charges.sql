-- ============================================================================
-- Vindex AI — Migracija 111: naplata za operacije koje nemaju AI poziv (P0-C)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor. Idempotentno.
--
-- ŠTA JE PRONAĐENO
-- Otvaranje ekrana „Podešavanja" naplaćivalo je 1 AI kredit. Nije bilo dugmeta
-- ni potvrde: `settingsLoad()` (static/vindex.js:2265) bezuslovno zove
-- `confidenceAuditLoad()` (:2278) → GET /api/audit/kalibracija →
-- `UsageService.consume(..., "confidence_audit")` (routers/confidence_audit.py:47).
--
-- `services/confidence_auditor.py` NEMA nijedan AI poziv — to je Brier proračun
-- nad korisnikovim sopstvenim redovima. Registry je pritom deklarisao
-- `ai_model='gpt-4o-mini'` za funkciju koja nikad ne dodirne model.
--
-- OBRAZAC, NE IZOLOVAN BUG — ALI SE LEČI NA DVA RAZLIČITA MESTA
-- Sedam naplatnih mesta naplaćuje bez dostižnog AI poziva. Ključna razlika,
-- utvrđena AST analizom svakog mesta pojedinačno:
--
--   A) `feature_key` čija SVA naplatna mesta nemaju AI  →  popravlja se OVDE
--      confidence_audit           3 mesta  confidence_audit.py:47, :99, :125
--      conflict_check             1 mesto  conflict_check.py:385
--      da_wallet_risk_assessment  1 mesto  wallet_provenance.py:320
--      (`conflict_check.py` i `wallet_provenance.py` nemaju ni `import openai`)
--
--   B) `feature_key` DELJEN sa endpointima koji STVARNO zovu GPT
--                                  →  NE sme se dirati ovde, popravlja se u kodu
--      case_commander         4 mesta: :445 commander_analiza    → IMA AI
--                                      :483 commander_quick_check → NEMA
--                                      :560 commander_checklist   → IMA AI
--                                      :1006 commander_jutarnji   → IMA (posredno)
--      zastarelost_guardian   2 mesta: :442 deadline_guardian     → IMA AI
--                                      :476 guardian_scan         → NEMA
--
-- ZAŠTO JE OVA PODELA VAŽNA
-- Prvobitni predlog je bio da se svih pet ključeva postavi na `krediti=0`. To bi
-- za grupu B bilo pogrešno: `case_commander` i `zastarelost_guardian` su isti
-- ključ za AI i ne-AI endpointe, pa bi `krediti=0` POKLONIO stvarnu GPT
-- potrošnju besplatno — skuplja greška od one koja se ispravlja. Za njih se
-- uklanja `consume()` poziv sa ne-AI endpointa; cena ključa ostaje netaknuta.
--
-- UZROK — jedan commit
-- `73083099` (2026-07-14), „wire PermissionService/UsageService into all AI
-- endpoints", 60 fajlova. Masovno je primenio obrazac na svaki endpoint koji je
-- Registry OPISIVAO kao AI — verujući koloni `ai_model` kao dokazu da AI poziv
-- postoji. `confidence_audit` i `conflict_check` su pre toga bili
-- `Depends(get_current_user)`: besplatni i otvoreni svim tarifama.
-- `case_commander.py:483` je drugi slučaj: Program Sigma Sprint 005 je kasnije
-- UKLONIO GPT poziv, a `consume()` ostavio.
--
-- ZAŠTO GA NIJEDNA PROVERA NIJE UHVATILA
-- `scripts/validate_feature_registry.py:76` upozorava na „krediti>0 a `ai_model`
-- prazan" — tačno OBRNUTO od stvarnog defekta. Red koji samouvereno deklariše
-- `gpt-4o-mini` za funkciju bez AI prolazi svaku postojeću proveru.
--
-- PRESEDAN
-- `migrations/070_feature_registry_feature_type.sql:62-66` je isti postupak nad
-- `firm_memory`/`knowledge_hygiene`. Semantika `chargeable` je tamo izričito
-- definisana (070:29-34): false SAMO za funkcije bez AI poziva — NE za namerno
-- besplatne poslovne odluke (`morning_briefing`, `voice`, `sudska_praksa`
-- ostaju `chargeable=true` sa `krediti=0`).
--
-- ZAŠTO `krediti=0` A NE UKLANJANJE `consume()` ZA GRUPU A
-- `shared/usage.py:396` gejtuje odbitak sa `if n_credits > 0:`. Sa `krediti=0`
-- ostaje sve osim naplate: cooldown claim (:321), dnevni/mesečni limit
-- (:339-362), autoritativni brojač (:385) i telemetrija (:476). Uklanjanje
-- poziva bi obrisalo i telemetriju i kuku za buduće limite.
-- ============================================================================

BEGIN;

-- ── A) Ključevi čija sva naplatna mesta nemaju AI poziv ─────────────────────
UPDATE public.feature_registry
   SET krediti    = 0,
       chargeable = false,
       updated_at = now(),
       updated_by = 'migration_111_phantom_ai_charges'
 WHERE feature_key IN (
        'confidence_audit',
        'conflict_check',
        'da_wallet_risk_assessment'
      );

-- ── B) Registry više ne sme da tvrdi model koji se nikad ne poziva ──────────
-- `ai_model` je do sada bila jedini „dokaz" na koji se oslanjala validacija.
-- Ako funkcija nema AI poziv, kolona mora biti prazna — inače sledeći masovni
-- prolaz ponovi grešku iz `73083099`.
UPDATE public.feature_registry
   SET ai_model   = NULL,
       updated_at = now(),
       updated_by = 'migration_111_phantom_ai_charges'
 WHERE feature_key IN (
        'confidence_audit',
        'conflict_check',
        'da_wallet_risk_assessment'
      )
   AND ai_model IS NOT NULL;

-- ── C) `confidence_audit` — vraćanje tarifne kapije na zatečeno stanje ──────
-- NIJE nova poslovna odluka nego povratak na pre-`73083099` stanje, kad je
-- endpoint bio `Depends(get_current_user)` — dostupan svima. Taj commit ga je
-- usput zaključao na `professional`, pa svaki `basic` korisnik od tada dobija
-- 403 čim otvori Podešavanja, iscrtan kao crvena „Greška:" kutija unutar
-- kartice (static/vindex.js:2379).
--
-- Dokaz da je besplatno-i-otvoreno ispravno stanje: `learningStatsLoad`
-- (static/vindex.js:2279) je ista vrsta funkcije — istorijska statistika nad
-- sopstvenim redovima, ista tabla Podešavanja, jedna kartica dalje — i
-- ispravno je besplatna i negejtovana (`routers/court_predictor.py:1758`).
-- Od sedam učitavača koje `settingsLoad` poziva, `confidence_audit` je jedini
-- gejtovan i naplativ.
--
-- 'basic' a NE NULL: NULL znači „otključava se ISKLJUČIVO preko addon-a"
-- (064:37-38). 'basic' je najniža tarifa u `_TIER_ORDER`
-- (shared/permissions.py:59), pa `_tier_satisfies` propušta sve.
UPDATE public.feature_registry
   SET minimum_plan = 'basic',
       updated_at   = now(),
       updated_by   = 'migration_111_phantom_ai_charges'
 WHERE feature_key = 'confidence_audit';

-- ── D) Budžetski ventil ─────────────────────────────────────────────────────
-- `confidence_audit` je jedini od četiri naplativa učitavača ekrana bez ijedne
-- zaštite: nema keš, nema cooldown, nema dnevni ni mesečni limit. Uz to
-- `index.html:3561` stavlja dugme „↻ Osveži" tačno tu. Cena je sada 0, ali
-- proračun i dalje pravi tri upita po pozivu. Obrazac preuzet od
-- `predmet_workspace_ai` (064:144, 065:117), koji se takođe izvršava pri
-- otvaranju ekrana i zato ima cooldown.
UPDATE public.feature_registry
   SET cooldown_seconds = 5,
       updated_at       = now(),
       updated_by       = 'migration_111_phantom_ai_charges'
 WHERE feature_key = 'confidence_audit'
   AND (cooldown_seconds IS NULL OR cooldown_seconds < 5);

COMMIT;

-- ============================================================================
-- VERIFIKACIJA (read-only, pokrenuti posle)
-- ============================================================================
-- 1) Očekivano: 3 reda, svi krediti=0, chargeable=false, ai_model prazan;
--    confidence_audit sa minimum_plan='basic', cooldown_seconds=5.
--
--   SELECT feature_key, krediti, chargeable, ai_model, minimum_plan,
--          cooldown_seconds, updated_by
--     FROM public.feature_registry
--    WHERE feature_key IN ('confidence_audit','conflict_check',
--                          'da_wallet_risk_assessment')
--    ORDER BY feature_key;
--
-- 2) KONTROLA — deljeni ključevi grupe B MORAJU ostati NETAKNUTI (krediti > 0).
--    Ako su ovde 0, neko je proširio migraciju i poklonio stvarnu GPT potrošnju:
--
--   SELECT feature_key, krediti, chargeable FROM public.feature_registry
--    WHERE feature_key IN ('case_commander','zastarelost_guardian');
--
-- 3) KONTROLA — namerno besplatne poslovne odluke ostaju chargeable=true:
--
--   SELECT feature_key, krediti, chargeable FROM public.feature_registry
--    WHERE feature_key IN ('morning_briefing','voice','sudska_praksa');
--
-- ============================================================================
-- ŠTA OVA MIGRACIJA NE REŠAVA (otvoreno, zaseban zadatak)
-- ============================================================================
-- 15 mesta obavija AI poziv u `try/except`, degradira na fallback, pa naplati
-- bezuslovno — korisnik plaća i kad AI korak tiho padne. Najgora tri naplaćuju
-- PRE nego što se provajder uopšte pozove: `routers/profitabilnost.py:321`,
-- `routers/voice.py:541`, `routers/copilot.py:1445`.
--
-- Ispravan obrazac već postoji u repou: `routers/precedenti.py:178` naplaćuje
-- unutar `else:` grane `try` bloka; `routers/evidence.py:485-487` izričito
-- preskače naplatu kad klasifikacija padne; `routers/cio.py:670` gejtuje
-- naplatu na stvarno obavljen posao.
-- ============================================================================
