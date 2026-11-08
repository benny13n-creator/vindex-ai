-- Local candidate. Requires migrations 043, 073, 081 and the 126 FK.
BEGIN;

-- The non-NULL branch relies on DELETE updating this exact candidate row.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.predmet_hronologija'::regclass
          AND confrelid = 'public.predmet_dokumenti'::regclass
          AND conkey = ARRAY[(
              SELECT attnum FROM pg_catalog.pg_attribute
              WHERE attrelid = conrelid AND attname = 'dokument_id'
          )]
          AND confdeltype = 'n' AND convalidated
    ) THEN
        RAISE EXCEPTION 'S08 requires the validated migration 126 ON DELETE SET NULL foreign key';
    END IF;
END;
$$;

CREATE FUNCTION public.s08_guard_rok_confirmation() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    rok public.predmet_hronologija%ROWTYPE;
    last_confirmation timestamptz;
BEGIN
    -- A BEFORE INSERT trigger can execute before the audit RLS WITH CHECK.
    -- Decline direct callers before evaluating the resource or its source.
    IF current_user <> 'service_role' THEN
        RAISE EXCEPTION 'S08 confirmation requires the backend role' USING ERRCODE = '42501';
    END IF;

    -- Fresh snapshots after a lock wait are required for the audit lookup.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'S08 requires read committed' USING ERRCODE = '25000';
    END IF;

    SELECT * INTO rok
    FROM public.predmet_hronologija
    WHERE id = NEW.resource_id::uuid AND user_id = NEW.user_id
    FOR NO KEY UPDATE;
    IF NOT FOUND OR NEW.resource_id <> rok.id::text THEN
        RAISE EXCEPTION 'S08 deadline unavailable' USING ERRCODE = 'P0804';
    END IF;

    SELECT created_at INTO last_confirmation
    FROM public.audit_immutable
    WHERE resource_type = 'rok' AND resource_id = NEW.resource_id
      AND user_id = NEW.user_id AND action = 'rok_potvrdjen'
    ORDER BY seq DESC LIMIT 1;
    IF FOUND THEN
        -- An initial request queued behind a confirmation cannot turn itself
        -- into a human re-review. Recheck the warning for competing reviews.
        IF NOT coalesce((NEW.metadata #>> '{}')::jsonb @> '{"ponovni_pregled": true}', false)
           OR NOT EXISTS (
               SELECT 1 FROM public.events
               WHERE user_id = rok.user_id::text AND predmet_id = rok.predmet_id::text
                 AND event_type = 'SourceInvalidated'
                 AND payload->>'source_type' = 'dokument'
                 AND created_at > last_confirmation
           ) THEN
            RAISE EXCEPTION 'S08 already confirmed' USING ERRCODE = 'P0801';
        END IF;
    ELSIF rok.akter = 'Genome (AI)' AND rok.dokument_id IS NOT NULL THEN
        -- A non-null FK already fences DELETE via ON DELETE SET NULL on rok.
        -- The FK proves identity, but does not enforce case/tenant ownership.
        IF NOT EXISTS (
            SELECT 1 FROM public.predmet_dokumenti
            WHERE id = rok.dokument_id AND user_id = rok.user_id AND predmet_id = rok.predmet_id
        ) THEN
            RAISE EXCEPTION 'S08 deadline source unavailable' USING ERRCODE = 'P0804';
        END IF;
    ELSIF rok.akter = 'Genome (AI)' AND nullif(rok.dokument_naziv, '') IS NOT NULL THEN
        -- With a null FK, pin one matching name until the audit commit.
        PERFORM 1 FROM public.predmet_dokumenti
        WHERE user_id = rok.user_id AND predmet_id = rok.predmet_id
          AND naziv_fajla = rok.dokument_naziv
        ORDER BY id LIMIT 1 FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'S08 withdrawn source' USING ERRCODE = 'P0802';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.s08_guard_rok_confirmation() FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER trg_s08_guard_rok_confirmation
    BEFORE INSERT ON public.audit_immutable
    FOR EACH ROW WHEN (NEW.action = 'rok_potvrdjen' AND NEW.resource_type = 'rok')
    EXECUTE FUNCTION public.s08_guard_rok_confirmation();

-- 133/137 emit after DELETE. now() would stamp a blocked deletion with
-- its transaction start, hiding the warning if it began before confirmation.
CREATE FUNCTION public.s08_stamp_document_invalidation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.s08_stamp_document_invalidation() FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER trg_s08_stamp_document_invalidation
    BEFORE INSERT ON public.events
    FOR EACH ROW WHEN (NEW.event_type = 'SourceInvalidated' AND NEW.payload->>'source_type' = 'dokument')
    EXECUTE FUNCTION public.s08_stamp_document_invalidation();

COMMIT;
