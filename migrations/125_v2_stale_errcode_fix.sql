-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 125: ISPRAVKA ERRCODE-a ZA USTAJALO OPAZANJE
--
-- ⚠ NIJE IZVRSENA. Pokrece je osnivac.
--
-- ─── STA SE DESILO ─────────────────────────────────────────────────────────
--
-- Migracija 124 (moja) je za oba stale guard-a koristila `ERRCODE = '40001'`.
-- Semanticki je delovalo tacno: 40001 JESTE `serialization_failure`, a ustajalo
-- opazanje JESTE konflikt serijalizacije.
--
-- Ali PostgREST klasu 40 tretira kao PROLAZNU gresku i ZAHTEV PONAVLJA. Nas
-- RAISE je determinististican -- ponavljanje uvek daje isti rezultat -- pa se
-- ciklus nikad ne razresi i klijent visi umesto da dobije odbijanje.
--
-- Izmereno u A016.8, kontrolisano poredjenje nad ISTOM funkcijom, gde se
-- razlikuje iskljucivo ERRCODE:
--
--     23503 (predmet ne postoji)  ->   0.32s   HTTP 409    cista greska
--     40001 (ustajalo opazanje)   ->  30.13s   TIMEOUT     bez odgovora
--     tacna verzija (uspeh)       ->   0.26s   HTTP 200
--
-- Podaci NISU bili ugrozeni: A016.8 T3 je izmerio da ustajalo opazanje nije
-- promenilo ni jednu kontradikciju, ni clanstvo, ni verziju. Guard je radio.
-- Neupotrebljiv je bio PRENOS odgovora, ne sama odbrana.
--
-- ─── ZASTO 55000, A NE NESTO DRUGO ─────────────────────────────────────────
--
-- `55000` = `object_not_in_prerequisite_state`. To je tacno ono sto se desilo:
-- predmet nije u stanju koje je odluka pretpostavila. Klasa 55 NIJE u skupu
-- koji PostgREST ponavlja (klasa 40 i 40P01), pa odgovor stize odmah.
--
-- Namerno NIJE `P0001` (podrazumevani `raise_exception`): njime bi ustajalo
-- opazanje postalo nerazlikovljivo od bilo kog drugog RAISE-a u lancu.
--
-- Namerno NIJE `55P03` (`lock_not_available`) -- to bi tvrdilo da lock nije
-- dobijen, a on JESTE dobijen; odbijena je odluka, ne zakljucavanje.
--
-- ─── OBIM ──────────────────────────────────────────────────────────────────
--
-- Menja se ISKLJUCIVO `ERRCODE` na dva mesta u `v2_persist_observation_package`.
-- Poruke, potpis, logika, redosled i sve ostalo ostaju identicni migraciji 124.
-- Migracije 119-123 se ne diraju.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.v2_persist_observation_package(
    p_predmet_id           UUID,
    p_user_id              UUID,
    p_event_id             TEXT,
    p_expected_version     INTEGER,
    p_observation_complete BOOLEAN,
    p_paket                JSONB
) RETURNS TABLE (
    out_version           INTEGER,
    out_indeks            INTEGER,
    out_issue_id          UUID,
    out_contradiction_id  UUID,
    out_created_issue     BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_tekuca    INTEGER;
    v_nova      INTEGER;
    v_stavka    JSONB;
    v_ref       TEXT;
    v_idx       INTEGER;
    v_issue_in  UUID;
    v_mapa      JSONB  := '{}'::jsonb;   -- '__nova__<i>' -> stvarni predmet_issues.id
    v_xmin_ocek TEXT;
    v_xmin_sad  TEXT;
    v_res       RECORD;
    v_opazene   UUID[] := ARRAY[]::UUID[];
    v_rezultat  JSONB  := '[]'::jsonb;
BEGIN
    IF p_predmet_id IS NULL THEN
        RAISE EXCEPTION 'v2_persist_observation_package: predmet_id je obavezan'
            USING ERRCODE = '23502';
    END IF;

    SELECT pr.observation_version INTO v_tekuca
      FROM public.predmeti pr
     WHERE pr.id = p_predmet_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'v2_persist_observation_package: predmet % ne postoji', p_predmet_id
            USING ERRCODE = '23503';
    END IF;

    -- ── STALE GUARD ────────────────────────────────────────────────────────
    -- 55000, ne 40001: vidi zaglavlje. 40001 je PostgREST ponavljao u krug.
    IF p_expected_version IS NOT NULL AND p_expected_version <> v_tekuca THEN
        RAISE EXCEPTION 'v2_persist_observation_package: ustajalo opazanje (video verziju %, tekuca je %)',
            p_expected_version, v_tekuca
            USING ERRCODE = '55000';
    END IF;

    v_nova := v_tekuca + 1;
    UPDATE public.predmeti SET observation_version = v_nova WHERE id = p_predmet_id;

    FOR v_stavka IN SELECT * FROM jsonb_array_elements(COALESCE(p_paket, '[]'::jsonb))
    LOOP
        v_idx       := COALESCE((v_stavka ->> 'indeks')::INTEGER, 0);
        v_ref       := NULLIF(v_stavka ->> 'issue_ref', '');
        v_xmin_ocek := NULLIF(v_stavka ->> 'expected_xmin', '');

        IF v_ref IS NULL THEN
            v_issue_in := NULL;
        ELSIF left(v_ref, 8) = '__nova__' THEN
            v_issue_in := NULLIF(v_mapa ->> v_ref, '')::UUID;
            IF v_issue_in IS NULL THEN
                RAISE EXCEPTION 'v2_persist_observation_package: stavka #% referise % koja u ovom paketu nije stvorena (napred-referenca ili preskocena stavka)',
                    v_idx, v_ref
                    USING ERRCODE = '23503';
            END IF;
        ELSE
            v_issue_in := v_ref::UUID;
        END IF;

        -- Revalidacija snapshot odluke. Isti razlog za 55000 kao gore.
        IF v_issue_in IS NOT NULL AND v_xmin_ocek IS NOT NULL THEN
            SELECT pi.xmin::text INTO v_xmin_sad
              FROM public.predmet_issues pi
             WHERE pi.id = v_issue_in;

            IF v_xmin_sad IS NULL OR v_xmin_sad <> v_xmin_ocek THEN
                RAISE EXCEPTION 'v2_persist_observation_package: sporna tacka % je promenjena od donosenja odluke (xmin % -> %)',
                    v_issue_in, v_xmin_ocek, COALESCE(v_xmin_sad, 'obrisan')
                    USING ERRCODE = '55000';
            END IF;
        END IF;

        SELECT * INTO v_res
          FROM public.v2_persist_contradiction(
                 p_predmet_id,
                 p_user_id,
                 v_issue_in,
                 v_stavka ->> 'label',
                 v_stavka ->> 'relation_type',
                 v_stavka ->> 'tezina',
                 v_stavka ->> 'fingerprint',
                 ARRAY(SELECT jsonb_array_elements_text(v_stavka -> 'dokaz_ids'))::UUID[],
                 ARRAY(SELECT jsonb_array_elements_text(v_stavka -> 'claim_identiteti'))::TEXT[]
               );

        v_mapa     := v_mapa || jsonb_build_object(
                          format('__nova__%s', v_idx), v_res.out_issue_id);
        v_opazene  := v_opazene || v_res.out_contradiction_id;
        v_rezultat := v_rezultat || jsonb_build_object(
            'indeks',           v_idx,
            'issue_id',         v_res.out_issue_id,
            'contradiction_id', v_res.out_contradiction_id,
            'created_issue',    v_res.out_created_issue);
    END LOOP;

    IF p_observation_complete IS TRUE THEN
        UPDATE public.predmet_contradictions pc
           SET state = 'NOT_OBSERVED',
               state_reason = format('nije opazena u kompletnom opazanju v%s', v_nova),
               updated_at = now()
          FROM public.predmet_issues pi
         WHERE pc.issue_id = pi.id
           AND pi.predmet_id = p_predmet_id
           AND pc.state = 'OPEN'
           AND NOT (pc.id = ANY (v_opazene));
    END IF;

    RETURN QUERY
    SELECT v_nova,
           (x ->> 'indeks')::INTEGER,
           (x ->> 'issue_id')::UUID,
           (x ->> 'contradiction_id')::UUID,
           (x ->> 'created_issue')::BOOLEAN
      FROM jsonb_array_elements(v_rezultat) AS x;
END;
$$;

REVOKE ALL ON FUNCTION public.v2_persist_observation_package FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.v2_persist_observation_package TO service_role;

COMMENT ON FUNCTION public.v2_persist_observation_package IS
  'A016.7/A016.8 -- JEDNO opazanje = JEDNA transakcija. Ustajalo opazanje se odbija sa ERRCODE 55000 (object_not_in_prerequisite_state); 40001 je izmereno kao neupotrebljivo jer ga PostgREST ponavlja u krug (A016.8: 30s timeout naspram 0.32s za 23503).';
