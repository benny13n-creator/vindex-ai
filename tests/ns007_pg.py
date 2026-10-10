"""NS007 — PRAVI PostgreSQL za dokaze atomičnosti (nije lažna baza).

`VX_TEST_PG_DSN` (npr. `postgresql://vx@127.0.0.1:55432/postgres`) pokazuje na IZOLOVAN lokalni klaster. Za svaki
test pravi se sveža baza sa minimalnim Supabase okruženjem (šema `auth`, `auth.uid()` iz podešavanja sesije, uloge
`anon` / `authenticated` / `service_role` sa BYPASSRLS kao na Supabase-u, minimalni `predmeti` i
`agent_recommendations`), pa se primenjuje migracija 136 TAČNO kako je u repou. Bez DSN-a testovi se preskaču.
"""
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

DSN = os.getenv("VX_TEST_PG_DSN", "")
KOREN = Path(__file__).resolve().parent.parent

_OKRUZENJE = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
END $$;
GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;
CREATE TABLE public.predmeti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL, naziv text, status text DEFAULT 'aktivan');
CREATE TABLE public.agent_recommendations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL, predmet_id uuid);
GRANT SELECT ON public.predmeti, public.agent_recommendations TO service_role;
"""


def dostupan() -> bool:
    if not DSN:
        return False
    try:
        import psycopg
        with psycopg.connect(DSN, connect_timeout=3):
            return True
    except Exception:
        return False


zahteva_pg = pytest.mark.skipif(not dostupan(), reason="VX_TEST_PG_DSN nije podešen ili lokalni PostgreSQL nije dostupan")


def migracija(broj: str) -> str:
    putanja = next((KOREN / "migrations").glob(f"{broj}_*.sql"))
    return putanja.read_text(encoding="utf-8")


@contextmanager
def sveza_baza(*migracije: str):
    """Sveža baza + okruženje + navedene migracije; posle testa se baza briše."""
    import psycopg
    ime = "vx_" + uuid.uuid4().hex[:12]
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{ime}"')
    dsn = DSN.rsplit("/", 1)[0] + "/" + ime
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(_OKRUZENJE)
            for m in migracije:
                c.execute(migracija(m))
        yield dsn
    finally:
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{ime}" WITH (FORCE)')
