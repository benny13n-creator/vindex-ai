-- ============================================================================
-- Vindex AI — Migracija 073: Smart Intake Phase 0 — Foundations
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 072.
--
-- Kontekst: Faza 0 implementacije Smart Intake Engine-a (docs/adr/, dizajn
-- zamrznut kao bazelin — ne menjati bez formalnog ADR-a). Cilj Faze 0:
-- učiniti upload pouzdanim i trajnim, BEZ ikakve promene AI ponašanja —
-- klasifikacija/ekstrakcija/case-matching dolaze tek u Fazi 1.
--
-- Tri tabele:
--   events            — durable outbox za event bus (ADR-0001, dizajn §6/§26.4).
--                        services/event_bus.py je danas in-memory/fire-and-
--                        forget — gubi događaje na restart. Ova tabela je
--                        "source of truth" pre nego što handler ikad
--                        pokuša da se pozove.
--   intake_jobs        — Postgres-backed job queue (ADR-0002). status je
--                        sama queue — workeri claim-uju redove preko
--                        claim_intake_job() RPC (SELECT FOR UPDATE SKIP
--                        LOCKED — PostgREST to ne ume direktno, zato RPC).
--   intake_audit_log   — append-only, mirroring feature_registry_audit.
--
-- enqueue_intake_job() RPC daje atomsku "Upload Transaction" — job insert +
-- audit log + outbox event u JEDNOJ Postgres transakciji, isti obrazac kao
-- postojeći deduct_credit()/deduct_n_credits() RPC-ovi.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.events (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type         TEXT NOT NULL,
    user_id            TEXT,
    predmet_id         TEXT,
    payload            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at      TIMESTAMPTZ,
    dispatch_attempts  INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT
);

COMMENT ON TABLE public.events IS
    'Durable outbox za services/event_bus.py (ADR-0001). Napisano u istoj Postgres transakciji kao promena koja ga je izazvala (preko RPC funkcija poput enqueue_intake_job). Poller (dispatch_pending_events) čita nedispečovane redove i poziva postojeći in-memory handler registry — "ništa se ne gubi" čak i posle restarta/redeploy-a.';

CREATE INDEX IF NOT EXISTS idx_events_undispatched
    ON public.events(created_at) WHERE dispatched_at IS NULL;

ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "events_service_role" ON public.events
    FOR ALL USING (auth.role() = 'service_role');


CREATE TABLE IF NOT EXISTS public.intake_jobs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source             TEXT NOT NULL DEFAULT 'dropzone'
                        CHECK (source IN ('dropzone', 'mobile', 'watcher', 'email', 'scanner', 'portal', 'api')),
    content_sha256     TEXT NOT NULL,
    storage_path       TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'received'
                        CHECK (status IN ('received', 'preprocessing', 'classifying', 'extracting',
                                           'matching', 'dedup_check', 'awaiting_review', 'completed', 'failed')),
    predmet_id         TEXT,
    kancelarija_id     TEXT,
    uploaded_by        TEXT NOT NULL,
    idempotency_key    TEXT,
    attempts           INTEGER NOT NULL DEFAULT 0,
    max_attempts       INTEGER NOT NULL DEFAULT 5,
    next_retry_at      TIMESTAMPTZ,
    last_error         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ
);

COMMENT ON TABLE public.intake_jobs IS
    'Postgres-backed job queue (ADR-0002) — status JE queue-a. Workeri claim-uju preko claim_intake_job() RPC, nikad direktnim UPDATE-om (race condition bez FOR UPDATE SKIP LOCKED, koji PostgREST ne izlaže).';
COMMENT ON COLUMN public.intake_jobs.idempotency_key IS
    'Klijentski retry-after-timeout zaštita. content_sha256 je zaseban dedup mehanizam za identičan sadržaj fajla.';

CREATE INDEX IF NOT EXISTS idx_intake_jobs_claimable
    ON public.intake_jobs(status, next_retry_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_intake_jobs_idempotency
    ON public.intake_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;

ALTER TABLE public.intake_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "intake_jobs_service_role" ON public.intake_jobs
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "intake_jobs_owner_read" ON public.intake_jobs
    FOR SELECT USING (auth.role() = 'authenticated' AND uploaded_by = auth.uid()::text);


CREATE TABLE IF NOT EXISTS public.intake_audit_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_job_id  UUID NOT NULL REFERENCES public.intake_jobs(id),
    event_type     TEXT NOT NULL,
    actor          TEXT NOT NULL CHECK (actor IN ('system', 'user')),
    before         JSONB,
    after          JSONB,
    at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.intake_audit_log IS
    'Append-only, mirroring feature_registry_audit. Nikad UPDATE/DELETE — istorija svake promene stanja jednog intake job-a.';

CREATE INDEX IF NOT EXISTS idx_intake_audit_job
    ON public.intake_audit_log(intake_job_id, at DESC);

ALTER TABLE public.intake_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "intake_audit_log_service_role" ON public.intake_audit_log
    FOR ALL USING (auth.role() = 'service_role');
-- Namerno NEMA UPDATE/DELETE politike — append-only.


-- ── enqueue_intake_job — atomska "Upload Transaction" ───────────────────────
-- Job insert + audit log + outbox event u JEDNOJ transakciji. Idempotentna
-- preko idempotency_key: ponovljen poziv sa istim ključem vraća POSTOJEĆI
-- job_id umesto da kreira duplikat (klijentski retry-after-timeout zaštita).

CREATE OR REPLACE FUNCTION public.enqueue_intake_job(
    p_source          TEXT,
    p_content_sha256  TEXT,
    p_storage_path    TEXT,
    p_uploaded_by     TEXT,
    p_kancelarija_id  TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_job_id UUID;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT id INTO v_job_id FROM public.intake_jobs WHERE idempotency_key = p_idempotency_key;
        IF v_job_id IS NOT NULL THEN
            RETURN v_job_id;
        END IF;
    END IF;

    INSERT INTO public.intake_jobs (source, content_sha256, storage_path, uploaded_by, kancelarija_id, idempotency_key)
    VALUES (p_source, p_content_sha256, p_storage_path, p_uploaded_by, p_kancelarija_id, p_idempotency_key)
    RETURNING id INTO v_job_id;

    INSERT INTO public.intake_audit_log (intake_job_id, event_type, actor, after)
    VALUES (v_job_id, 'job_created', 'system', jsonb_build_object('status', 'received', 'source', p_source));

    INSERT INTO public.events (event_type, user_id, payload)
    VALUES ('DocumentJobEnqueued', p_uploaded_by, jsonb_build_object('intake_job_id', v_job_id, 'source', p_source));

    RETURN v_job_id;
END;
$$;

COMMENT ON FUNCTION public.enqueue_intake_job IS
    'Atomska Upload Transaction (Faza 0) — job + audit_log + outbox event u jednoj transakciji. Isti obrazac kao deduct_credit()/deduct_n_credits().';


-- ── claim_intake_job — SELECT FOR UPDATE SKIP LOCKED preko RPC ──────────────
-- PostgREST (Supabase klijentska biblioteka) ne izlaže row-level lock
-- semantiku direktno — otuda RPC. Vraća najstariji claimable red i odmah
-- ga prebacuje u sledeći status, atomski, bez race condition-a između dva
-- konkurentna workera.

CREATE OR REPLACE FUNCTION public.claim_intake_job(
    p_from_status TEXT,
    p_to_status   TEXT
) RETURNS SETOF public.intake_jobs
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.intake_jobs
    SET status = p_to_status
    WHERE id = (
        SELECT id FROM public.intake_jobs
        WHERE status = p_from_status
          AND (next_retry_at IS NULL OR next_retry_at <= now())
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;

COMMENT ON FUNCTION public.claim_intake_job IS
    'Worker claim, ADR-0002 — SELECT ... FOR UPDATE SKIP LOCKED, jedini bezbedan način da dva konkurentna workera ne obrade isti red dvaput.';

-- Oba RPC-a pozivaju samo backend workeri (service_role ključ) — isti obrazac
-- kao deduct_credit()/deduct_n_credits(). Nikad izloženo anon/authenticated.
REVOKE ALL ON FUNCTION public.enqueue_intake_job(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_intake_job(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.enqueue_intake_job(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_intake_job(TEXT, TEXT) TO service_role;
