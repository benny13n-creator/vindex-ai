-- ============================================================================
-- Vindex AI -- Migracija 077: SEC-031 Phase 1 Safety Lock
-- ON DELETE CASCADE -> RESTRICT na auth.users FK-ovima
-- v3 -- name-agnostic, i svedena na CONFIRMED LIVE constraint-e
-- ============================================================================
--
-- ISTORIJA REVIZIJA:
--
-- v1 (prvi pokusaj): tvrdo zakucana imena constraint-a
-- (<tabela>_<kolona>_fkey). PALA na prvom pokretanju:
-- "predmet_delegiranja_od_user_id_fkey" ne postoji. GRUPA 1 transakcija se
-- bezbedno vratila, nijedan red podataka nije dotaknut.
--
-- v2: zamenjena tvrdo zakucana imena funkcijom _sec031_fix_fk() koja
-- PRONALAZI stvarno ime constraint-a preko pg_constraint umesto da ga
-- pretpostavlja.
--
-- v3 (ova verzija) -- POSLE stvarne produkcione dijagnostike (SS0 upit
-- pokrenut i vracen 2026-07-23): potvrdjeno da v2-ov problem NIJE bio samo
-- pogresno ime -- 3 od 19 planiranih (tabela, kolona) parova NE POSTOJE
-- u produkciji uopste (ni tabela, ni constraint):
--
--   * predmet_delegiranja.od_user_id / na_user_id -- migrations/054_
--     predmet_delegiranja.sql sopstveni komentar kaze "Tabela nikad nije
--     migrirana." Ovo NIJE SEC-031 problem -- to je odvojen, precizno
--     imenovan nalaz (routers/enterprise.py-ova dva endpointa za
--     delegiranje predmeta verovatno ne rade u produkciji uopste, jer im
--     tabela ne postoji). Van obima ove migracije.
--
--   * conversations.user_id -- definisana samo u legacy supabase_migration.sql
--     (ne u glavnoj migrations/ seriji), sumnja izrazena unapred u
--     SEC031_MIGRATION_DRY_RUN.md sada POTVRDJENA -- taj fajl ocigledno
--     nikad nije pokrenut protiv produkcije. Tabela ne postoji, pa nema
--     sta ni da se stiti trenutno.
--
--   * tos_acceptances.user_id -- OVO JE IZNENADJENJE, ne objasnjeno unapred
--     (056_tos_acceptances.sql je normalna, numerisana migracija, ne
--     legacy fajl). Zahteva POSEBNU proveru pre zakljucka -- videti
--     napomenu na dnu ovog fajla. NIJE uklonjeno iz ovog fajla zbog
--     pretpostavke da je "kao i ostala dva" -- uklonjeno iz aktivnog
--     pokretanja SAMO da ne blokira ostatak, dok se razlog ne potvrdi.
--
-- Preostalih 16 (tabela, kolona) parova SU potvrdjeni live u produkciji
-- (SS0 dijagnostika), sa ON DELETE CASCADE, tacno kako je i ocekivano.
-- GRUPA 2 (financial, svih 6) je bez izmene -- vec je bila potpuno tacna
-- i u v1 i v2, jer je za te tabele pretpostavljeno ime bilo tacno.
--
-- DO NOT RUN THIS BLINDLY. Pre ponovnog pokretanja:
--   1. Potvrditi SS0 dijagnostikom (ispod, read-only) da GRUPA 1 iz
--      neuspesnog v1/v2 pokusaja NIJE ostavila delimicno primenjene izmene
--      (transakcija bi trebalo da je sve vratila -- potvrditi, ne
--      pretpostaviti).
--   2. Proveriti da li GRUPA 2 (financial) mozda VEC uspesno prosla u
--      prethodnom pokusaju (v1/v2 su odvojene transakcije -- ako je GRUPA 1
--      pala, GRUPA 2/3 mozda nikad nisu ni pokusane, ili jesu i uspele).
--      SS0 dijagnostika to pokazuje direktno (confdeltype = 'r' znaci vec
--      RESTRICT).
--
-- Puna forenzicka analiza i nezavisan peer review:
--   docs/security/SEC031_IMPACT_ANALYSIS.md
--   docs/security/SEC031_FK_GRAPH.md
--   docs/security/SEC031_MIGRATION_SAFETY_PLAN.md
--   docs/security/SEC031_MIGRATION_DRY_RUN.md
--   docs/security/SEC031_PEER_REVIEW_CONSENSUS.md
--
-- Ovaj fajl i dalje ne menja NIJEDAN red podataka -- menja SAMO ON DELETE
-- pravilo na postojecim foreign key constraint-ima.
-- ============================================================================


-- ─── SS0: DIJAGNOSTIKA (read-only, pokrenuti PRVO i POSLE svake grupe) ────────
--
-- SELECT
--     conrelid::regclass AS tabela,
--     conname            AS constraint_ime,
--     pg_get_constraintdef(oid) AS definicija
-- FROM pg_constraint
-- WHERE confrelid = 'auth.users'::regclass
--   AND contype = 'f'
-- ORDER BY conrelid::regclass::text, conname;
--
-- Dodatna provera POSTOJI LI tabela uopste (za predmet_delegiranja,
-- conversations, tos_acceptances -- read-only, ne menja nista):
--
-- SELECT
--     'predmet_delegiranja' AS tabela, to_regclass('public.predmet_delegiranja') IS NOT NULL AS postoji
-- UNION ALL
-- SELECT 'conversations', to_regclass('public.conversations') IS NOT NULL
-- UNION ALL
-- SELECT 'tos_acceptances', to_regclass('public.tos_acceptances') IS NOT NULL;


-- ─── Pomocna funkcija: pronadji i promeni ON DELETE pravilo bez oslanjanja ────
-- ─── na pretpostavljeno ime constraint-a ──────────────────────────────────────
CREATE OR REPLACE FUNCTION _sec031_fix_fk(
    p_table  regclass,
    p_column text,
    p_new_rule text  -- 'RESTRICT' ili 'CASCADE'
) RETURNS void AS $BODY$
DECLARE
    v_conname   text;
    v_attnum    smallint;
BEGIN
    SELECT attnum INTO v_attnum
    FROM pg_attribute
    WHERE attrelid = p_table AND attname = p_column AND NOT attisdropped;

    IF v_attnum IS NULL THEN
        RAISE EXCEPTION 'Kolona %.% ne postoji', p_table, p_column;
    END IF;

    SELECT conname INTO v_conname
    FROM pg_constraint
    WHERE conrelid = p_table
      AND confrelid = 'auth.users'::regclass
      AND contype = 'f'
      AND conkey = ARRAY[v_attnum];

    IF v_conname IS NULL THEN
        RAISE EXCEPTION
            'Nijedan FK constraint na %.% koji referencira auth.users nije pronadjen -- proveri SS0 dijagnostiku',
            p_table, p_column;
    END IF;

    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', p_table, v_conname);
    EXECUTE format(
        'ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES auth.users(id) ON DELETE %s NOT VALID',
        p_table, v_conname, p_column, p_new_rule
    );
    EXECUTE format('ALTER TABLE %s VALIDATE CONSTRAINT %I', p_table, v_conname);

    RAISE NOTICE 'OK: %.% (constraint %) -> ON DELETE %', p_table, p_column, v_conname, p_new_rule;
END;
$BODY$ LANGUAGE plpgsql;


-- ─── GRUPA 1: Legal core (BEZ predmet_delegiranja i conversations --────────────
-- ─── potvrdjeno ne postoje u produkciji, videti napomenu na vrhu) ─────────────
BEGIN;
SELECT _sec031_fix_fk('predmeti',             'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_dokumenti',    'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_hronologija',  'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_beleske',      'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_istorija',     'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('user_knowledge',       'user_id',     'RESTRICT');
COMMIT;


-- ─── GRUPA 2: Financial (nepromenjeno -- svih 6 potvrdjeno live) ──────────────
BEGIN;
SELECT _sec031_fix_fk('fakture',                'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('billing_entries',        'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('timer_sessions',         'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('tarife',                 'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('tarifne_stavke_custom',  'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('sef_log',                'user_id', 'RESTRICT');
COMMIT;


-- ─── GRUPA 3: Ostali legal/compliance (BEZ tos_acceptances -- videti ──────────
-- ─── napomenu na vrhu, zahteva posebnu proveru pre dodavanja nazad) ───────────
BEGIN;
SELECT _sec031_fix_fk('praceni_predmeti',        'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('rocista',                 'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('smart_contract_analyses', 'user_id', 'RESTRICT');
COMMIT;


-- ============================================================================
-- ODLOZENO -- NE deo ovog pokretanja, cekaju posebnu odluku:
--
--   predmet_delegiranja.od_user_id / na_user_id
--     -> tabela ne postoji u produkciji (migracija 054 nikad pokrenuta).
--        Akcija: ili pokrenuti 054 prvo (ako je funkcija delegiranja
--        predmeta stvarno u upotrebi/planu), ili formalno zatvoriti kao
--        "feature nikad lansiran" i izbaciti iz Tier A liste trajno.
--
--   conversations.user_id
--     -> tabela ne postoji u produkciji (supabase_migration.sql, legacy
--        fajl, nikad pokrenut). Akcija: potvrditi da se ovaj put zaista
--        nigde ne koristi (vec potvrdjeno u SEC031_FK_GRAPH.md -- 0 poziva
--        u trenutnom kodu), pa formalno izbaciti iz Tier A liste, ili
--        pokrenuti taj legacy fajl ako se ispostavi da JESTE potreban.
--
--   tos_acceptances.user_id
--     -> NEOCEKIVANO odsutna iz produkcije uprkos numerisanoj migraciji
--        056. Zahteva: (a) potvrditi da tabela zaista ne postoji (SS0
--        dodatna provera iznad), (b) ako ne postoji, pokrenuti
--        056_tos_acceptances.sql pre nego sto se ovaj constraint doda,
--        (c) razmotriti da li nepostojanje ove tabele znaci da se
--        korisnicki pristanak na Uslove koriscenja TRENUTNO NE BELEZI
--        NIGDE u produkciji -- odvojeno, potencijalno bitnije pitanje od
--        same SEC-031 zakljucavanja.
-- ============================================================================


-- ============================================================================
-- VERIFIKACIJA POSLE POKRETANJA (read-only) -- ponoviti SS0 upit iznad.
-- 15 redova (GRUPA 1: 6, GRUPA 2: 6, GRUPA 3: 3) mora imati definiciju
-- koja sadrzi "ON DELETE RESTRICT".
-- ============================================================================


-- ============================================================================
-- ROLLBACK -- potpuno bezbedan (menja samo metapodatke). Koristi istu
-- _sec031_fix_fk funkciju sa 'CASCADE', radi bez obzira na trenutno ime.
-- ============================================================================
--
-- BEGIN;
-- SELECT _sec031_fix_fk('predmeti',             'user_id',     'CASCADE');
-- SELECT _sec031_fix_fk('predmet_dokumenti',    'user_id',     'CASCADE');
-- SELECT _sec031_fix_fk('predmet_hronologija',  'user_id',     'CASCADE');
-- SELECT _sec031_fix_fk('predmet_beleske',      'user_id',     'CASCADE');
-- SELECT _sec031_fix_fk('predmet_istorija',     'user_id',     'CASCADE');
-- SELECT _sec031_fix_fk('user_knowledge',       'user_id',     'CASCADE');
-- SELECT _sec031_fix_fk('fakture',                'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('billing_entries',        'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('timer_sessions',         'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('tarife',                 'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('tarifne_stavke_custom',  'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('sef_log',                'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('praceni_predmeti',        'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('rocista',                 'user_id', 'CASCADE');
-- SELECT _sec031_fix_fk('smart_contract_analyses', 'user_id', 'CASCADE');
-- COMMIT;
--
-- DROP FUNCTION IF EXISTS _sec031_fix_fk(regclass, text, text);
-- ============================================================================
