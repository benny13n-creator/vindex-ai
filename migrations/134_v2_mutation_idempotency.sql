-- ============================================================================
-- Migration 134 -- Durable idempotency for V2 NG mutations
--
-- NS005 Closure Gate A2 (2026-10-09). Founder decision: DURABLE DATABASE
-- idempotency; in-memory rejected (gunicorn.conf.py allows WEB_CONCURRENCY
-- workers with max_requests recycling; deploys/crashes clear memory).
--
-- WHY (measured, docs/v2-recovery/NS005_OVERNIGHT_EVIDENCE.md, Gate A):
--   when the HTTP/2 edge loses the browser session AFTER the origin processed
--   a request, Chromium re-sends the same POST on a new session -- one click
--   reached the real uvicorn/api.py twice (/api/pitanje and notes). A
--   client-side "outcome unknown" does not prevent the second server effect.
--
-- CONTRACT (shared/idempotency.py):
--   * claim   = INSERT of (user_id, idempotency_key) in state IN_PROGRESS.
--               The PRIMARY KEY decides the single owner -- no SELECT-then-
--               INSERT, no process memory, valid across workers, instances
--               and restarts. A second INSERT of the same pair fails 23505.
--   * finish  = UPDATE ... WHERE state = 'IN_PROGRESS' AND owner_token = <own>
--               -- only the execution owner can mark COMPLETED.
--   * replay  = COMPLETED + same fingerprint -> stored status/body, route not run.
--   * reuse   = same key, different fingerprint -> 409, route not run.
--   * stale IN_PROGRESS is NEVER reclaimed: an effect may have committed before
--     the owner died. expires_at is a RETENTION boundary, not permission to
--     execute again.
--
-- WHY owner_token (not in the minimal field list): it is the only way the
-- database itself can enforce "only the owner completes" -- without it any
-- process holding the same (user_id, key) could overwrite the record.
--
-- WHY no FAILED/UNKNOWN state: every non-completion (exception, crash,
-- completion write failure) must behave exactly like IN_PROGRESS (fail-closed,
-- never re-executed). A separate state would add no behavior.
--
-- WHY no FK to auth.users: infrastructure rows with a 24 h retention; an FK
-- would couple account deletion (SEC-031 RESTRICT policy) to transient replay
-- records. user_id is written ONLY from the server-verified token subject.
--
-- STORED DATA: no request body (only SHA-256 fingerprint of method + path +
-- query + body), no Authorization header, no token. The response body is
-- stored ENCRYPTED (security/crypto.py::encrypt_field, AES-256-GCM,
-- FIELD_ENCRYPTION_KEY); an undecryptable record is never replayed and never
-- re-executed (503 IDEMPOTENCY_REPLAY_UNAVAILABLE).
--
-- ACCESS: internal infrastructure. RLS enabled with NO policies; explicit
-- REVOKE from PUBLIC/anon/authenticated/service_role (Supabase default
-- privileges would otherwise grant ALL to each); service_role then gets back
-- only SELECT/INSERT/UPDATE.
-- Additive only. No other schema object is touched.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.v2_mutation_idempotency (
    user_id                UUID        NOT NULL,
    idempotency_key        UUID        NOT NULL,
    method                 TEXT        NOT NULL CHECK (method IN ('POST', 'PATCH')),
    path                   TEXT        NOT NULL CHECK (char_length(path) BETWEEN 1 AND 512),
    request_fingerprint    TEXT        NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    state                  TEXT        NOT NULL DEFAULT 'IN_PROGRESS'
                                       CHECK (state IN ('IN_PROGRESS', 'COMPLETED')),
    owner_token            UUID        NOT NULL,
    status_code            INTEGER     CHECK (status_code BETWEEN 100 AND 599),
    response_content_type  TEXT        CHECK (response_content_type IS NULL OR char_length(response_content_type) <= 200),
    response_payload_enc   TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at           TIMESTAMPTZ,
    expires_at             TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '24 hours'),
    PRIMARY KEY (user_id, idempotency_key),
    CONSTRAINT v2_idem_state_consistent CHECK (
        (state = 'IN_PROGRESS' AND status_code IS NULL AND completed_at IS NULL AND response_payload_enc IS NULL)
        OR
        (state = 'COMPLETED'   AND status_code IS NOT NULL AND completed_at IS NOT NULL AND response_payload_enc IS NOT NULL)
    ),
    CONSTRAINT v2_idem_payload_encrypted CHECK (
        response_payload_enc IS NULL OR response_payload_enc LIKE 'enc\_v1:%'
    )
);

CREATE INDEX IF NOT EXISTS v2_mutation_idempotency_expires_idx
    ON public.v2_mutation_idempotency (expires_at);

ALTER TABLE public.v2_mutation_idempotency ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.v2_mutation_idempotency FROM PUBLIC;
REVOKE ALL ON TABLE public.v2_mutation_idempotency FROM anon;
REVOKE ALL ON TABLE public.v2_mutation_idempotency FROM authenticated;
-- Supabase default privileges also grant ALL (incl. DELETE/TRUNCATE) to service_role;
-- reset it to exactly what the application needs (no DELETE: records are never removed by the app).
REVOKE ALL ON TABLE public.v2_mutation_idempotency FROM service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.v2_mutation_idempotency TO service_role;

COMMENT ON TABLE public.v2_mutation_idempotency IS
    'NS005 Gate A2: durable idempotency for V2 NG mutations (shared/idempotency.py). '
    'Internal; service_role only. No request bodies or tokens; response encrypted (enc_v1).';
