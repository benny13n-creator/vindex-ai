-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 121: popravka `v2_persist_contradiction`
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run
--
-- ⚠ NIJE IZVRSENA. Napisana u V2 PERSISTENCE SPRINT 001; pokrece je osnivac.
--
-- ─── STA JE PUKLO ──────────────────────────────────────────────────────────
-- Migracija 120 je izvrsena i funkcija POSTOJI, ali prvi poziv sa validnim
-- podacima pada:
--
--     42702  column reference "issue_id" is ambiguous
--            It could refer to either a PL/pgSQL variable or a table column.
--
-- UZROK: `RETURNS TABLE (issue_id UUID, contradiction_id UUID, ...)` u plpgsql
-- uvodi promenljive tacno tih imena. Svako kasnije `WHERE issue_id = ...` ili
-- `ON CONFLICT (issue_id, ...)` postaje dvosmisleno jer isto ime nosi i kolona
-- (`predmet_contradictions.issue_id`, `predmet_contradiction_claims.contradiction_id`).
--
-- Ovo je defekt u SQL-u koji je napisan u A010, ne arhitektonski problem:
-- domen, semа i granice identiteta ostaju nepromenjeni.
--
-- ─── POPRAVKA — TRI STVARI, SVE TRI NADJENE MERENJEM ───────────────────────
--
-- (1) AMBIGUITY. Izlazne promenljive se preimenuju u `out_*`, i SVAKA referenca
--     na kolonu dobija alias (`pi/pi2/pi3/pc/pc2/pc3/pcx/pcc`). `DROP` pre
--     `CREATE` je obavezan: Postgres ne dozvoljava da `CREATE OR REPLACE`
--     promeni IMENA izlaznih parametara. Potpis argumenata je nepromenjen.
--
-- (2) PRAZAN NIZ JE PROLAZIO PORED GUARD-a  ← nadjeno uzivo u A011.
--     `array_length(ARRAY[]::uuid[], 1)` vraca NULL, ne 0, pa je
--     `array_length(...) < 2` za prazan niz NULL (ne-tacan) i guard NE opali.
--     Posle popravke (1) to bi proizvelo spornu tacku BEZ IJEDNOG CLANA.
--     Sada se broje RAZLICITE vrednosti, uz `COALESCE(..., 0)`.
--
-- (3) NEMA PROVERE VLASNISTVA NAD TVRDNJAMA  ← nadjeno citanjem 119/120.
--     FK `dokaz_id -> predmet_dokazi(id)` proverava samo POSTOJANJE. Bez nove
--     provere, kontradikcija je mogla da uzme tvrdnju iz TUDJEG predmeta i
--     izolacija bi zavisila iskljucivo od Python sloja. A011 §9 trazi da bude
--     dokazana i SQL-om.
--
-- Atomicnost, `ON CONFLICT` strategija, `NOT_OBSERVED` pri izostanku clana i
-- provera opsega predmeta pri kontinuitetu ostaju kao u migraciji 120.
-- ═══════════════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS public.v2_persist_contradiction(
    UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, UUID[], TEXT[]);

CREATE FUNCTION public.v2_persist_contradiction(
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
    i          INT;
BEGIN
    -- ── GUARD 1: najmanje DVE RAZLICITE tvrdnje ─────────────────────────────
    -- `array_length(ARRAY[]::uuid[], 1)` vraca NULL, ne 0, pa je uslov
    -- `array_length(...) < 2` za prazan niz NULL (dakle NE-tacan) i guard NE bi
    -- opalio. Izmereno uzivo u A011: prazan niz je prosao pored provere.
    -- Bez `COALESCE` bi posle popravke ambiguity greske nastala sporna tacka
    -- BEZ IJEDNOG CLANA -- tacno stanje koje domen zabranjuje.
    --
    -- Broje se RAZLICITE vrednosti: dva puta ista tvrdnja nisu dva clana
    -- (isti kriterijum koji `shared/issue_v2.py` vec sprovodi nad `frozenset`).
    SELECT ARRAY(SELECT DISTINCT u FROM unnest(COALESCE(p_dokaz_ids, ARRAY[]::UUID[])) AS u)
      INTO v_distinct;

    IF COALESCE(array_length(v_distinct, 1), 0) < 2 THEN
        RAISE EXCEPTION 'v2_persist_contradiction: najmanje 2 razlicite tvrdnje su obavezne (dobijeno %)',
            COALESCE(array_length(v_distinct, 1), 0)
            USING ERRCODE = '22023';
    END IF;

    -- ── GUARD 2: sve tvrdnje moraju pripadati OVOM predmetu ─────────────────
    -- FK `dokaz_id -> predmet_dokazi(id)` proverava samo POSTOJANJE, ne i
    -- vlasnistvo. Bez ove provere kontradikcija bi mogla da uzme tvrdnju iz
    -- TUDJEG predmeta -- izolacija bi zavisila iskljucivo od aplikacije, a
    -- A011 §9 trazi da bude dokazana i SQL-om.
    -- Soft-obrisana tvrdnja (`deleted_at`) takodje nije validan clan.
    SELECT count(*) INTO v_tudjih
      FROM unnest(v_distinct) AS x(did)
     WHERE NOT EXISTS (
           SELECT 1 FROM public.predmet_dokazi pd
            WHERE pd.id = x.did
              AND pd.predmet_id = p_predmet_id
              AND pd.deleted_at IS NULL);

    IF v_tudjih > 0 THEN
        RAISE EXCEPTION 'v2_persist_contradiction: % tvrdnja ne pripada predmetu % ili je obrisana',
            v_tudjih, p_predmet_id
            USING ERRCODE = '23503';
    END IF;

    IF p_issue_id IS NULL THEN
        -- KREIRANJE. `ON CONFLICT` nad parcijalnim UNIQUE indeksom je tacka na
        -- kojoj se trka gubi bez izuzetka: drugi proces ne dobija gresku nego
        -- POSTOJECU spornu tacku.
        INSERT INTO public.predmet_issues AS pi
            (predmet_id, user_id, label, status, initial_claim_fingerprint)
        VALUES (p_predmet_id, p_user_id, p_label, 'DISCOVERED', p_fingerprint)
        ON CONFLICT (predmet_id, initial_claim_fingerprint)
            WHERE initial_claim_fingerprint IS NOT NULL AND status <> 'MERGED'
        DO NOTHING
        RETURNING pi.id INTO v_issue;

        IF v_issue IS NULL THEN
            SELECT pi2.id INTO v_issue
              FROM public.predmet_issues pi2
             WHERE pi2.predmet_id = p_predmet_id
               AND pi2.initial_claim_fingerprint = p_fingerprint
               AND pi2.status <> 'MERGED'
             LIMIT 1;
        ELSE
            v_created := TRUE;
            IF p_label IS NOT NULL THEN
                INSERT INTO public.predmet_issue_labels (issue_id, label, izvor)
                VALUES (v_issue, p_label, 'producer');
            END IF;
        END IF;
    ELSE
        SELECT pi3.id INTO v_issue
          FROM public.predmet_issues pi3
         WHERE pi3.id = p_issue_id AND pi3.predmet_id = p_predmet_id;   -- opseg predmeta
        IF v_issue IS NULL THEN
            RAISE EXCEPTION 'v2_persist_contradiction: sporna tacka % ne pripada predmetu %',
                p_issue_id, p_predmet_id USING ERRCODE = '23503';
        END IF;
    END IF;

    -- Kontradikcija: najvise jedna OTVORENA po (sporna tacka, tip relacije).
    SELECT pc.id INTO v_kontr
      FROM public.predmet_contradictions pc
     WHERE pc.issue_id = v_issue AND pc.relation_type = p_relation_type AND pc.state = 'OPEN'
     LIMIT 1;

    IF v_kontr IS NULL THEN
        INSERT INTO public.predmet_contradictions AS pcx
            (issue_id, relation_type, state, tezina)
        VALUES (v_issue, p_relation_type, 'OPEN', p_tezina)
        ON CONFLICT (issue_id, relation_type) WHERE state = 'OPEN' DO NOTHING
        RETURNING pcx.id INTO v_kontr;

        IF v_kontr IS NULL THEN
            SELECT pc2.id INTO v_kontr
              FROM public.predmet_contradictions pc2
             WHERE pc2.issue_id = v_issue AND pc2.relation_type = p_relation_type
               AND pc2.state = 'OPEN'
             LIMIT 1;
        END IF;
    ELSE
        UPDATE public.predmet_contradictions pc3
           SET tezina = COALESCE(p_tezina, pc3.tezina), updated_at = now()
         WHERE pc3.id = v_kontr;
    END IF;

    -- CLANSTVO. Tvrdnja koja vise nije u dolazecem skupu dobija `removed_at`
    -- i razlog `NOT_OBSERVED` -- NIKAD `RESOLVED` i NIKAD DELETE.
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

COMMENT ON FUNCTION public.v2_persist_contradiction IS
  'A010/V2 -- ATOMICAN upis jedne V2 kontradikcije (sporna tacka + kontradikcija + clanstvo) u JEDNOJ transakciji. NE donosi odluku o identitetu: odluku donosi shared/issue_v2.py i prosledjuje je kroz p_issue_id. Trka pri kreiranju se gubi bez izuzetka -- ON CONFLICT vraca POSTOJECU spornu tacku. Migracija 121 preimenovala izlazne parametre u out_* zbog 42702 kolizije sa imenima kolona.';

REVOKE ALL ON FUNCTION public.v2_persist_contradiction FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.v2_persist_contradiction TO service_role;

-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK: vratiti verziju iz migracije 120 (koja je dokazano neispravna),
-- ili jednostavno
--   DROP FUNCTION IF EXISTS public.v2_persist_contradiction(UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,UUID[],TEXT[]);
-- Tabele, indeksi i podaci se NE diraju -- 121 menja iskljucivo telo funkcije.
-- ═══════════════════════════════════════════════════════════════════════════
