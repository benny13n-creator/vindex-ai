-- Transactional audit for one logical court-draft approval.
-- Requires 043/081 and the 149 approval fence. Production cutover is separate.
BEGIN;

CREATE FUNCTION public.mir03_upisi_audit_odobrenja()
RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    akcija constant text := 'dokument_za_sud_odobren';
    prethodni_hash text;
    vreme timestamptz := pg_catalog.clock_timestamp();
    tekst_vremena text;
    novi_hash text;
    naziv_indeksa text;
BEGIN
    IF current_user <> 'service_role' OR NEW.approved_by IS DISTINCT FROM NEW.user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Odobrenje nije dozvoljeno.';
    END IF;
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION USING ERRCODE = '25000', MESSAGE = 'Odobrenje zahteva read committed.';
    END IF;

    -- Match the existing Python audit verifier's UTC timestamp and hash input.
    tekst_vremena := pg_catalog.to_char(vreme AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS');
    IF vreme <> pg_catalog.date_trunc('second', vreme) THEN
        tekst_vremena := tekst_vremena || pg_catalog.to_char(vreme AT TIME ZONE 'UTC', '.US');
    END IF;
    tekst_vremena := tekst_vremena || '+00:00';

    FOR pokusaj IN 1..5 LOOP
        SELECT a.entry_hash INTO prethodni_hash
        FROM public.audit_immutable AS a ORDER BY a.seq DESC LIMIT 1;
        IF NOT FOUND THEN
            prethodni_hash := pg_catalog.repeat('0', 64);
        ELSIF prethodni_hash !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION USING ERRCODE = '22000', MESSAGE = 'Glava audit lanca nije potvrđena.';
        END IF;

        novi_hash := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            prethodni_hash || '|' || NEW.user_id::uuid::text || '|' || akcija || '|' ||
            tekst_vremena || '|staging|' || NEW.id::text, 'UTF8')), 'hex');
        BEGIN
            INSERT INTO public.audit_immutable
                (prev_hash, entry_hash, user_id, action, resource_type, resource_id, metadata, created_at)
            VALUES (prethodni_hash, novi_hash, NEW.user_id::uuid, akcija, 'staging', NEW.id::text,
                pg_catalog.jsonb_build_object(
                    'predmet_id', NEW.predmet_id,
                    'sha256', NEW.quality_detail #>> '{usvajanje,odobreno,sha256}',
                    'verzija', NEW.quality_detail #> '{usvajanje,verzija}'),
                vreme);
            RETURN NEW;
        EXCEPTION WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS naziv_indeksa = CONSTRAINT_NAME;
            IF naziv_indeksa <> 'audit_immutable_prev_hash_unique' OR pokusaj = 5 THEN
                RAISE;
            END IF;
        END;
    END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION public.mir03_upisi_audit_odobrenja() FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER mir03_odobrenje_upisuje_audit
    AFTER UPDATE OF status ON public.staging_memory
    FOR EACH ROW
    WHEN (OLD.status = 'pending' AND NEW.status = 'approved' AND NEW.tip = 'dokument_za_sud')
    EXECUTE FUNCTION public.mir03_upisi_audit_odobrenja();

COMMIT;
