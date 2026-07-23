-- ============================================================================
-- Vindex AI -- Migracija 077: SEC-031 Phase 1 Safety Lock
-- ON DELETE CASCADE -> RESTRICT na auth.users FK-ovima (Tier A, 19 constraint-a)
-- ============================================================================
--
-- DO NOT RUN THIS BLINDLY. Pre pokretanja, obavezno:
--
--   1. Izvrsiti Production Reality Gate provere iz
--      docs/security/SEC031_PRODUCTION_ASSUMPTIONS.md (stavke 1, 5, 7) --
--      posebno information_schema upit koji potvrdjuje da su imena
--      constraint-a ispod ZAISTA <tabela>_<kolona>_fkey u produkciji (default
--      Postgres konvencija za neimenovan inline FK -- pretpostavljeno, nije
--      potvrdjeno protiv zive baze).
--   2. Potvrditi da tabela `conversations` postoji u produkciji (definisana
--      je samo u legacy supabase_migration.sql, ne u glavnoj migrations/
--      seriji -- ako ne postoji, GRUPA 1 ispod ce pasti na toj jednoj
--      izjavi; obrisati taj blok ako tabela ne postoji, ili pustiti da
--      padne -- DROP/ADD CONSTRAINT na nepostojecoj tabeli je bezbedna,
--      jasna greska, ne tiha posledica).
--
-- Ovaj fajl ne menja NIJEDAN red podataka -- menja SAMO ON DELETE pravilo na
-- 19 postojecih foreign key constraint-a (CASCADE -> RESTRICT). Efekat:
-- direktno brisanje reda u auth.users vise nece moci da lancano obrise
-- predmete/klijente/fakture/dokaze -- Postgres ce odbiti (foreign key
-- violation) ako korisnik ima I JEDAN red u bilo kojoj od ovih tabela.
--
-- Puna forenzicka analiza, dokaz da 19 constraint-a stiti ceo graf
-- (ukljucujuci transitivno ~56 tabela), i nezavisan peer review:
--   docs/security/SEC031_IMPACT_ANALYSIS.md
--   docs/security/SEC031_FK_GRAPH.md
--   docs/security/SEC031_MIGRATION_SAFETY_PLAN.md
--   docs/security/SEC031_MIGRATION_DRY_RUN.md  (ovaj fajl je doslovna
--                                                 transkripcija njegovog SS2)
--   docs/security/SEC031_PEER_REVIEW_CONSENSUS.md
--
-- ROLLBACK: SS na dnu ovog fajla -- potpuno bezbedan, ne dira podatke,
-- samo vraca ON DELETE CASCADE na svih 19 constraint-a.
--
-- Podeljeno u 3 manje transakcije (ne jedna od 19) -- namerno, iz
-- SEC031_MIGRATION_DRY_RUN.md SS3 revizije: svaki DROP/ADD CONSTRAINT na FK
-- koji referencira auth.users uzima ShareRowExclusiveLock na SAMOJ
-- auth.users tabeli (ne samo na tabeli koja deklarise FK) -- to znaci da
-- signup/login mogu kratko da cekaju iza migracije. Manje transakcije =
-- kraci pojedinacni prozor zakljucavanja. Pokrenuti grupe REDOM, jednu po
-- jednu (nezavisne su, ali redosled ovde je isti kao u dry-run dokumentu
-- radi lakseg pracenja).
-- ============================================================================


-- ─── GRUPA 1: Legal core (predmeti + direktna deca + user_knowledge/conversations) ───
-- 10 constraint-a: predmeti, predmet_dokumenti, predmet_hronologija,
-- predmet_beleske, predmet_istorija, predmet_delegiranja (x2),
-- user_knowledge, conversations

BEGIN;

ALTER TABLE predmeti DROP CONSTRAINT predmeti_user_id_fkey;
ALTER TABLE predmeti ADD CONSTRAINT predmeti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmeti VALIDATE CONSTRAINT predmeti_user_id_fkey;

ALTER TABLE predmet_dokumenti DROP CONSTRAINT predmet_dokumenti_user_id_fkey;
ALTER TABLE predmet_dokumenti ADD CONSTRAINT predmet_dokumenti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_dokumenti VALIDATE CONSTRAINT predmet_dokumenti_user_id_fkey;

ALTER TABLE predmet_hronologija DROP CONSTRAINT predmet_hronologija_user_id_fkey;
ALTER TABLE predmet_hronologija ADD CONSTRAINT predmet_hronologija_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_hronologija VALIDATE CONSTRAINT predmet_hronologija_user_id_fkey;

ALTER TABLE predmet_beleske DROP CONSTRAINT predmet_beleske_user_id_fkey;
ALTER TABLE predmet_beleske ADD CONSTRAINT predmet_beleske_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_beleske VALIDATE CONSTRAINT predmet_beleske_user_id_fkey;

ALTER TABLE predmet_istorija DROP CONSTRAINT predmet_istorija_user_id_fkey;
ALTER TABLE predmet_istorija ADD CONSTRAINT predmet_istorija_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_istorija VALIDATE CONSTRAINT predmet_istorija_user_id_fkey;

ALTER TABLE predmet_delegiranja DROP CONSTRAINT predmet_delegiranja_od_user_id_fkey;
ALTER TABLE predmet_delegiranja ADD CONSTRAINT predmet_delegiranja_od_user_id_fkey
    FOREIGN KEY (od_user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_delegiranja VALIDATE CONSTRAINT predmet_delegiranja_od_user_id_fkey;

ALTER TABLE predmet_delegiranja DROP CONSTRAINT predmet_delegiranja_na_user_id_fkey;
ALTER TABLE predmet_delegiranja ADD CONSTRAINT predmet_delegiranja_na_user_id_fkey
    FOREIGN KEY (na_user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_delegiranja VALIDATE CONSTRAINT predmet_delegiranja_na_user_id_fkey;

ALTER TABLE user_knowledge DROP CONSTRAINT user_knowledge_user_id_fkey;
ALTER TABLE user_knowledge ADD CONSTRAINT user_knowledge_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE user_knowledge VALIDATE CONSTRAINT user_knowledge_user_id_fkey;

-- conversations: definisana samo u legacy supabase_migration.sql. Ako ova
-- tabela ne postoji u produkciji, ovaj blok ce pasti sa jasnom "relation
-- does not exist" greskom -- OBRISATI OVAJ BLOK i ponovo pokrenuti GRUPU 1
-- bez njega ako se to desi, ne pokusavati "popraviti" tabelu koja ne
-- postoji.
ALTER TABLE conversations DROP CONSTRAINT conversations_user_id_fkey;
ALTER TABLE conversations ADD CONSTRAINT conversations_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE conversations VALIDATE CONSTRAINT conversations_user_id_fkey;

COMMIT;


-- ─── GRUPA 2: Financial (fakture, billing, tarife) ────────────────────────────
-- 6 constraint-a: fakture, billing_entries, timer_sessions, tarife,
-- tarifne_stavke_custom, sef_log

BEGIN;

ALTER TABLE fakture DROP CONSTRAINT fakture_user_id_fkey;
ALTER TABLE fakture ADD CONSTRAINT fakture_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE fakture VALIDATE CONSTRAINT fakture_user_id_fkey;

ALTER TABLE billing_entries DROP CONSTRAINT billing_entries_user_id_fkey;
ALTER TABLE billing_entries ADD CONSTRAINT billing_entries_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE billing_entries VALIDATE CONSTRAINT billing_entries_user_id_fkey;

ALTER TABLE timer_sessions DROP CONSTRAINT timer_sessions_user_id_fkey;
ALTER TABLE timer_sessions ADD CONSTRAINT timer_sessions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE timer_sessions VALIDATE CONSTRAINT timer_sessions_user_id_fkey;

ALTER TABLE tarife DROP CONSTRAINT tarife_user_id_fkey;
ALTER TABLE tarife ADD CONSTRAINT tarife_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE tarife VALIDATE CONSTRAINT tarife_user_id_fkey;

ALTER TABLE tarifne_stavke_custom DROP CONSTRAINT tarifne_stavke_custom_user_id_fkey;
ALTER TABLE tarifne_stavke_custom ADD CONSTRAINT tarifne_stavke_custom_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE tarifne_stavke_custom VALIDATE CONSTRAINT tarifne_stavke_custom_user_id_fkey;

ALTER TABLE sef_log DROP CONSTRAINT sef_log_user_id_fkey;
ALTER TABLE sef_log ADD CONSTRAINT sef_log_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE sef_log VALIDATE CONSTRAINT sef_log_user_id_fkey;

COMMIT;


-- ─── GRUPA 3: Ostali legal/compliance (rocista, praceni predmeti, itd.) ──────
-- 3 constraint-a: praceni_predmeti, rocista, smart_contract_analyses,
-- tos_acceptances (4 tabele -- komentar iznad govori o brojnosti tabela u
-- ovoj grupi, ne kolona; sve su 1:1 kolona:constraint)

BEGIN;

ALTER TABLE praceni_predmeti DROP CONSTRAINT praceni_predmeti_user_id_fkey;
ALTER TABLE praceni_predmeti ADD CONSTRAINT praceni_predmeti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE praceni_predmeti VALIDATE CONSTRAINT praceni_predmeti_user_id_fkey;

ALTER TABLE rocista DROP CONSTRAINT rocista_user_id_fkey;
ALTER TABLE rocista ADD CONSTRAINT rocista_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE rocista VALIDATE CONSTRAINT rocista_user_id_fkey;

ALTER TABLE smart_contract_analyses DROP CONSTRAINT smart_contract_analyses_user_id_fkey;
ALTER TABLE smart_contract_analyses ADD CONSTRAINT smart_contract_analyses_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE smart_contract_analyses VALIDATE CONSTRAINT smart_contract_analyses_user_id_fkey;

ALTER TABLE tos_acceptances DROP CONSTRAINT tos_acceptances_user_id_fkey;
ALTER TABLE tos_acceptances ADD CONSTRAINT tos_acceptances_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE tos_acceptances VALIDATE CONSTRAINT tos_acceptances_user_id_fkey;

COMMIT;


-- ============================================================================
-- VERIFIKACIJA POSLE POKRETANJA (read-only, bezbedno pokrenuti odmah posle):
--
-- SELECT conrelid::regclass AS tabela, conname, confdeltype
-- FROM pg_constraint
-- WHERE confrelid = 'auth.users'::regclass AND contype = 'f'
-- ORDER BY conrelid::regclass::text;
--
-- confdeltype mora biti 'r' (RESTRICT) za svih 19 redova iznad -- 'c' bi
-- znacilo da je ta konkretna izmena tiho preskocena/pala.
-- ============================================================================


-- ============================================================================
-- ROLLBACK -- potpuno bezbedan (menja samo metapodatke, ne dira nijedan red).
-- Pokrenuti kompletno ispod ako treba vratiti CASCADE ponasanje.
-- ============================================================================
--
-- BEGIN;
-- ALTER TABLE predmeti DROP CONSTRAINT predmeti_user_id_fkey;
-- ALTER TABLE predmeti ADD CONSTRAINT predmeti_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmeti VALIDATE CONSTRAINT predmeti_user_id_fkey;
--
-- ALTER TABLE predmet_dokumenti DROP CONSTRAINT predmet_dokumenti_user_id_fkey;
-- ALTER TABLE predmet_dokumenti ADD CONSTRAINT predmet_dokumenti_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmet_dokumenti VALIDATE CONSTRAINT predmet_dokumenti_user_id_fkey;
--
-- ALTER TABLE predmet_hronologija DROP CONSTRAINT predmet_hronologija_user_id_fkey;
-- ALTER TABLE predmet_hronologija ADD CONSTRAINT predmet_hronologija_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmet_hronologija VALIDATE CONSTRAINT predmet_hronologija_user_id_fkey;
--
-- ALTER TABLE predmet_beleske DROP CONSTRAINT predmet_beleske_user_id_fkey;
-- ALTER TABLE predmet_beleske ADD CONSTRAINT predmet_beleske_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmet_beleske VALIDATE CONSTRAINT predmet_beleske_user_id_fkey;
--
-- ALTER TABLE predmet_istorija DROP CONSTRAINT predmet_istorija_user_id_fkey;
-- ALTER TABLE predmet_istorija ADD CONSTRAINT predmet_istorija_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmet_istorija VALIDATE CONSTRAINT predmet_istorija_user_id_fkey;
--
-- ALTER TABLE predmet_delegiranja DROP CONSTRAINT predmet_delegiranja_od_user_id_fkey;
-- ALTER TABLE predmet_delegiranja ADD CONSTRAINT predmet_delegiranja_od_user_id_fkey
--     FOREIGN KEY (od_user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmet_delegiranja VALIDATE CONSTRAINT predmet_delegiranja_od_user_id_fkey;
--
-- ALTER TABLE predmet_delegiranja DROP CONSTRAINT predmet_delegiranja_na_user_id_fkey;
-- ALTER TABLE predmet_delegiranja ADD CONSTRAINT predmet_delegiranja_na_user_id_fkey
--     FOREIGN KEY (na_user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE predmet_delegiranja VALIDATE CONSTRAINT predmet_delegiranja_na_user_id_fkey;
--
-- ALTER TABLE user_knowledge DROP CONSTRAINT user_knowledge_user_id_fkey;
-- ALTER TABLE user_knowledge ADD CONSTRAINT user_knowledge_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE user_knowledge VALIDATE CONSTRAINT user_knowledge_user_id_fkey;
--
-- ALTER TABLE conversations DROP CONSTRAINT conversations_user_id_fkey;
-- ALTER TABLE conversations ADD CONSTRAINT conversations_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE conversations VALIDATE CONSTRAINT conversations_user_id_fkey;
--
-- ALTER TABLE fakture DROP CONSTRAINT fakture_user_id_fkey;
-- ALTER TABLE fakture ADD CONSTRAINT fakture_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE fakture VALIDATE CONSTRAINT fakture_user_id_fkey;
--
-- ALTER TABLE billing_entries DROP CONSTRAINT billing_entries_user_id_fkey;
-- ALTER TABLE billing_entries ADD CONSTRAINT billing_entries_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE billing_entries VALIDATE CONSTRAINT billing_entries_user_id_fkey;
--
-- ALTER TABLE timer_sessions DROP CONSTRAINT timer_sessions_user_id_fkey;
-- ALTER TABLE timer_sessions ADD CONSTRAINT timer_sessions_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE timer_sessions VALIDATE CONSTRAINT timer_sessions_user_id_fkey;
--
-- ALTER TABLE tarife DROP CONSTRAINT tarife_user_id_fkey;
-- ALTER TABLE tarife ADD CONSTRAINT tarife_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE tarife VALIDATE CONSTRAINT tarife_user_id_fkey;
--
-- ALTER TABLE tarifne_stavke_custom DROP CONSTRAINT tarifne_stavke_custom_user_id_fkey;
-- ALTER TABLE tarifne_stavke_custom ADD CONSTRAINT tarifne_stavke_custom_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE tarifne_stavke_custom VALIDATE CONSTRAINT tarifne_stavke_custom_user_id_fkey;
--
-- ALTER TABLE sef_log DROP CONSTRAINT sef_log_user_id_fkey;
-- ALTER TABLE sef_log ADD CONSTRAINT sef_log_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE sef_log VALIDATE CONSTRAINT sef_log_user_id_fkey;
--
-- ALTER TABLE praceni_predmeti DROP CONSTRAINT praceni_predmeti_user_id_fkey;
-- ALTER TABLE praceni_predmeti ADD CONSTRAINT praceni_predmeti_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE praceni_predmeti VALIDATE CONSTRAINT praceni_predmeti_user_id_fkey;
--
-- ALTER TABLE rocista DROP CONSTRAINT rocista_user_id_fkey;
-- ALTER TABLE rocista ADD CONSTRAINT rocista_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE rocista VALIDATE CONSTRAINT rocista_user_id_fkey;
--
-- ALTER TABLE smart_contract_analyses DROP CONSTRAINT smart_contract_analyses_user_id_fkey;
-- ALTER TABLE smart_contract_analyses ADD CONSTRAINT smart_contract_analyses_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE smart_contract_analyses VALIDATE CONSTRAINT smart_contract_analyses_user_id_fkey;
--
-- ALTER TABLE tos_acceptances DROP CONSTRAINT tos_acceptances_user_id_fkey;
-- ALTER TABLE tos_acceptances ADD CONSTRAINT tos_acceptances_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
-- ALTER TABLE tos_acceptances VALIDATE CONSTRAINT tos_acceptances_user_id_fkey;
-- COMMIT;
-- ============================================================================
