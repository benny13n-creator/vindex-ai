-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 120: CONTRADICTION V2 — atomicnost i zastita od trke
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run
--
-- ⚠ NIJE IZVRSENA. Napisana u A010; pokrece je osnivac.
--
-- ZASTO POSTOJI — migracija 119 je verifikovana i DOVOLJNA za PREDSTAVLJANJE
-- domena (A010 §3, F1–F5 svi PASS), ali NEDOVOLJNA za BEZBEDAN UPIS:
--
--   1. ATOMICNOST. Jedan logicki nalaz trazi upis u TRI tabele
--      (predmet_issues → predmet_contradictions → predmet_contradiction_claims).
--      PostgREST klijent nema transakcije. Delimican upis ostavlja
--      "authoritative" spornu tacku bez ijednog clana — stanje koje V2 domen
--      ne definise.
--
--   2. TRKA PRI KREIRANJU. `predmet_issues.id` je `gen_random_uuid()` i NAMERNO
--      se ne izvodi iz sadrzaja (A008 I12). Dva istovremena Genome refresh-a nad
--      istim ulazom oba vide "0 kandidata" (ne vide tudji jos-neupisani red) i
--      oba kreiraju NOVU spornu tacku. Rezultat: 2 sporne tacke za 1 spor.
--
-- Oba se zatvaraju NA NIVOU BAZE, ne aplikacionom logikom — isti doktrinarni
-- izbor koji migracija 099 vec zapisuje ("DB ogranicenje, ne aplikaciona
-- logika, garantuje bezbednost pri konkurentnim projekcijama") i isti obrazac
-- koji vec koriste 073/091/092/107/108 (Postgres funkcija preko `supa.rpc`).
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── 1. OTISAK POCETNOG SKUPA TVRDNJI ───────────────────────────────────────
-- NIJE identitet. Identitet ostaje `id` (UUID iz baze). Ovo je iskljucivo
-- ZASTITA OD DUPLIKATA pri istovremenom kreiranju.
--
-- Izvodi se iz `predmet_dokazi.id` vrednosti (identiteta IZ BAZE), NIKAD iz
-- labela, opisa, lokacije ni ijednog LLM teksta — zato ne krsi A008 I12.
--
-- NEPROMENLJIV je posle kreiranja: cuva otisak POCETNOG clanstva. Zato
-- evolucija clanstva (dodavanje/izostanak tvrdnje) NIKAD ne moze da udari u
-- ovo ogranicenje — ono vazi samo na tacki nastanka.
ALTER TABLE public.predmet_issues
  ADD COLUMN IF NOT EXISTS initial_claim_fingerprint TEXT;

COMMENT ON COLUMN public.predmet_issues.initial_claim_fingerprint IS
  'sha256 nad sortiranim skupom predmet_dokazi.id vrednosti u trenutku NASTANKA sporne tacke. NIJE identitet -- identitet je `id`. Sluzi iskljucivo kao DB-nivo zastita od duplikata pri istovremenom kreiranju. Nepromenljiv posle INSERT-a.';

-- Dve sporne tacke u ISTOM predmetu ne smeju nastati nad istim pocetnim
-- skupom tvrdnji. Spojene (`MERGED`) su izuzete -- one su tombstone i smeju
-- koegzistirati sa prezivelom.
CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_initial_fingerprint
  ON public.predmet_issues(predmet_id, initial_claim_fingerprint)
  WHERE initial_claim_fingerprint IS NOT NULL AND status <> 'MERGED';

-- ─── 2. ATOMICAN UPIS ───────────────────────────────────────────────────────
-- Ulaz je VEC RAZRESEN u Python domenskom sloju (`shared/issue_v2.py`), koji je
-- pokriven sa 86 testova i 20/20 ubijenih mutacija. Ova funkcija NE donosi
-- nijednu odluku o identitetu -- ona samo atomicno UPISUJE vec donetu odluku.
--
--   p_issue_id IS NULL  → kreiraj novu spornu tacku (uz zastitu otiskom)
--   p_issue_id NOT NULL → nastavi postojecu (kontinuitet, odlucen u Python-u)
--
-- Vraca (issue_id, contradiction_id, created_issue).
CREATE OR REPLACE FUNCTION public.v2_persist_contradiction(
    p_predmet_id     UUID,
    p_user_id        UUID,
    p_issue_id       UUID,
    p_label          TEXT,
    p_relation_type  TEXT,
    p_tezina         TEXT,
    p_fingerprint    TEXT,
    p_dokaz_ids      UUID[],
    p_claim_identiteti TEXT[]
) RETURNS TABLE (issue_id UUID, contradiction_id UUID, created_issue BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_issue      UUID;
    v_kontr      UUID;
    v_created    BOOLEAN := FALSE;
    i            INT;
BEGIN
    -- Kontradikcija bez najmanje dve tvrdnje nije spor. Fail-closed, ista
    -- granica koju Python sloj vec sprovodi (MIN_TVRDNJI).
    IF p_dokaz_ids IS NULL OR array_length(p_dokaz_ids, 1) < 2 THEN
        RAISE EXCEPTION 'v2_persist_contradiction: najmanje 2 tvrdnje su obavezne (dobijeno %)',
            COALESCE(array_length(p_dokaz_ids, 1), 0)
            USING ERRCODE = '22023';
    END IF;

    IF p_issue_id IS NULL THEN
        -- KREIRANJE. `ON CONFLICT` nad parcijalnim UNIQUE indeksom je tacka na
        -- kojoj se trka gubi bez izuzetka: drugi proces ne dobija gresku nego
        -- POSTOJECU spornu tacku.
        INSERT INTO public.predmet_issues
            (predmet_id, user_id, label, status, initial_claim_fingerprint)
        VALUES (p_predmet_id, p_user_id, p_label, 'DISCOVERED', p_fingerprint)
        ON CONFLICT (predmet_id, initial_claim_fingerprint)
            WHERE initial_claim_fingerprint IS NOT NULL AND status <> 'MERGED'
        DO NOTHING
        RETURNING id INTO v_issue;

        IF v_issue IS NULL THEN
            SELECT id INTO v_issue
              FROM public.predmet_issues
             WHERE predmet_id = p_predmet_id
               AND initial_claim_fingerprint = p_fingerprint
               AND status <> 'MERGED'
             LIMIT 1;
        ELSE
            v_created := TRUE;
            IF p_label IS NOT NULL THEN
                INSERT INTO public.predmet_issue_labels (issue_id, label, izvor)
                VALUES (v_issue, p_label, 'producer');
            END IF;
        END IF;
    ELSE
        SELECT id INTO v_issue
          FROM public.predmet_issues
         WHERE id = p_issue_id AND predmet_id = p_predmet_id;      -- opseg predmeta
        IF v_issue IS NULL THEN
            RAISE EXCEPTION 'v2_persist_contradiction: sporna tacka % ne pripada predmetu %',
                p_issue_id, p_predmet_id USING ERRCODE = '23503';
        END IF;
    END IF;

    -- Kontradikcija: najvise jedna OTVORENA po (sporna tacka, tip relacije).
    SELECT id INTO v_kontr
      FROM public.predmet_contradictions
     WHERE issue_id = v_issue AND relation_type = p_relation_type AND state = 'OPEN'
     LIMIT 1;

    IF v_kontr IS NULL THEN
        INSERT INTO public.predmet_contradictions (issue_id, relation_type, state, tezina)
        VALUES (v_issue, p_relation_type, 'OPEN', p_tezina)
        ON CONFLICT (issue_id, relation_type) WHERE state = 'OPEN' DO NOTHING
        RETURNING id INTO v_kontr;

        IF v_kontr IS NULL THEN
            SELECT id INTO v_kontr
              FROM public.predmet_contradictions
             WHERE issue_id = v_issue AND relation_type = p_relation_type AND state = 'OPEN'
             LIMIT 1;
        END IF;
    ELSE
        UPDATE public.predmet_contradictions
           SET tezina = COALESCE(p_tezina, tezina), updated_at = now()
         WHERE id = v_kontr;
    END IF;

    -- CLANSTVO. Tvrdnja koja vise nije u dolazecem skupu dobija `removed_at`
    -- i razlog `NOT_OBSERVED` -- NIKAD `RESOLVED` i NIKAD DELETE.
    UPDATE public.predmet_contradiction_claims
       SET removed_at = now(), removed_reason = 'NOT_OBSERVED'
     WHERE contradiction_id = v_kontr
       AND removed_at IS NULL
       AND dokaz_id <> ALL (p_dokaz_ids);

    FOR i IN 1 .. array_length(p_dokaz_ids, 1) LOOP
        INSERT INTO public.predmet_contradiction_claims
            (contradiction_id, dokaz_id, claim_identitet)
        VALUES (v_kontr, p_dokaz_ids[i],
                CASE WHEN p_claim_identiteti IS NULL THEN NULL
                     ELSE p_claim_identiteti[i] END)
        ON CONFLICT (contradiction_id, dokaz_id) WHERE removed_at IS NULL
        DO NOTHING;
    END LOOP;

    RETURN QUERY SELECT v_issue, v_kontr, v_created;
END;
$$;

COMMENT ON FUNCTION public.v2_persist_contradiction IS
  'A010 -- ATOMICAN upis jedne V2 kontradikcije (sporna tacka + kontradikcija + clanstvo) u JEDNOJ transakciji. NE donosi odluku o identitetu: odluku donosi shared/issue_v2.py i prosledjuje je kroz p_issue_id. Trka pri kreiranju se gubi bez izuzetka -- ON CONFLICT vraca POSTOJECU spornu tacku umesto da napravi drugu.';

REVOKE ALL ON FUNCTION public.v2_persist_contradiction FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.v2_persist_contradiction TO service_role;

-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK
--   DROP FUNCTION IF EXISTS public.v2_persist_contradiction(UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,UUID[],TEXT[]);
--   DROP INDEX  IF EXISTS public.idx_issues_initial_fingerprint;
--   ALTER TABLE public.predmet_issues DROP COLUMN IF EXISTS initial_claim_fingerprint;
-- Bez posledica po postojece podatke -- V2 tabele su prazne (0 redova, A010 §4).
-- ═══════════════════════════════════════════════════════════════════════════
