-- TEST-ONLY fixture for isolated Word-session PostgreSQL acceptance tests.
-- This is not a production migration and must never be applied to Supabase.

DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END
$roles$;

ALTER ROLE anon NOLOGIN;
ALTER ROLE authenticated NOLOGIN;
ALTER ROLE service_role NOLOGIN BYPASSRLS;

CREATE SCHEMA auth;
CREATE TABLE auth.users (
  id uuid PRIMARY KEY
);

CREATE TABLE public.word_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  token_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  last_dispatch_claimed_at timestamptz,
  CONSTRAINT word_sessions_user_fk
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT,
  CONSTRAINT word_sessions_token_hash_unique UNIQUE (token_hash),
  CONSTRAINT word_sessions_token_hash_sha256_check
    CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT word_sessions_expiry_check
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '1 hour')
);

CREATE INDEX word_sessions_user_id_idx ON public.word_sessions (user_id);
CREATE INDEX word_sessions_expires_at_idx ON public.word_sessions (expires_at);
CREATE INDEX word_sessions_active_user_expiry_idx
  ON public.word_sessions (user_id, expires_at)
  WHERE revoked_at IS NULL;

ALTER TABLE public.word_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.word_sessions FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.word_sessions TO service_role;

-- Match the reviewed PostgREST RPC contract. SECURITY INVOKER is intentional:
-- service_role has BYPASSRLS and is the only role granted EXECUTE.
CREATE FUNCTION public.claim_word_session_provider_attempt(
  p_session_id uuid,
  p_user_id uuid,
  p_token_hash text
)
RETURNS boolean
LANGUAGE sql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $claim$
  WITH claimed AS (
    UPDATE public.word_sessions
       SET last_dispatch_claimed_at = clock_timestamp()
     WHERE id = p_session_id
       AND user_id = p_user_id
       AND token_hash = p_token_hash
       AND revoked_at IS NULL
       AND expires_at > clock_timestamp()
    RETURNING 1
  )
  SELECT EXISTS (SELECT 1 FROM claimed)
$claim$;

REVOKE ALL ON FUNCTION public.claim_word_session_provider_attempt(uuid, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_word_session_provider_attempt(uuid, uuid, text)
  TO service_role;

CREATE TABLE public.profiles (
  id uuid PRIMARY KEY,
  email text NOT NULL,
  full_name text NOT NULL
);

CREATE TABLE public.korisnik_email_notif (
  user_id uuid PRIMARY KEY,
  aktivan boolean NOT NULL DEFAULT true
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.profiles TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.korisnik_email_notif TO service_role;
