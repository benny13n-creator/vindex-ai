-- ============================================================================
-- Vindex AI — Migracija 073: Smart Intake Phase 0 — Foundations
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 072.
--
-- POPRAVKA (posle prvog pokretanja): CREATE TABLE/CREATE OR REPLACE FUNCTION
-- su idempotentni, ali CREATE POLICY nije (Postgres nema CREATE POLICY IF
-- NOT EXISTS) — svaki DROP POLICY IF EXISTS ispred CREATE POLICY ispod je
-- zato dodat da ceo fajl bude bezbedan za ponovno pokretanje od početka do
-- kraja. Ovo je stvarni uzrok zašto je prvo pokretanje stalo na pola (na
-- prvoj CREATE POLICY liniji pri ponovnom pokušaju), ne PostgREST cache.
--
-- Kontekst: Faza 0 implementacije Smart Intake Engine-a (docs/adr/, dizajn
-- zamrznut kao bazelin — ne menjati bez formalnog ADR-a). Cilj Faze 0:
-- učiniti upload pouzdanim i trajnim, BEZ ikakve promene AI ponašanja —
-- klasifikacija/ekstrakcija/case-matching dolaze tek u Fazi 1.
--
-- Founder je eksplicitno zahtevao da Faza 0 NE bude "infrastruktura koja
-- postoji ali se ne koristi" — dodato u ovoj verziji migracije (pre nego što
-- je ijednom pokrenuta): claimed_at + reaper podrška (worker koji padne
-- usred obrade ne sme trajno zaglaviti posao), atomske complete/fail RPC
-- funkcije (isti obrazac kao enqueue_intake_job), worker heartbeat tabela
-- i dva metrics view-a za operativnu vidljivost pre nego što se Faza 0
-- proglasi završenom.
--
-- Tabele:
--   events                    — durable outbox za event bus (ADR-0001).
--   intake_jobs                — Postgres-backed job queue (ADR-0002).
--   intake_audit_log            — append-only, mirroring feature_registry_audit.
--   intake_worker_heartbeat     — po worker_id, za health endpoint.
--
-- View-ovi (derive, ne store — isti princip kao Pricing Matrix):
--   intake_queue_metrics, events_outbox_metrics.
--
-- RPC-ovi (svi atomski, isti obrazac kao deduct_credit()):
--   enqueue_intake_job   — job + audit + outbox event.
--   claim_intake_job     — SELECT FOR UPDATE SKIP LOCKED, postavlja claimed_at.
--   complete_intake_job  — status=completed + audit + outbox event.
--   fail_intake_job       — retry (backoff) ili dead-letter (max_attempts),
--                           dead-letter grana piše i audit i outbox event.
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
DROP POLICY IF EXISTS "events_service_role" ON public.events;
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
    claimed_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ
);

-- CREATE TABLE IF NOT EXISTS iznad ne dodaje kolone na tabelu koja već
-- postoji (npr. iz ranijeg delimičnog pokretanja pre nego što je claimed_at
-- dodat) — otuda eksplicitan ALTER TABLE, isti obrazac kao migracija 072
-- (business_groups.tagline). Ovo je stvarni uzrok greške "column claimed_at
-- does not exist" pri prethodnom pokušaju.
ALTER TABLE public.intake_jobs ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;

COMMENT ON TABLE public.intake_jobs IS
    'Postgres-backed job queue (ADR-0002) — status JE queue-a. Workeri claim-uju preko claim_intake_job() RPC, nikad direktnim UPDATE-om (race condition bez FOR UPDATE SKIP LOCKED, koji PostgREST ne izlaže).';
COMMENT ON COLUMN public.intake_jobs.idempotency_key IS
    'Klijentski retry-after-timeout zaštita. content_sha256 je zaseban dedup mehanizam za identičan sadržaj fajla.';
COMMENT ON COLUMN public.intake_jobs.claimed_at IS
    'Postavlja claim_intake_job() RPC. Reaper (shared/intake_queue.py::reap_stale_jobs) traži redove u ne-terminalnom statusu čiji je claimed_at stariji od praga — worker koji je pao usred obrade ostavlja posao ovde, nikad trajno zaglavljen.';

CREATE INDEX IF NOT EXISTS idx_intake_jobs_claimable
    ON public.intake_jobs(status, next_retry_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_intake_jobs_idempotency
    ON public.intake_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;

ALTER TABLE public.intake_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "intake_jobs_service_role" ON public.intake_jobs;
CREATE POLICY "intake_jobs_service_role" ON public.intake_jobs
    FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "intake_jobs_owner_read" ON public.intake_jobs;
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
DROP POLICY IF EXISTS "intake_audit_log_service_role" ON public.intake_audit_log;
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
    SET status = p_to_status, claimed_at = now()
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

-- ── complete_intake_job — atomsko uspešno okončanje ─────────────────────────
-- status=completed + audit + outbox event u jednoj transakciji. Idempotentna
-- po konstrukciji — pozivanje nad već completed poslom samo ponovo piše iste
-- vrednosti, nema efekta ni greške (bitno za "effectively-once" garanciju
-- kada worker posle restarta zavrsi posao koji je delimicno vec obradio).

CREATE OR REPLACE FUNCTION public.complete_intake_job(
    p_job_id UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.intake_jobs
    SET status = 'completed', completed_at = now()
    WHERE id = p_job_id;

    INSERT INTO public.intake_audit_log (intake_job_id, event_type, actor, after)
    VALUES (p_job_id, 'job_completed', 'system', jsonb_build_object('status', 'completed'));

    INSERT INTO public.events (event_type, payload)
    VALUES ('DocumentJobCompleted', jsonb_build_object('intake_job_id', p_job_id));
END;
$$;

COMMENT ON FUNCTION public.complete_intake_job IS
    'Atomsko uspešno okončanje (Faza 0) — status + audit + outbox event u jednoj transakciji. Idempotentna: dvostruki poziv nad istim job_id ne pravi duplirane efekte osim drugog audit/outbox reda (prihvatljivo — audit log je istorijski, ne stanje).';


-- ── fail_intake_job — atomski retry (backoff) ili dead-letter ───────────────
-- Ako je attempts+1 < max_attempts: nazad na 'received' sa next_retry_at
-- (eksponencijalni backoff, računa se u Python-u i prosleđuje ovde radi
-- jedne definicije formule — shared/intake_queue.py). Ako je dostignut
-- max_attempts: status='failed' (dead-letter) + audit + outbox event, tako
-- da druge komponente mogu da reaguju na trajni neuspeh bez pollovanja.

CREATE OR REPLACE FUNCTION public.fail_intake_job(
    p_job_id        UUID,
    p_error         TEXT,
    p_new_attempts  INTEGER,
    p_max_attempts  INTEGER,
    p_next_retry_at TIMESTAMPTZ
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF p_new_attempts >= p_max_attempts THEN
        UPDATE public.intake_jobs
        SET status = 'failed', attempts = p_new_attempts, last_error = p_error
        WHERE id = p_job_id;

        INSERT INTO public.intake_audit_log (intake_job_id, event_type, actor, after)
        VALUES (p_job_id, 'job_dead_lettered', 'system', jsonb_build_object('attempts', p_new_attempts, 'error', p_error));

        INSERT INTO public.events (event_type, payload)
        VALUES ('DocumentJobFailed', jsonb_build_object('intake_job_id', p_job_id, 'attempts', p_new_attempts, 'error', p_error));
    ELSE
        UPDATE public.intake_jobs
        SET status = 'received', attempts = p_new_attempts, next_retry_at = p_next_retry_at,
            last_error = p_error, claimed_at = NULL
        WHERE id = p_job_id;

        INSERT INTO public.intake_audit_log (intake_job_id, event_type, actor, after)
        VALUES (p_job_id, 'job_retry_scheduled', 'system',
                jsonb_build_object('attempts', p_new_attempts, 'next_retry_at', p_next_retry_at, 'error', p_error));
    END IF;
END;
$$;

COMMENT ON FUNCTION public.fail_intake_job IS
    'Atomski retry/dead-letter (Faza 0) — status + audit (+ outbox event samo na dead-letter, retry nije terminalno stanje). claimed_at se resetuje na NULL pri retry-u da reaper ne pokusa da ga ponovo reap-uje pre next_retry_at.';


-- ── intake_worker_heartbeat — po worker_id, za health endpoint ──────────────

CREATE TABLE IF NOT EXISTS public.intake_worker_heartbeat (
    worker_id          TEXT PRIMARY KEY,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    jobs_processed     BIGINT NOT NULL DEFAULT 0,
    jobs_failed        BIGINT NOT NULL DEFAULT 0
);

COMMENT ON TABLE public.intake_worker_heartbeat IS
    'Jedan red po worker procesu (worker_id = hostname:pid ili UUID pri startu). Worker upisuje/osvežava svoj red na svaki tick. Health endpoint (GET /api/admin/intake/health) čita ovo da pokaže da li je bar jedan worker živ.';

ALTER TABLE public.intake_worker_heartbeat ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "intake_worker_heartbeat_service_role" ON public.intake_worker_heartbeat;
CREATE POLICY "intake_worker_heartbeat_service_role" ON public.intake_worker_heartbeat
    FOR ALL USING (auth.role() = 'service_role');


-- ── Metrics view-ovi — IZVEDENI, nikad zaseban stored red (isti princip kao
-- Pricing Matrix) ────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.intake_queue_metrics AS
SELECT
    count(*) FILTER (WHERE status NOT IN ('completed', 'failed'))            AS queue_depth,
    min(created_at) FILTER (WHERE status NOT IN ('completed', 'failed'))     AS oldest_pending_at,
    count(*) FILTER (WHERE status = 'failed')                                AS failed_count,
    count(*) FILTER (WHERE attempts > 0 AND status NOT IN ('completed', 'failed')) AS retrying_count,
    count(*) FILTER (WHERE status = 'awaiting_review')                       AS awaiting_review_count,
    avg(extract(epoch FROM (completed_at - created_at))) FILTER (WHERE status = 'completed') AS avg_processing_latency_s
FROM public.intake_jobs;

COMMENT ON VIEW public.intake_queue_metrics IS
    'Operativna vidljivost (Faza 0 Definition of Done) — queue depth, najstariji pending, failed/retrying brojevi, prosečna latencija obrade. Izvedeno u letu, nikad zaseban stored red.';

CREATE OR REPLACE VIEW public.events_outbox_metrics AS
SELECT
    count(*) FILTER (WHERE dispatched_at IS NULL)                            AS undispatched_backlog,
    min(created_at) FILTER (WHERE dispatched_at IS NULL)                     AS oldest_undispatched_at,
    avg(extract(epoch FROM (dispatched_at - created_at))) FILTER (WHERE dispatched_at IS NOT NULL) AS avg_dispatch_latency_s,
    count(*) FILTER (WHERE dispatch_attempts > 0 AND dispatched_at IS NULL)  AS events_with_errors
FROM public.events;

COMMENT ON VIEW public.events_outbox_metrics IS
    'Outbox backlog i dispatch latencija — ADR-0001 postoji specifično da spreči gubitak događaja; ovaj view je kako se to proverava u produkciji, ne samo veruje na reč.';


-- Svi RPC-ovi pozivaju samo backend workeri (service_role ključ) — isti
-- obrazac kao deduct_credit()/deduct_n_credits(). Nikad izloženo anon/authenticated.
REVOKE ALL ON FUNCTION public.enqueue_intake_job(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_intake_job(TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.complete_intake_job(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fail_intake_job(UUID, TEXT, INTEGER, INTEGER, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.enqueue_intake_job(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_intake_job(TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_intake_job(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.fail_intake_job(UUID, TEXT, INTEGER, INTEGER, TIMESTAMPTZ) TO service_role;


-- ── Storage bucket za intake dokumenta ───────────────────────────────────────
-- Isti obrazac kao klijent-dokumenti (Trezor) — enkriptovano pre upload-a
-- (routers/smart_intake.py), bucket sam po sebi NIJE public. Ako je bucket
-- već ručno kreiran u Supabase Dashboard-u, ovaj insert je no-op.

INSERT INTO storage.buckets (id, name, public)
VALUES ('intake-dokumenti', 'intake-dokumenti', false)
ON CONFLICT (id) DO NOTHING;
