-- ============================================================================
-- Vindex AI -- Migracija 077: SEC-031 Phase 1 Safety Lock
-- ON DELETE CASCADE -> RESTRICT na auth.users FK-ovima
-- v4 -- name-agnostic, 18 potvrdjenih parova (posle 054+056 pokretanja)
-- ============================================================================
--
-- ISTORIJA REVIZIJA:
--
-- v1: tvrdo zakucana imena constraint-a. PALA na prvom pokretanju --
-- "predmet_delegiranja_od_user_id_fkey" ne postoji. GRUPA 1 transakcija se
-- bezbedno vratila, nijedan red podataka nije dotaknut.
--
-- v2: zamenjena tvrdo zakucana imena funkcijom _sec031_fix_fk() koja
-- PRONALAZI stvarno ime constraint-a preko pg_constraint.
--
-- v3: posle stvarne produkcione dijagnostike, potvrdjeno da 3 od 19
-- planiranih parova (predmet_delegiranja x2, conversations, tos_acceptances)
-- NE POSTOJE u produkciji uopste -- uklonjeni iz aktivnog pokretanja (15
-- parova), dokumentovani u ODLOZENO sekciji.
--
-- v4 (ova verzija, 2026-07-23) -- POSLE pokretanja migracija 054
-- (predmet_delegiranja) i 056 (tos_acceptances) u produkciji: te dve tabele
-- sada postoje. Vraceni njihovi parovi u aktivnu listu (18 ukupno).
-- `conversations` OSTAJE TRAJNO ISKLJUCENA -- legacy tabela, nula poziva u
-- trenutnom kodu (predmet_istorija je zamenio tu funkciju), nema razloga da
-- se vraca u zivot samo da bi SEC-031 mogao da je "zastiti".
--
-- DO NOT RUN THIS BLINDLY. Pre pokretanja:
--   1. Potvrditi SS0 dijagnostikom (ispod, read-only) TRENUTNO stanje --
--      posebno da li je GRUPA 2/3 iz ranijeg v1/v2/v3 pokusaja mozda VEC
--      uspesno prosla (moguce je da je samo GRUPA 1 ikad pala, a GRUPA 2/3
--      vec bila pokrenuta i uspela u nekom ranijem pokusaju). Ako jesu,
--      ponovno pokretanje ovog fajla je i dalje bezbedno (funkcija samo
--      ponovo potvrdjuje isto RESTRICT pravilo -- ne baca gresku ako je
--      vec RESTRICT), samo suvisno -- ali bolje potvrditi nego pretpostaviti.
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
-- Dodatna provera (read-only, ne menja nista) -- predmet_delegiranja i
-- tos_acceptances su POTVRDJENE kao pokrenute (migracije 054 i 056), ova
-- provera je sad samo za conversations (ocekivano: false, trajno):
--
-- SELECT 'conversations' AS tabela, to_regclass('public.conversations') IS NOT NULL AS postoji;


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


-- ─── GRUPA 1: Legal core (predmet_delegiranja VRACENA -- 054 pokrenuta; ───────
-- ─── conversations OSTAJE ISKLJUCENA -- trajno, ne postoji, ne treba) ─────────
BEGIN;
SELECT _sec031_fix_fk('predmeti',             'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_dokumenti',    'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_hronologija',  'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_beleske',      'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_istorija',     'user_id',     'RESTRICT');
SELECT _sec031_fix_fk('predmet_delegiranja',  'od_user_id',  'RESTRICT');
SELECT _sec031_fix_fk('predmet_delegiranja',  'na_user_id',  'RESTRICT');
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


-- ─── GRUPA 3: Ostali legal/compliance (tos_acceptances VRACENA -- 056 ────────
-- ─── pokrenuta) ────────────────────────────────────────────────────────────
BEGIN;
SELECT _sec031_fix_fk('praceni_predmeti',        'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('rocista',                 'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('smart_contract_analyses', 'user_id', 'RESTRICT');
SELECT _sec031_fix_fk('tos_acceptances',         'user_id', 'RESTRICT');
COMMIT;


-- ============================================================================
-- ODLOZENO TRAJNO -- namerno NE deo ovog ili bilo kog buduceg pokretanja:
--
--   conversations.user_id
--     -> tabela ne postoji u produkciji (supabase_migration.sql, legacy
--        fajl, nikad pokrenut). Potvrdjeno u SEC031_FK_GRAPH.md -- 0 poziva
--        u trenutnom kodu (predmet_istorija je zamenio tu funkciju jos
--        ranije). Nema razloga da se ova tabela vraca u zivot -- formalno
--        izbacena iz Tier A liste, ne "ceka odluku".
-- ============================================================================


-- ============================================================================
-- VERIFIKACIJA POSLE POKRETANJA (read-only) -- ponoviti SS0 upit iznad.
-- 18 redova (GRUPA 1: 8, GRUPA 2: 6, GRUPA 3: 4) mora imati definiciju
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
-- SELECT _sec031_fix_fk('predmet_delegiranja',  'od_user_id',  'CASCADE');
-- SELECT _sec031_fix_fk('predmet_delegiranja',  'na_user_id',  'CASCADE');
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
-- SELECT _sec031_fix_fk('tos_acceptances',         'user_id', 'CASCADE');
-- COMMIT;
--
-- DROP FUNCTION IF EXISTS _sec031_fix_fk(regclass, text, text);
-- ============================================================================
