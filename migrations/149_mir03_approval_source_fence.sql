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

COMMIT;
