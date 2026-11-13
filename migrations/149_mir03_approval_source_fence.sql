-- MIR-03: serialize source withdrawal/edit with pending court-document approval.
-- Standalone candidate, requires separate reviewed production DDL authorization.
-- Depends on the application storing server-derived source text hashes in the
-- immutable approval, and on the staging_memory access controls from 141.
BEGIN;

CREATE FUNCTION public.proveri_izvore_pri_odobrenju_dokumenta_za_sud()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    ocekivani jsonb := NEW.quality_detail #> '{usvajanje,odobreno,sha256_izvori}';
    predlog_id uuid;
    predlog_hash text := OLD.quality_detail #>> '{usvajanje,predlog_sha256}';
    izvor_ids uuid[];
    dokument record;
    broj integer := 0;
    konflikt constant text := 'Izvor na koji se dokument oslanja nije potvrđen u aktuelnom spisu.';
BEGIN
    IF current_user <> 'service_role' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Odobrenje nije dozvoljeno.';
    END IF;

    IF pg_catalog.jsonb_typeof(ocekivani) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    BEGIN
        predlog_id := (OLD.quality_detail #>> '{usvajanje,predlog_id}')::uuid;
        SELECT pg_catalog.array_agg(k::uuid) INTO izvor_ids
          FROM pg_catalog.jsonb_object_keys(ocekivani) AS j(k);
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END;

    IF predlog_id IS NULL OR predlog_hash IS NULL
       OR (NEW.quality_detail #>> '{usvajanje,predlog_id}') IS DISTINCT FROM predlog_id::text
       OR (NEW.quality_detail #>> '{usvajanje,predlog_sha256}') IS DISTINCT FROM predlog_hash THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    -- Rejection and approval serialize on the immutable proposal row.
    PERFORM 1 FROM public.staging_memory AS p
    WHERE p.id = predlog_id AND p.user_id = NEW.user_id AND p.predmet_id = NEW.predmet_id
      AND p.tip = 'nacrt_iz_spisa' AND p.status <> 'rejected'
      AND p.quality_detail #>> '{predlog,sha256}' = predlog_hash
    FOR SHARE OF p;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    IF izvor_ids IS NULL THEN
        RETURN NEW;
    END IF;

    -- FOR SHARE conflicts with both text UPDATE and DELETE. Use the primary key
    -- order to give approvals a consistent lock order over multiple sources.
    FOR dokument IN
        SELECT d.id, d.tekst_sadrzaj
          FROM public.predmet_dokumenti AS d
         WHERE d.id = ANY(izvor_ids)
           AND d.predmet_id::text = NEW.predmet_id
           AND d.user_id::text = NEW.user_id
         ORDER BY d.id
         FOR SHARE OF d
    LOOP
        broj := broj + 1;
        IF pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(dokument.tekst_sadrzaj, 'UTF8')), 'hex')
                IS DISTINCT FROM (ocekivani ->> dokument.id::text)
           OR dokument.tekst_sadrzaj IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
        END IF;
    END LOOP;

    IF broj <> pg_catalog.cardinality(izvor_ids) THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.proveri_izvore_pri_odobrenju_dokumenta_za_sud()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER mir03_odobrenje_proverava_izvore
    BEFORE UPDATE OF status ON public.staging_memory
    FOR EACH ROW
    WHEN (OLD.status = 'pending' AND NEW.status = 'approved' AND NEW.tip = 'dokument_za_sud')
    EXECUTE FUNCTION public.proveri_izvore_pri_odobrenju_dokumenta_za_sud();

-- Lokalni kandidat. Pregled izvora, čuvanje predloga i naplata su jedna transakcija.
-- Povratak: -1 bez upisa zbog nedovoljno kredita, 0 bez naplate, inače novi saldo.
CREATE FUNCTION public.mir03_sacuvaj_nacrt(p_red jsonb, p_izvori jsonb, p_krediti integer)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    nacrt_id uuid;
    korisnik_id uuid;
    spis_id uuid;
    izvor_ids uuid[];
    sudski_ids uuid[];
    sudski_id uuid;
    sudski_izvori jsonb := COALESCE(p_red -> 'sudski_izvori', '[]'::jsonb);
    mesec text := p_red ->> 'mesec';
    dokument record;
    potvrda jsonb;
    vrsta text;
    broj integer := 0;
    saldo integer := 0;
    konflikt constant text := 'Izvor na koji se dokument oslanja nije potvrđen u aktuelnom spisu.';
BEGIN
    IF current_user <> 'service_role' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Čuvanje nacrta nije dozvoljeno.';
    END IF;

    IF pg_catalog.jsonb_typeof(p_red) IS DISTINCT FROM 'object'
       OR p_krediti IS NULL OR p_krediti < 0
       OR (p_krediti > 0 AND (mesec IS NULL OR mesec !~ '^[0-9]{4}-(0[1-9]|1[0-2])$')) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Nevažeći podaci za čuvanje nacrta.';
    END IF;

    IF pg_catalog.jsonb_typeof(p_izvori) IS DISTINCT FROM 'object'
       OR pg_catalog.jsonb_typeof(sudski_izvori) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    nacrt_id := (p_red ->> 'id')::uuid;
    korisnik_id := (p_red ->> 'user_id')::uuid;
    spis_id := (p_red ->> 'predmet_id')::uuid;

    IF nacrt_id IS NULL OR korisnik_id IS NULL OR spis_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Nevažeći podaci za čuvanje nacrta.';
    END IF;

    BEGIN
        SELECT pg_catalog.array_agg(k::uuid) INTO izvor_ids
          FROM pg_catalog.jsonb_object_keys(p_izvori) AS j(k);
        SELECT COALESCE(pg_catalog.array_agg(k::uuid), ARRAY[]::uuid[]) INTO sudski_ids
          FROM pg_catalog.jsonb_array_elements_text(sudski_izvori) AS j(k);
    EXCEPTION WHEN data_exception THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.unnest(sudski_ids) AS j(k)
        WHERE (p_izvori ? k::text) IS DISTINCT FROM true
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    PERFORM 1 FROM public.predmeti AS p
    WHERE p.id = spis_id AND p.user_id = korisnik_id
    FOR SHARE OF p;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    FOR dokument IN
        SELECT d.id, d.tekst_sadrzaj
          FROM public.predmet_dokumenti AS d
         WHERE d.id = ANY(izvor_ids)
           AND d.predmet_id = spis_id
           AND d.user_id = korisnik_id
         ORDER BY d.id
         FOR SHARE OF d
    LOOP
        broj := broj + 1;
        IF dokument.tekst_sadrzaj IS NULL
           OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(dokument.tekst_sadrzaj, 'UTF8')), 'hex')
                IS DISTINCT FROM (p_izvori ->> dokument.id::text) THEN
            RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
        END IF;
    END LOOP;

    IF broj <> COALESCE(pg_catalog.cardinality(izvor_ids), 0) THEN
        RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
    END IF;

    -- Reclassification updates the document before its separate audit write.
    -- Require both the locked current type and the latest human decision.
    FOREACH sudski_id IN ARRAY sudski_ids LOOP
        SELECT d.tip_dokaza, a.metadata INTO vrsta, potvrda
          FROM public.predmet_dokumenti AS d
          LEFT JOIN LATERAL (
              SELECT a.metadata
                FROM public.audit_immutable AS a
               WHERE a.user_id = korisnik_id
                 AND a.action = 'dokument_vrsta_ispravljena'
                 AND a.resource_type = 'predmet_dokumenti'
                 AND a.resource_id = d.id::text
               ORDER BY a.seq DESC
               LIMIT 1
          ) AS a ON true
         WHERE d.id = sudski_id;

        IF pg_catalog.jsonb_typeof(potvrda) = 'string' THEN
            BEGIN
                potvrda := (potvrda #>> '{}')::jsonb;
            EXCEPTION WHEN data_exception THEN
                RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
            END;
        END IF;

        IF pg_catalog.jsonb_typeof(potvrda) IS DISTINCT FROM 'object'
           OR COALESCE(potvrda ->> 'novo', '') NOT IN ('court_decision', 'judgment')
           OR (potvrda ->> 'novo') IS DISTINCT FROM vrsta
           OR (potvrda ->> 'predmet_id') IS DISTINCT FROM spis_id::text THEN
            RAISE EXCEPTION USING ERRCODE = 'PT409', MESSAGE = konflikt;
        END IF;
    END LOOP;

    IF p_krediti > 0 THEN
        saldo := public.deduct_n_credits(korisnik_id, p_krediti);
        IF saldo = -1 THEN
            RETURN -1;
        END IF;
        IF saldo IS NULL OR saldo < 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Naplata nacrta nije potvrđena.';
        END IF;
        IF COALESCE(public.increment_monthly_usage(korisnik_id, mesec), -1) < 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'Mesečna upotreba nije potvrđena.';
        END IF;
    END IF;

    INSERT INTO public.staging_memory
        (id, user_id, kancelarija_id, predmet_id, tip, naziv, tekst, confidence_score, quality_detail, status)
    VALUES
        (nacrt_id, korisnik_id::text, (p_red ->> 'kancelarija_id')::uuid, spis_id::text,
         'nacrt_iz_spisa', p_red ->> 'naziv', p_red ->> 'tekst',
         (p_red ->> 'confidence_score')::numeric, p_red -> 'quality_detail', 'pending');
    RETURN saldo;
END;
$$;

REVOKE ALL ON FUNCTION public.mir03_sacuvaj_nacrt(jsonb, jsonb, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mir03_sacuvaj_nacrt(jsonb, jsonb, integer)
    TO service_role;

-- Recovery nakon povlačenja aplikacionog poziva:
-- DROP FUNCTION IF EXISTS public.mir03_sacuvaj_nacrt(jsonb, jsonb, integer);

COMMIT;
