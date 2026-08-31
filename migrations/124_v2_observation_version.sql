-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 124: OBSERVATION VERSION + PAKETNA ATOMICNOST
--
-- ⚠ NIJE IZVRSENA. Pokrece je osnivac (DDL kanal ne postoji — utvrdjeno A011,
--   provereno ponovo u A016.7: svi connection string-ovi UNSET, psql nema).
--
-- ─── STA ZATVARA ───────────────────────────────────────────────────────────
-- A016.3  `persist_paket` je atoman po PREDLOGU, ne po PAKETU (mereno:
--         paket #0 validan / #1 pao -> prvi PREZIVI).
-- A016.4  ustajalo opazanje ponovo otvara ono sto je novije zatvorilo
--         (mereno: B zatvori -> A persistira -> OPEN).
-- A016.5  `updated_at` NIJE observation clock (mereno 0/3): nema auto-touch
--         trigera, ljudska odluka ga ne pomera, pa guard propusta.
-- A016.6  dizajn: `observation_version` po predmetu + `xmin` kao row-version.
--
-- ─── ZASTO OVAKO, A NE DRUGACIJE ───────────────────────────────────────────
--
-- (1) NEMA DUPLIRANE LOGIKE.  Paketna funkcija NE prepisuje logiku upisa nego
--     N puta poziva postojecu `v2_persist_contradiction`. Telo plpgsql funkcije
--     JESTE jedna transakcija, pa se paketna atomicnost dobija besplatno, bez
--     drugog vlasnika istog pravila. To je i jedina odbrana koju imam od klase
--     gresaka koja me je vec dvaput kostala (42702 u 120, 42703 u 122): sto
--     manje NOVOG SQL-a, to manje neproverenog SQL-a.
--
-- (2) JEDAN LOCK, NE N.  Zakljucava se JEDAN red `predmeti`, ne N spornih
--     tacaka. Time nestaje pitanje determinististickog redosleda zakljucavanja
--     (A016.4 GAP-3) — ne resava se, nego prestaje da postoji.
--
-- (3) BEZ `updated_at`.  Poredak nosi `observation_version`, ne vreme. Zato
--     ova funkcija NE poziva `v2_close_unobserved` (koja trazi
--     `p_observed_since`) nego zatvara inline, oslonjena na verziju i lock.
--     `v2_close_unobserved` ostaje netaknuta za postojece pozivaoce.
--
-- (4) INKREMENT U ISTOJ TRANSAKCIJI.  `UPDATE ... RETURNING`, ne `nextval`.
--     Rollback ponistava i inkrement, pa u numeraciji NEMA RUPA (A016.6 §7).
-- ═══════════════════════════════════════════════════════════════════════════


-- ── DEO 1: jedina nova kolona ──────────────────────────────────────────────
ALTER TABLE public.predmeti
    ADD COLUMN IF NOT EXISTS observation_version INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.predmeti.observation_version IS
  'A016.6/A016.7 -- monotona verzija opazanja po predmetu. Inkrementira se ISKLJUCIVO unutar v2_persist_observation_package, u istoj transakciji kao i upis paketa, pa rollback ponistava i inkrement (nema rupa). NIJE identitet i NIJE vreme -- sluzi samo za poredak opazanja nad JEDNIM predmetom.';


-- ── DEO 2: paketni upis ────────────────────────────────────────────────────
--
-- p_paket je JSONB niz; svaka stavka:
--   {"indeks": 0,
--    "issue_ref": null | "<uuid>" | "__nova__<i>",
--        -- odluka domena. `__nova__<i>` znaci "nastavlja spornu tacku koju je
--        -- stavka #i stvorila U OVOM ISTOM PAKETU". Adapter to vise NE moze da
--        -- prevede sam: u paketnom rezimu nema medjurezultata izmedju stavki,
--        -- pa prevod mora ovde. Bez ovoga bi paket {C1,C2} pa {C1,C2,C3} poslao
--        -- token umesto UUID-a i pao na 22P02 -- ista greska koju je A013 vec
--        -- jednom platio, samo pomerena u novi sloj.
--    "label": "...", "relation_type": "...", "tezina": "..." | null,
--    "fingerprint": "...",
--    "dokaz_ids": ["<uuid>", ...],
--    "claim_identiteti": [null, ...],
--    "expected_xmin": null | "1924628"}    -- xmin reda sporne tacke u trenutku odluke
--
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

    -- ── LINEARIZACIONA TACKA ────────────────────────────────────────────────
    -- Jedan red, jedan lock. Sve sto sledi je serijalizovano po predmetu.
    SELECT pr.observation_version INTO v_tekuca
      FROM public.predmeti pr
     WHERE pr.id = p_predmet_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'v2_persist_observation_package: predmet % ne postoji', p_predmet_id
            USING ERRCODE = '23503';
    END IF;

    -- ── STALE GUARD ────────────────────────────────────────────────────────
    -- Pozivalac saopstava koju je verziju video kad je doneo odluku. Ako je u
    -- medjuvremenu neko drugi commit-ovao, ova operacija NE SME da prodje.
    -- Ovo je zamena za `updated_at`, koji je A016.5 oborio.
    IF p_expected_version IS NOT NULL AND p_expected_version <> v_tekuca THEN
        RAISE EXCEPTION 'v2_persist_observation_package: ustajalo opazanje (video verziju %, tekuca je %)',
            p_expected_version, v_tekuca
            USING ERRCODE = '40001';
    END IF;

    v_nova := v_tekuca + 1;
    UPDATE public.predmeti SET observation_version = v_nova WHERE id = p_predmet_id;

    -- ── PAKET: sve ili nista ───────────────────────────────────────────────
    FOR v_stavka IN SELECT * FROM jsonb_array_elements(COALESCE(p_paket, '[]'::jsonb))
    LOOP
        v_idx       := COALESCE((v_stavka ->> 'indeks')::INTEGER, 0);
        v_ref       := NULLIF(v_stavka ->> 'issue_ref', '');
        v_xmin_ocek := NULLIF(v_stavka ->> 'expected_xmin', '');

        -- Razresenje reference na spornu tacku. `left(...)` namerno, a ne LIKE:
        -- u LIKE obrascu je `_` dzoker, pa bi '__nova__%' pogadjao i tudje nizove.
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

        -- Revalidacija snapshot odluke (A016.6 §7): odluka je doneta u Pythonu
        -- nad redom koji je tada imao odredjen `xmin`. Ako se red u medjuvremenu
        -- promenio -- ljudski RESOLVED, drugo opazanje, bilo sta -- odluka vise
        -- ne vazi i CEO paket se odbija. Nikad tiha korekcija.
        IF v_issue_in IS NOT NULL AND v_xmin_ocek IS NOT NULL THEN
            SELECT pi.xmin::text INTO v_xmin_sad
              FROM public.predmet_issues pi
             WHERE pi.id = v_issue_in;

            IF v_xmin_sad IS NULL OR v_xmin_sad <> v_xmin_ocek THEN
                RAISE EXCEPTION 'v2_persist_observation_package: sporna tacka % je promenjena od donosenja odluke (xmin % -> %)',
                    v_issue_in, v_xmin_ocek, COALESCE(v_xmin_sad, 'obrisan')
                    USING ERRCODE = '40001';
            END IF;
        END IF;

        -- Postojeca funkcija, nepromenjena. Njen izuzetak obara CELU transakciju,
        -- dakle i inkrement verzije i sve prethodne stavke paketa.
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

    -- ── LIFECYCLE, U ISTOJ TRANSAKCIJI ─────────────────────────────────────
    -- Zatvaranje pripada paketu (A016.4 F3): nove kontradikcije ne smeju biti
    -- vidljive bez zatvaranja onih kojih vise nema. Bez `p_observed_since` --
    -- poredak nosi verzija, a iskljucivost lock.
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
  'A016.7 -- JEDNO opazanje = JEDNA transakcija. Zakljucava jedan red `predmeti`, odbija ustajalo opazanje preko `observation_version`, revalidira snapshot odluku preko `xmin`, poziva postojecu v2_persist_contradiction po stavci (bez dupliranja logike) i u istoj granici zatvara neopazene. `p_event_id` se prima radi audita; trajno belezenje identiteta run-a trazi kolonu koju A016.7 nije smeo da doda.';


-- ═══════════════════════════════════════════════════════════════════════════
-- STA OVAJ FAJL SVESNO NE RESAVA
--
-- 1. IDENTITET RUN-a SE NE PAMTI.  `p_event_id` se prima i koristi u poruci,
--    ali se nigde ne upisuje -- A016.7 §5 dozvoljava tacno JEDNU novu kolonu
--    (`observation_version`), a trajno belezenje `event_id` trazilo bi drugu.
--    Posledica: retry istog run-a i NOVO opazanje sa identicnim sadrzajem se
--    na nivou baze i dalje NE RAZLIKUJU. Retry je bezbedan samo zato sto je
--    upis idempotentan po sadrzaju, uz svez procitanu verziju.
--
-- 2. `SUPERSEDED` i `MERGED` i dalje nemaju pisca.
--
-- 3. Zatvaranje ne postavlja `predmet_issues.close_reason`/`closed_at` --
--    lifecycle sporne tacke (za razliku od kontradikcije) jos nema vlasnika.
--
-- ROLLBACK:
--   DROP FUNCTION IF EXISTS public.v2_persist_observation_package(UUID,UUID,TEXT,INTEGER,BOOLEAN,JSONB);
--   ALTER TABLE public.predmeti DROP COLUMN IF EXISTS observation_version;
-- Postojece funkcije 121/122/123 se NE diraju ni u jednom smeru.
-- ═══════════════════════════════════════════════════════════════════════════
