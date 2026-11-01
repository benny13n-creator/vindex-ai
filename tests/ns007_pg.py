"""NS007 — PRAVI PostgreSQL za dokaze atomičnosti (nije lažna baza).

`VX_TEST_PG_DSN` (npr. `postgresql://vx@127.0.0.1:55432/postgres`) pokazuje na IZOLOVAN lokalni klaster. Za svaki
test pravi se sveža baza sa minimalnim Supabase okruženjem (šema `auth`, `auth.uid()` iz podešavanja sesije, uloge
`anon` / `authenticated` / `service_role` sa BYPASSRLS kao na Supabase-u, minimalni `predmeti` i
`agent_recommendations`), pa se primenjuje migracija 136 TAČNO kako je u repou. Bez DSN-a testovi se preskaču.

CI (`.github/workflows/tests.yml`) podiže izolovan klaster kroz `scripts/test_db.py` i postavlja `VINDEX_PG_TEST_DSN`
(isti naziv kao `tests/ns4f_pg.py`); ranije se ovde čitao samo `VX_TEST_PG_DSN`, pa su se svi PG testovi ovog
pomoćnika u CI-ju preskakali. Sada: `VX_TEST_PG_DSN`, inače `VINDEX_PG_TEST_DSN`. DSN mora biti loopback, a ako je
podešen a baza nedostupna, to je PAD (ne preskok) — preskok sme samo kad DSN nije podešen.
"""
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import pytest

DSN = os.getenv("VX_TEST_PG_DSN", "") or os.getenv("VINDEX_PG_TEST_DSN", "")
if DSN and (urlparse(DSN).hostname or "").lower() not in ("127.0.0.1", "localhost", "::1"):
    raise RuntimeError("PG DSN za ns007_pg mora biti lokalan izolovan klaster (loopback) — odbijeno")
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
    except Exception as e:
        # podešen DSN koji ne radi nije razlog za preskok; poruka bez DSN-a (tajne)
        raise RuntimeError(f"PG DSN za ns007_pg je podešen, ali baza nije dostupna ({type(e).__name__})") from None


zahteva_pg = pytest.mark.skipif(not dostupan(), reason="ni VX_TEST_PG_DSN ni VINDEX_PG_TEST_DSN nije podešen")


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
