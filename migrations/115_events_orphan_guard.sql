-- ============================================================================
-- 115 — BLK-2.1: `events` red se ne upisuje za predmet koji se briše ili je
--        obrisan. ATOMARNO, na nivou baze.
--
-- ZAŠTO POSTOJI
--
-- `shared/predmet_deletion.py` briše `events` u koraku 5b, a `predmeti` red tek
-- u koraku 7. Svaki pisac koji upiše događaj IZMEĐU ta dva koraka ostavlja red
-- koji pokazuje na predmet kog više nema. `events.predmet_id` nema strani ključ,
-- pa ga korak 7 ne dodiruje.
--
-- Izmereno determinističkom trkom (barijera puštena TAČNO kad korak 5b obriše
-- `events`), produkcija `61dd6b6`:  **54 od 55 iteracija = orphan**.
--
-- Aplikativni guard (`services/event_bus.py::predmet_prima_dogadjaje`, commit
-- `1c0d7119`) je tu trku zatvorio: **0 od 55**. Ali guard radi SELECT pa INSERT,
-- što je po definiciji neatomarno. Izmereno prisilnim rasporedom (INSERT gurnut
-- posle CELOG brisanja): **55 od 55 = orphan**. Aplikativna provera taj prozor
-- ne može zatvoriti — samo baza može.
--
-- ZAŠTO NE STRANI KLJUČ
--
-- `events.predmet_id` je `TEXT`, `predmeti.id` je `UUID`. Izmereno na produkciji:
-- **871 od 1000** redova u uzorku nosi vrednosti koje NISU UUID (`pred-1`,
-- `pred-001` — talog jediničnih testova), plus 86 sa `NULL`. Strani ključ bi
-- tražio promenu tipa kolone i brisanje/migraciju tih redova. Invarijanta 8
-- specifikacije (`docs/beta_gate/P15_LIFECYCLE_SPECIFICATION.md`) to izričito
-- zabranjuje bez dokaza da orphan redova nema — a ovde ih ima.
--
-- ZAŠTO `RETURN NULL`, A NE `RAISE`
--
-- `RETURN NULL` u `BEFORE INSERT ... FOR EACH ROW` tiho otkazuje upis TOG reda.
-- To je isto ponašanje koje aplikativni guard već ima (rani `return`), pa je
-- ugovor prema pozivaocima nepromenjen: nijedan pisac ne proverava povratne
-- podatke `insert().execute()`. `RAISE` bi propagirao izuzetak kroz
-- `emit_durable` i menjao ponašanje svih 11+ pozivalaca.
--
-- ŠTA OVO NE RADI
--
-- Ne dira postojeće redove. Ne menja tip nijedne kolone. Ne briše ništa.
-- Ne dodiruje `audit_immutable` niti bilo koji audit (v. BLK-2 §6).
-- Deploy je bezbedan u oba redosleda: kod bez migracije radi (guard pokriva
-- uobičajen slučaj), migracija bez novog koda takođe radi (okidač je samostalan).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.events_odbij_za_obrisan_predmet()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    _pid   UUID;
    _stanje RECORD;
BEGIN
    -- Sistemski događaj (nije vezan za predmet) — prolazi nedirnut.
    IF NEW.predmet_id IS NULL OR btrim(NEW.predmet_id) = '' THEN
        RETURN NEW;
    END IF;

    -- `predmet_id` koji nije UUID ne može referencirati stvaran predmet
    -- (`predmeti.id` je UUID), pa ne može ni biti orphan. Prolazi nedirnut —
    -- inače bi 871 postojećih test-redova počelo da puca sa 22P02.
    BEGIN
        _pid := NEW.predmet_id::UUID;
    EXCEPTION WHEN others THEN
        RETURN NEW;
    END;

    SELECT id, brisanje_zapoceto INTO _stanje
    FROM public.predmeti
    WHERE id = _pid;

    -- Predmet ne postoji (obrisan) — red bi bio orphan.
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    -- Predmet je označen za brisanje — korak 5b je već prošao, red bi preživeo
    -- korak 7 kao orphan.
    IF _stanje.brisanje_zapoceto IS NOT NULL THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_events_odbij_za_obrisan_predmet ON public.events;
CREATE TRIGGER trg_events_odbij_za_obrisan_predmet
    BEFORE INSERT ON public.events
    FOR EACH ROW EXECUTE FUNCTION public.events_odbij_za_obrisan_predmet();

COMMENT ON FUNCTION public.events_odbij_za_obrisan_predmet() IS
    'BLK-2.1 — atomarno sprecava orphan `events` red za predmet koji se brise ili je obrisan. Aplikativni guard (services/event_bus.py::predmet_prima_dogadjaje) pokriva uobicajen slucaj; ovaj okidac zatvara TOCTOU prozor izmedju njegove provere i upisa, koji aplikacija ne moze zatvoriti. Tiho otkazuje upis (RETURN NULL), ne baca izuzetak — isti ugovor koji pozivaoci vec imaju.';
