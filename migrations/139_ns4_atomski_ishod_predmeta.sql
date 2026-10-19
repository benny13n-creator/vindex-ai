-- ============================================================================
-- Vindex AI — Migracija 139: ishod predmeta i `case_patterns` u JEDNOJ transakciji (NS4 G1/G2)
-- ============================================================================
-- PROBLEM (NS4R §5, strogi xfail G1/G2):
--   `routers/learning.zabeleži_ishod` je upisivao `outcome_log` jednim PostgREST pozivom, a zatim
--   `_preracunaj_obrasce` čitao → računao → pisao `case_patterns` u više ZASEBNIH poziva, bez transakcije:
--     G1  zastareo preračun (pročitan pre tuđeg upisa, upisan posle tuđeg preračuna) prepisuje tačan zbir;
--     G2  postojeći faktori su čitani bez straničenja — iznad PostgREST max-rows preračun puca usred petlje;
--     +   pad procesa između upisa ishoda i preračuna ostavlja zbir zastarelim do sledećeg upisa te vrste.
--
-- REŠENJE: jedna funkcija, jedna transakcija (PostgREST RPC = jedna transakcija):
--   1. `pg_advisory_xact_lock` po KORISNIKU — svi upisi ishoda jednog korisnika su linearizovani
--      (jedna brava → bez zastoja; različiti korisnici ne dele redove `case_patterns`);
--   2. vlasništvo predmeta i vrsta spora se čitaju U transakciji, posle brave (ne veruje se pozivaocu);
--   3. upsert `outcome_log` (isti `on_conflict = predmet_id` kao ranije);
--   4. `case_patterns` za novu i (ako se promenila) staru vrstu spora preračunava se SKUPOVNO iz
--      `outcome_log` — bez ograničenja broja redova; faktor bez ishoda ostaje sa nulama (red se ne briše).
--   Greška bilo gde → rollback CELE transakcije: ishod i zbir su uvek usklađeni ili oba nepromenjena.
--
-- Semantika faktora je ista kao u Python verziji (`dict.fromkeys(faktori[:10])`): prvih 10 elemenata,
-- ponovljeni faktor u jednom ishodu se broji jednom; NULL element se preskače.
--
-- BEZBEDNOST:
--   SECURITY INVOKER (poziva ga backend kao `service_role`, koji već zaobilazi RLS) — nema eskalacije.
--   EXECUTE oduzet od PUBLIC/anon/authenticated: korisnik sa JWT-om ne može da je pozove sa tuđim `user_id`.
--   `search_path` fiksiran na `pg_catalog, public`; svi objekti kvalifikovani šemom.
--   Direktan upis u `outcome_log`/`case_patterns` preko Data API-ja se oduzima (frontend ih ne koristi —
--   NS4 izveštaj §G1); time zbir ne može da se razilazi od ishoda ni zaobilaženjem funkcije. SELECT ostaje.
--
-- Zaključavanje: CREATE FUNCTION/REVOKE — kratke brave, bez prepisivanja podataka. Idempotentno.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.zabelezi_ishod_predmeta(
    p_user_id          uuid,
    p_predmet_id       uuid,
    p_ishod            text,
    p_faktori          text[],
    p_trajanje_meseci  integer,
    p_vrednost_spora   numeric,
    p_komentar         text,
    p_uzroci           text[],
    p_kontekst_poraza  text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_tip        text;
    v_stari_tip  text;
    v_stari_uid  uuid;
    v_vrsta      text;
    v_faktora    integer := 0;
BEGIN
    IF p_user_id IS NULL OR p_predmet_id IS NULL THEN
        RAISE EXCEPTION 'nedostaje identitet korisnika ili predmeta' USING ERRCODE = '22023';
    END IF;

    -- (1) Linearizacija svih upisa ishoda jednog korisnika (oslobađa se na kraju transakcije).
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('vindex.ishod_predmeta'),
                                             pg_catalog.hashtext(p_user_id::text));

    -- (2) Vlasništvo i vrsta spora — u transakciji, posle brave.
    SELECT p.tip INTO v_tip
      FROM public.predmeti p
     WHERE p.id = p_predmet_id AND p.user_id = p_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'predmet nije pronađen' USING ERRCODE = 'P0002';
    END IF;

    SELECT o.tip_spora, o.user_id INTO v_stari_tip, v_stari_uid
      FROM public.outcome_log o
     WHERE o.predmet_id = p_predmet_id
     FOR UPDATE;
    IF FOUND AND v_stari_uid IS DISTINCT FROM p_user_id THEN
        -- Ishod predmeta pripada drugom korisniku: prepisivanje bi ostavilo njegov zbir zastarelim.
        RAISE EXCEPTION 'ishod predmeta pripada drugom korisniku' USING ERRCODE = '42501';
    END IF;

    -- (3) Ishod (isti ključ kao ranije: predmet_id UNIQUE).
    INSERT INTO public.outcome_log AS o
        (predmet_id, user_id, ishod, presudni_faktori, trajanje_meseci, vrednost_spora_rsd,
         komentar, tip_spora, uzroci, kontekst_poraza)
    VALUES
        (p_predmet_id, p_user_id, p_ishod, COALESCE(p_faktori, '{}'), p_trajanje_meseci, p_vrednost_spora,
         p_komentar, v_tip, COALESCE(p_uzroci, '{}'), p_kontekst_poraza)
    ON CONFLICT (predmet_id) DO UPDATE SET
        ishod              = EXCLUDED.ishod,
        presudni_faktori   = EXCLUDED.presudni_faktori,
        trajanje_meseci    = EXCLUDED.trajanje_meseci,
        vrednost_spora_rsd = EXCLUDED.vrednost_spora_rsd,
        komentar           = EXCLUDED.komentar,
        tip_spora          = EXCLUDED.tip_spora,
        uzroci             = EXCLUDED.uzroci,
        kontekst_poraza    = EXCLUDED.kontekst_poraza,
        updated_at         = pg_catalog.now();

    -- (4) Zbir za novu i (ako se razlikuje) staru vrstu spora, u stalnom redosledu.
    FOR v_vrsta IN
        SELECT DISTINCT x FROM unnest(ARRAY[v_tip, v_stari_tip]) AS x
         WHERE x IS NOT NULL AND x <> ''
         ORDER BY x
    LOOP
        UPDATE public.case_patterns c
           SET pobede = 0, porazi = 0, ukupno = 0, updated_at = pg_catalog.now()
         WHERE c.user_id = p_user_id AND c.tip_spora = v_vrsta;

        INSERT INTO public.case_patterns AS c (user_id, tip_spora, faktor, pobede, porazi, ukupno, updated_at)
        SELECT p_user_id, v_vrsta, f.faktor,
               count(*) FILTER (WHERE f.ishod = 'pobeda'),
               count(*) FILTER (WHERE f.ishod = 'poraz'),
               count(*),
               pg_catalog.now()
          FROM (
                SELECT DISTINCT o.predmet_id, o.ishod, e.faktor
                  FROM public.outcome_log o
                  CROSS JOIN LATERAL unnest(COALESCE(o.presudni_faktori, '{}')) WITH ORDINALITY AS e(faktor, n)
                 WHERE o.user_id = p_user_id AND o.tip_spora = v_vrsta
                   AND e.n <= 10 AND e.faktor IS NOT NULL
               ) f
         GROUP BY f.faktor
        ON CONFLICT (user_id, tip_spora, faktor) DO UPDATE SET
            pobede = EXCLUDED.pobede, porazi = EXCLUDED.porazi, ukupno = EXCLUDED.ukupno,
            updated_at = EXCLUDED.updated_at;
    END LOOP;

    SELECT count(DISTINCT e.faktor) INTO v_faktora
      FROM unnest(COALESCE(p_faktori, '{}')) WITH ORDINALITY AS e(faktor, n)
     WHERE e.n <= 10 AND e.faktor IS NOT NULL;

    RETURN jsonb_build_object('tip_spora', v_tip, 'prethodna_vrsta', v_stari_tip, 'faktora', v_faktora);
END;
$$;

REVOKE ALL ON FUNCTION public.zabelezi_ishod_predmeta(uuid, uuid, text, text[], integer, numeric, text, text[], text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.zabelezi_ishod_predmeta(uuid, uuid, text, text[], integer, numeric, text, text[], text)
    TO service_role;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.outcome_log, public.case_patterns FROM anon, authenticated;

COMMIT;

-- ─── Provera posle primene ───────────────────────────────────────────────────
-- (a) funkcija postoji i nije izvršiva za anon/authenticated (očekivano: f, f, t):
-- SELECT has_function_privilege('anon', 'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)', 'EXECUTE'),
--        has_function_privilege('authenticated', 'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)', 'EXECUTE'),
--        has_function_privilege('service_role', 'public.zabelezi_ishod_predmeta(uuid,uuid,text,text[],integer,numeric,text,text[],text)', 'EXECUTE');
-- (b) zbir = funkcija ishoda (očekivano: 0 redova razlike):
-- WITH f AS (SELECT DISTINCT o.user_id, o.tip_spora, o.predmet_id, o.ishod, e.faktor
--              FROM public.outcome_log o CROSS JOIN LATERAL unnest(o.presudni_faktori) WITH ORDINALITY e(faktor, n)
--             WHERE e.n <= 10 AND e.faktor IS NOT NULL AND o.tip_spora <> ''),
--      a AS (SELECT user_id, tip_spora, faktor, count(*) FILTER (WHERE ishod='pobeda') p,
--                   count(*) FILTER (WHERE ishod='poraz') po, count(*) u FROM f GROUP BY 1,2,3)
-- SELECT * FROM public.case_patterns c FULL JOIN a USING (user_id, tip_spora, faktor)
--  WHERE (COALESCE(c.pobede,0), COALESCE(c.porazi,0), COALESCE(c.ukupno,0)) IS DISTINCT FROM
--        (COALESCE(a.p,0), COALESCE(a.po,0), COALESCE(a.u,0));
--
-- ─── Povratak ────────────────────────────────────────────────────────────────
-- Funkcija je aditivna. Kod koji je poziva (NS4 release) MORA se vratiti PRE uklanjanja funkcije:
-- DROP FUNCTION IF EXISTS public.zabelezi_ishod_predmeta(uuid, uuid, text, text[], integer, numeric, text, text[], text);
-- Dozvole upisa vratiti samo ako se dokaže potrošač: GRANT INSERT, UPDATE, DELETE ON public.outcome_log TO authenticated;
