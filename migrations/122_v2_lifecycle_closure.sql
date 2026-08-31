-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 122: V2 CONTRADICTION LIFECYCLE (PREDLOG, v2)
--
-- ⚠⚠ NIJE IZVRSENA. Pokrece je osnivac. A016.2B §9/§14: predlog -> STOP.
--
-- ─── ZASTO v2 ──────────────────────────────────────────────────────────────
-- Prva verzija ovog fajla (A016.2A) je imala TRI rupe koje je A016.2B nasao
-- pokusavajuci da je obori. Sve tri su ovde zatvorene, i svaka je zatvorena
-- OBRASCEM KOJI REPO VEC KORISTI, ne novim izumom:
--
--   (1) TRKA ZATVARANJE/PONOVNO-OPAZANJE.  Run A („nije opazena") i run B
--       („opazena") su oba atomicna, ali je ishod zavisio od redosleda:
--           B otvori, pa A zatvori  ->  NOT_OBSERVED, iako je B video spor.
--       Zatvoreno optimistickom konkurentnoscu nad `updated_at` -- isti obrazac
--       koji `services/case_evolution.py::_consequence_refresh_case_actions`
--       vec koristi za CLOSE granu (`.eq("updated_at", snapshot)`).
--
--   (2) BAZA PRIHVATA STANJE KOJE DOMEN ZABRANJUJE.  Izmereno uzivo u A016.2B,
--       direktnim upisom mimo adaptera:
--           kontradikcija sa 0 clanova   -> PRIHVACENA
--           kontradikcija sa 1 clanom    -> PRIHVACENA
--           tvrdnja iz DRUGOG predmeta   -> PRIHVACENA
--       §8 trazi da SQL bude poslednja linija odbrane. Zatvoreno odlozenim
--       constraint trigerom -- isti obrazac koji `migrations/115_events_orphan_guard.sql`
--       vec koristi.
--
--   (3) OPEN SA NULA CLANOVA.  A016.2A je izmerio da takva kontradikcija ostaje
--       OPEN i da projekcija emituje akciju sa praznom listom tvrdnji. DEO 3
--       to cini nemogucim: povlacenje svih clanova mora biti praceno promenom
--       stanja, u istoj transakciji.
--
-- ⚠ DEO 3 MENJA POSTOJECE PONASANJE: `OPEN` sa manje od 2 aktivna clana postaje
--   nedozvoljeno. To je namerno i to je odluka koju osnivac prihvata zajedno sa
--   migracijom. Postojecih redova: 0 (`predmet_contradictions` je prazan), pa
--   migracija ne moze oboriti nijedan postojeci podatak.
--
-- Migracije 119/120/121 se NE diraju. Potpis `v2_persist_contradiction` ostaje
-- identican (zato `CREATE OR REPLACE`, bez `DROP`).
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
-- DEO 1: PONOVNO OTVARANJE — identitet se ne menja
--
-- A016.2A je uzivo oborio H6: posle zatvaranja, ponovno opazanje istog spora
-- pravilo je NOV `contradiction_id` (fb0020b6 -> 6ffeea29), jer lookup trazi
-- samo `state='OPEN'`, a parcijalni UNIQUE indeks pokriva samo `OPEN` redove.
-- ───────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.v2_persist_contradiction(
    p_predmet_id       UUID,
    p_user_id          UUID,
    p_issue_id         UUID,
    p_label            TEXT,
    p_relation_type    TEXT,
    p_tezina           TEXT,
    p_fingerprint      TEXT,
    p_dokaz_ids        UUID[],
    p_claim_identiteti TEXT[]
) RETURNS TABLE (out_issue_id UUID, out_contradiction_id UUID, out_created_issue BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_issue    UUID;
    v_kontr    UUID;
    v_created  BOOLEAN := FALSE;
    v_distinct UUID[];
    v_tudjih   INT;
    v_staro    TEXT;
    i          INT;
BEGIN
    SELECT ARRAY(SELECT DISTINCT u FROM unnest(COALESCE(p_dokaz_ids, ARRAY[]::UUID[])) AS u)
      INTO v_distinct;
    IF COALESCE(array_length(v_distinct, 1), 0) < 2 THEN
        RAISE EXCEPTION 'v2_persist_contradiction: najmanje 2 razlicite tvrdnje su obavezne (dobijeno %)',
            COALESCE(array_length(v_distinct, 1), 0) USING ERRCODE = '22023';
    END IF;

    SELECT count(*) INTO v_tudjih
      FROM unnest(v_distinct) AS x(did)
     WHERE NOT EXISTS (SELECT 1 FROM public.predmet_dokazi pd
                        WHERE pd.id = x.did AND pd.predmet_id = p_predmet_id
                          AND pd.deleted_at IS NULL);
    IF v_tudjih > 0 THEN
        RAISE EXCEPTION 'v2_persist_contradiction: % tvrdnja ne pripada predmetu % ili je obrisana',
            v_tudjih, p_predmet_id USING ERRCODE = '23503';
    END IF;

    IF p_issue_id IS NULL THEN
        INSERT INTO public.predmet_issues AS pi
            (predmet_id, user_id, label, status, initial_claim_fingerprint)
        VALUES (p_predmet_id, p_user_id, p_label, 'DISCOVERED', p_fingerprint)
        ON CONFLICT (predmet_id, initial_claim_fingerprint)
            WHERE initial_claim_fingerprint IS NOT NULL AND status <> 'MERGED'
        DO NOTHING
        RETURNING pi.id INTO v_issue;
        IF v_issue IS NULL THEN
            SELECT pi2.id INTO v_issue FROM public.predmet_issues pi2
             WHERE pi2.predmet_id = p_predmet_id
               AND pi2.initial_claim_fingerprint = p_fingerprint
               AND pi2.status <> 'MERGED' LIMIT 1;
        ELSE
            v_created := TRUE;
            IF p_label IS NOT NULL THEN
                INSERT INTO public.predmet_issue_labels (issue_id, label, izvor)
                VALUES (v_issue, p_label, 'producer');
            END IF;
        END IF;
    ELSE
        SELECT pi3.id INTO v_issue FROM public.predmet_issues pi3
         WHERE pi3.id = p_issue_id AND pi3.predmet_id = p_predmet_id;
        IF v_issue IS NULL THEN
            RAISE EXCEPTION 'v2_persist_contradiction: sporna tacka % ne pripada predmetu %',
                p_issue_id, p_predmet_id USING ERRCODE = '23503';
        END IF;
    END IF;

    -- Zakljucaj red sporne tacke za ostatak transakcije. Time trka
    -- zatvaranje/ponovno-opazanje nad ISTOM spornom tackom postaje serijalizovana
    -- na nivou baze, a ne na nivou redosleda klijentskih poziva.
    PERFORM 1 FROM public.predmet_issues WHERE id = v_issue FOR UPDATE;

    SELECT pc.id INTO v_kontr
      FROM public.predmet_contradictions pc
     WHERE pc.issue_id = v_issue AND pc.relation_type = p_relation_type AND pc.state = 'OPEN'
     LIMIT 1;

    -- ═══ PONOVNO OTVARANJE PRE KREIRANJA ═══════════════════════════════════
    -- `NOT_OBSERVED` je SISTEMSKA tvrdnja („nismo je videli u kompletnom
    -- opazanju"); njeno povlacenje je bezbedno i deterministicko.
    -- `RESOLVED` je DOMENSKA/ljudska odluka; tiho vracanje u `OPEN` bi je
    -- pregazilo, pa takav red ide u `REVIEW_REQUIRED` NA ISTOM REDU --
    -- identitet ostaje stabilan, a odluku donosi covek. To je H5 u SQL-u.
    IF v_kontr IS NULL THEN
        SELECT pcr.id, pcr.state INTO v_kontr, v_staro
          FROM public.predmet_contradictions pcr
         WHERE pcr.issue_id = v_issue AND pcr.relation_type = p_relation_type
           AND pcr.state IN ('NOT_OBSERVED', 'REVIEW_REQUIRED', 'RESOLVED')
         ORDER BY pcr.updated_at DESC
         LIMIT 1;

        IF v_kontr IS NOT NULL THEN
            UPDATE public.predmet_contradictions pcu
               SET state = CASE WHEN v_staro = 'RESOLVED' THEN 'REVIEW_REQUIRED' ELSE 'OPEN' END,
                   state_reason = CASE WHEN v_staro = 'RESOLVED'
                                       THEN 'ponovo opazena posle RESOLVED — trazi ljudsku potvrdu'
                                       ELSE NULL END,
                   tezina = COALESCE(p_tezina, pcu.tezina),
                   updated_at = now()
             WHERE pcu.id = v_kontr;
        END IF;
    END IF;

    IF v_kontr IS NULL THEN
        INSERT INTO public.predmet_contradictions AS pcx
            (issue_id, relation_type, state, tezina)
        VALUES (v_issue, p_relation_type, 'OPEN', p_tezina)
        ON CONFLICT (issue_id, relation_type) WHERE state = 'OPEN' DO NOTHING
        RETURNING pcx.id INTO v_kontr;
        IF v_kontr IS NULL THEN
            SELECT pc2.id INTO v_kontr FROM public.predmet_contradictions pc2
             WHERE pc2.issue_id = v_issue AND pc2.relation_type = p_relation_type
               AND pc2.state = 'OPEN' LIMIT 1;
        END IF;
    ELSE
        UPDATE public.predmet_contradictions pc3
           SET tezina = COALESCE(p_tezina, pc3.tezina), updated_at = now()
         WHERE pc3.id = v_kontr;
    END IF;

    UPDATE public.predmet_contradiction_claims pcc
       SET removed_at = now(), removed_reason = 'NOT_OBSERVED'
     WHERE pcc.contradiction_id = v_kontr
       AND pcc.removed_at IS NULL
       AND pcc.dokaz_id <> ALL (v_distinct);

    FOR i IN 1 .. array_length(v_distinct, 1) LOOP
        INSERT INTO public.predmet_contradiction_claims
            (contradiction_id, dokaz_id, claim_identitet)
        VALUES (v_kontr, v_distinct[i],
                (SELECT p_claim_identiteti[k] FROM generate_subscripts(p_dokaz_ids, 1) AS k
                  WHERE p_claim_identiteti IS NOT NULL AND p_dokaz_ids[k] = v_distinct[i]
                  LIMIT 1))
        ON CONFLICT (contradiction_id, dokaz_id) WHERE removed_at IS NULL
        DO NOTHING;
    END LOOP;

    RETURN QUERY SELECT v_issue, v_kontr, v_created;
END;
$$;


-- ───────────────────────────────────────────────────────────────────────────
-- DEO 2: ZATVARANJE — samo posle KOMPLETNOG opazanja, i samo ako niko
--        svezije nije dodirnuo red
-- ───────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.v2_close_unobserved(
    p_predmet_id           UUID,
    p_observed_ids         UUID[],
    p_observation_complete BOOLEAN,
    p_observed_since       TIMESTAMPTZ,
    p_reason               TEXT DEFAULT 'nije opazena u kompletnom osvezavanju'
) RETURNS TABLE (out_closed_id UUID)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Kompletnost je tvrdnja pozivaoca; baza je ne moze proveriti, ali MOZE
    -- odbiti poziv koji je ne tvrdi. Time „zatvaranje posle nepotpunog
    -- opazanja" prestaje da bude greska u aplikaciji i postaje strukturno
    -- nemoguce na granici upisa (A012: baza sama ne stiti nista osim trke).
    IF p_observation_complete IS NOT TRUE THEN
        RAISE EXCEPTION 'v2_close_unobserved: zatvaranje je dozvoljeno SAMO posle kompletnog opazanja'
            USING ERRCODE = '22023';
    END IF;
    IF p_predmet_id IS NULL THEN
        RAISE EXCEPTION 'v2_close_unobserved: predmet_id je obavezan' USING ERRCODE = '23502';
    END IF;
    -- Bez vremena pocetka opazanja nema nacina da se razlikuje ustajali od
    -- svezeg pogleda -- a to je bila rupa (1) prve verzije.
    IF p_observed_since IS NULL THEN
        RAISE EXCEPTION 'v2_close_unobserved: p_observed_since je obavezan (optimisticka konkurentnost)'
            USING ERRCODE = '23502';
    END IF;

    RETURN QUERY
    UPDATE public.predmet_contradictions pc
       SET state = 'NOT_OBSERVED',
           state_reason = p_reason,
           updated_at = now()
      FROM public.predmet_issues pi
     WHERE pc.issue_id = pi.id
       AND pi.predmet_id = p_predmet_id            -- opseg predmeta, u SQL-u
       AND pc.state = 'OPEN'                        -- idempotentno
       AND pc.updated_at < p_observed_since         -- ustajali pogled ne gazi svezi
       AND NOT (pc.id = ANY (COALESCE(p_observed_ids, ARRAY[]::UUID[])))
    RETURNING pc.id;
END;
$$;

REVOKE ALL ON FUNCTION public.v2_close_unobserved FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.v2_close_unobserved TO service_role;

COMMENT ON FUNCTION public.v2_close_unobserved IS
  'A016.2B -- zatvara OPEN kontradikcije predmeta kojih NEMA u skupu opazenih. Iskljucivo NOT_OBSERVED, nikad RESOLVED (A006 par.9). Odbija poziv bez tvrdnje o kompletnosti i bez vremena pocetka opazanja; `updated_at < p_observed_since` sprecava da ustajalo opazanje pregazi svezije.';


-- ───────────────────────────────────────────────────────────────────────────
-- DEO 3: BAZA KAO POSLEDNJA LINIJA ODBRANE
--
-- Izmereno uzivo (A016.2B, direktan upis mimo adaptera): baza danas prihvata
-- kontradikciju sa 0 clanova, sa 1 clanom, i sa tvrdnjom iz DRUGOG predmeta.
-- Guard mora biti ODLOZEN: unutar jedne transakcije RPC prvo kreira
-- kontradikciju (0 clanova), pa tek onda upisuje clanstvo. Provera zato mora
-- da se izvrsi na COMMIT-u, ne po redu.
--
-- Isti obrazac koji `migrations/115_events_orphan_guard.sql` vec koristi.
-- ───────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.v2_kontradikcija_invarijanta()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_kontr   UUID;
    v_stanje  TEXT;
    v_predmet UUID;
    v_aktivnih INT;
    v_tudjih   INT;
BEGIN
    v_kontr := COALESCE(NEW.contradiction_id, OLD.contradiction_id, NEW.id, OLD.id);
    IF v_kontr IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT pc.state, pi.predmet_id INTO v_stanje, v_predmet
      FROM public.predmet_contradictions pc
      JOIN public.predmet_issues pi ON pi.id = pc.issue_id
     WHERE pc.id = v_kontr;

    -- Red je u medjuvremenu obrisan (npr. CASCADE) -- nema sta da se proverava.
    IF v_stanje IS NULL THEN
        RETURN NULL;
    END IF;

    -- Invarijanta vazi SAMO za otvorenu kontradikciju. Zatvorena sme imati
    -- nula aktivnih clanova -- to je upravo ono sto zatvaranje i znaci.
    IF v_stanje <> 'OPEN' THEN
        RETURN NULL;
    END IF;

    SELECT count(DISTINCT pcc.dokaz_id) INTO v_aktivnih
      FROM public.predmet_contradiction_claims pcc
     WHERE pcc.contradiction_id = v_kontr AND pcc.removed_at IS NULL;

    IF v_aktivnih < 2 THEN
        RAISE EXCEPTION 'kontradikcija % je OPEN sa % aktivnih tvrdnji (minimum je 2)',
            v_kontr, v_aktivnih USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO v_tudjih
      FROM public.predmet_contradiction_claims pcc
      JOIN public.predmet_dokazi pd ON pd.id = pcc.dokaz_id
     WHERE pcc.contradiction_id = v_kontr AND pcc.removed_at IS NULL
       AND (pd.predmet_id <> v_predmet OR pd.deleted_at IS NOT NULL);

    IF v_tudjih > 0 THEN
        RAISE EXCEPTION 'kontradikcija % ima % tvrdnji van predmeta % ili obrisanih',
            v_kontr, v_tudjih, v_predmet USING ERRCODE = '23503';
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_v2_kontradikcija_invarijanta ON public.predmet_contradictions;
CREATE CONSTRAINT TRIGGER trg_v2_kontradikcija_invarijanta
    AFTER INSERT OR UPDATE ON public.predmet_contradictions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.v2_kontradikcija_invarijanta();

DROP TRIGGER IF EXISTS trg_v2_clanstvo_invarijanta ON public.predmet_contradiction_claims;
CREATE CONSTRAINT TRIGGER trg_v2_clanstvo_invarijanta
    AFTER INSERT OR UPDATE OR DELETE ON public.predmet_contradiction_claims
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.v2_kontradikcija_invarijanta();


-- ═══════════════════════════════════════════════════════════════════════════
-- STA OVAJ PREDLOG I DALJE NE POKRIVA
--
-- 1. `SUPERSEDED` i `MERGED` nemaju pisca.
-- 2. Kompletnost opazanja ostaje tvrdnja pozivaoca (baza je ne moze proveriti,
--    samo odbija poziv koji je ne tvrdi).
-- 3. `RESOLVED` i dalje nema pisca -- nijedan kodni put ga ne postavlja. Ovaj
--    predlog ga samo POSTUJE ako postoji.
-- 4. Trka izmedju dva opazanja je serijalizovana `FOR UPDATE`-om nad spornom
--    tackom I `updated_at` guardom, ali to NIJE izmereno -- migracija nije
--    izvrsena. Do merenja: NEPROVERENO.
--
-- ROLLBACK:
--   DROP TRIGGER IF EXISTS trg_v2_clanstvo_invarijanta ON public.predmet_contradiction_claims;
--   DROP TRIGGER IF EXISTS trg_v2_kontradikcija_invarijanta ON public.predmet_contradictions;
--   DROP FUNCTION IF EXISTS public.v2_kontradikcija_invarijanta();
--   DROP FUNCTION IF EXISTS public.v2_close_unobserved(UUID,UUID[],BOOLEAN,TIMESTAMPTZ,TEXT);
--   CREATE OR REPLACE v2_persist_contradiction telom iz migracije 121.
-- Tabele, indeksi i redovi se ne diraju ni u jednom smeru.
-- ═══════════════════════════════════════════════════════════════════════════
