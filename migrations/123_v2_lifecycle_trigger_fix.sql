-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 123: HITNA POPRAVKA TRIGERA IZ MIGRACIJE 122
--
-- ⚠ NIJE IZVRSENA. Pokrece je osnivac.
-- ⚠ DO IZVRSENJA JE V2 PERSISTENCE POTPUNO NEUPOTREBLJIV.
--
-- ─── STA JE PUKLO ──────────────────────────────────────────────────────────
-- Migracija 122 je izvrsena i njen DEO 3 je uveo JEDNU trigger funkciju za DVE
-- tabele. Prva linija te funkcije glasi:
--
--     v_kontr := COALESCE(NEW.contradiction_id, OLD.contradiction_id, NEW.id, OLD.id);
--
-- U plpgsql `NEW.contradiction_id` nad tabelom koja tu kolonu NEMA nije NULL
-- nego GRESKA, pa `COALESCE` nikad ne stigne da odradi svoj posao. Izmereno
-- uzivo u A016.2C:
--
--     INSERT predmet_issues          -> OK
--     INSERT predmet_contradictions  -> 42703  record "new" has no field "contradiction_id"
--     INSERT (state='NOT_OBSERVED')  -> 42703  isto
--
-- Posledica: SVAKI upis u `predmet_contradictions` puca, dakle ceo V2 lifecycle
-- je oboren. Isti kvar ima i druga grana: `AFTER ... DELETE` nad
-- `predmet_contradiction_claims` cita `NEW`, koji pri brisanju uopste nije
-- dodeljen.
--
-- Blast radius u produkciji: NULA. V2 jos nije uvezan ni u jednu produkcionu
-- putanju (A015/A016 -- adapter ima 0 call-site-ova), `predmet_contradictions`
-- ima 0 redova, i nijedan korisnicki tok ne dodiruje te tabele.
--
-- ─── POPRAVKA ──────────────────────────────────────────────────────────────
-- Jedna provera, DVA tanka omotaca -- svaki cita samo polja koja njegova tabela
-- stvarno ima. Nema dinamickog pristupa polju, nema `COALESCE` preko tabela.
-- Semantika invarijante je nepromenjena u odnosu na 122.
-- ═══════════════════════════════════════════════════════════════════════════

DROP TRIGGER IF EXISTS trg_v2_kontradikcija_invarijanta ON public.predmet_contradictions;
DROP TRIGGER IF EXISTS trg_v2_clanstvo_invarijanta      ON public.predmet_contradiction_claims;
DROP FUNCTION IF EXISTS public.v2_kontradikcija_invarijanta();


-- ── ZAJEDNICKA PROVERA ─────────────────────────────────────────────────────
-- Invarijanta vazi SAMO za `state='OPEN'`. Zatvorena kontradikcija sme imati
-- nula aktivnih clanova -- to je upravo ono sto zatvaranje i znaci.
CREATE OR REPLACE FUNCTION public.v2_proveri_kontradikciju(p_kontr UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_stanje   TEXT;
    v_predmet  UUID;
    v_aktivnih INT;
    v_tudjih   INT;
BEGIN
    IF p_kontr IS NULL THEN
        RETURN;
    END IF;

    SELECT pc.state, pi.predmet_id INTO v_stanje, v_predmet
      FROM public.predmet_contradictions pc
      JOIN public.predmet_issues pi ON pi.id = pc.issue_id
     WHERE pc.id = p_kontr;

    -- Red je u medjuvremenu obrisan (npr. ON DELETE CASCADE) -- nema sta da se
    -- proverava. Ovo je i razlog zasto brisanje kontradikcije mora ostati
    -- dozvoljeno bez obzira na clanstvo.
    IF v_stanje IS NULL OR v_stanje <> 'OPEN' THEN
        RETURN;
    END IF;

    SELECT count(DISTINCT pcc.dokaz_id) INTO v_aktivnih
      FROM public.predmet_contradiction_claims pcc
     WHERE pcc.contradiction_id = p_kontr AND pcc.removed_at IS NULL;

    IF v_aktivnih < 2 THEN
        RAISE EXCEPTION 'kontradikcija % je OPEN sa % aktivnih tvrdnji (minimum je 2)',
            p_kontr, v_aktivnih USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO v_tudjih
      FROM public.predmet_contradiction_claims pcc
      JOIN public.predmet_dokazi pd ON pd.id = pcc.dokaz_id
     WHERE pcc.contradiction_id = p_kontr AND pcc.removed_at IS NULL
       AND (pd.predmet_id <> v_predmet OR pd.deleted_at IS NOT NULL);

    IF v_tudjih > 0 THEN
        RAISE EXCEPTION 'kontradikcija % ima % tvrdnji van predmeta % ili obrisanih',
            p_kontr, v_tudjih, v_predmet USING ERRCODE = '23503';
    END IF;
END;
$$;


-- ── OMOTAC 1: predmet_contradictions ───────────────────────────────────────
-- AFTER INSERT OR UPDATE -> `NEW` je uvek dodeljen; `NEW.id` uvek postoji.
CREATE OR REPLACE FUNCTION public.v2_trg_kontradikcija()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM public.v2_proveri_kontradikciju(NEW.id);
    RETURN NULL;
END;
$$;


-- ── OMOTAC 2: predmet_contradiction_claims ─────────────────────────────────
-- Pri DELETE `NEW` NIJE dodeljen, pa se sme citati iskljucivo `OLD`.
CREATE OR REPLACE FUNCTION public.v2_trg_clanstvo()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM public.v2_proveri_kontradikciju(OLD.contradiction_id);
    ELSE
        PERFORM public.v2_proveri_kontradikciju(NEW.contradiction_id);
        -- Premestanje clanstva izmedju kontradikcija se ne desava u praksi, ali
        -- ako se ikad desi, i STARA kontradikcija mora ostati validna.
        IF TG_OP = 'UPDATE' AND OLD.contradiction_id IS DISTINCT FROM NEW.contradiction_id THEN
            PERFORM public.v2_proveri_kontradikciju(OLD.contradiction_id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;


CREATE CONSTRAINT TRIGGER trg_v2_kontradikcija_invarijanta
    AFTER INSERT OR UPDATE ON public.predmet_contradictions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.v2_trg_kontradikcija();

CREATE CONSTRAINT TRIGGER trg_v2_clanstvo_invarijanta
    AFTER INSERT OR UPDATE OR DELETE ON public.predmet_contradiction_claims
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.v2_trg_clanstvo();


-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK:
--   DROP TRIGGER IF EXISTS trg_v2_clanstvo_invarijanta      ON public.predmet_contradiction_claims;
--   DROP TRIGGER IF EXISTS trg_v2_kontradikcija_invarijanta ON public.predmet_contradictions;
--   DROP FUNCTION IF EXISTS public.v2_trg_clanstvo();
--   DROP FUNCTION IF EXISTS public.v2_trg_kontradikcija();
--   DROP FUNCTION IF EXISTS public.v2_proveri_kontradikciju(UUID);
-- Time se V2 vraca u stanje bez odlozene invarijante (kao posle migracije 121),
-- sto je i dalje upotrebljivo -- za razliku od trenutnog stanja posle 122.
-- Tabele, indeksi i redovi se ne diraju ni u jednom smeru.
-- ═══════════════════════════════════════════════════════════════════════════
