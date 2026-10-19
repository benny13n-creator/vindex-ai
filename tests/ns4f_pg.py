# -*- coding: utf-8 -*-
"""NS4 završno zatvaranje — STVARNI PostgreSQL za dokaze transakcija, brava, dozvola i RLS-a.

Lažna baza (`tests/ns005_harness`) ne može da dokaže atomičnost, zaključavanje ni efektivne GRANT/RLS dozvole.
Ovaj modul pravi izolovanu bazu nalik Supabase-u i nad njom primenjuje PRAVE migracije iz `migrations/`:
  • uloge `anon`, `authenticated`, `service_role` (BYPASSRLS), `auth.uid()` iz `request.jwt.claim.sub`;
  • Supabase podrazumevana prava (ALTER DEFAULT PRIVILEGES … TO anon, authenticated, service_role) — isto
    stanje koje je produkcija pokazala 2026-10-19 (anon SELECT → 200 [] na svim tabelama memorije);
  • minimalne osnovne tabele (`predmeti`, `klijenti`, `kancelarije`, `kancelarija_clanovi`, `predmet_dokumenti`)
    sa tipovima kolona iz produkcione šeme (OpenAPI, samo čitanje).

Pokretanje: `VINDEX_PG_TEST_DSN=postgresql://postgres@127.0.0.1:54329/postgres` (administratorski DSN
izolovanog klastera). Bez promenljive se testovi preskaču — NIKAD se ne povezuju na produkciju: DSN mora biti
lokalan (127.0.0.1/localhost), inače se odbija.
"""
from __future__ import annotations

import os
import pathlib
import uuid
from urllib.parse import urlparse

import pytest

KOREN = pathlib.Path(__file__).resolve().parent.parent
MIGRACIJE_OSNOVA = ["037_learning_loop.sql", "038_deep_learning.sql", "045_firm_intelligence.sql",
                    "046_firm_memory.sql", "047_trust_graph_workflow.sql",
                    "059_workflow_solo_i_sistemski_predlosci.sql", "088_staging_memory.sql"]
MIGRACIJE_NS4 = ["138_ns4_memorija_bez_direktnog_pristupa.sql", "139_ns4_atomski_ishod_predmeta.sql",
                 "140_ns4_oporavak_promocije_nacrta.sql"]

SUPABASE_STUB = r"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
  $f$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $f$;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
  $f$ SELECT nullif(current_setting('request.jwt.claim.role', true), '') $f$;
GRANT USAGE ON SCHEMA auth, public TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA auth TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;

CREATE TABLE public.kancelarije (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), admin_uid text, naziv text,
  created_at timestamptz DEFAULT now());
CREATE TABLE public.kancelarija_clanovi (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kancelarija_id uuid,
  user_id text, email text, uloga text, status text);
CREATE TABLE public.predmeti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, naziv text,
  tip text DEFAULT 'opsti', status text DEFAULT 'aktivan', opis text, created_at timestamptz DEFAULT now());
CREATE TABLE public.billing_entries (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid,
  iznos_rsd numeric, sati numeric, obracunato boolean, created_at timestamptz DEFAULT now());
CREATE TABLE public.klijenti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id text, ime text,
  prezime text, firma text, deleted_at timestamptz, aktivan boolean NOT NULL DEFAULT true);
CREATE TABLE public.predmet_dokumenti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid,
  user_id uuid, naziv_fajla text, storage_path text, pinecone_namespace text, status text DEFAULT 'na_cekanju',
  velicina_kb integer, redni_broj integer, tekst_sadrzaj text, tip_dokaza text, created_at timestamptz DEFAULT now());
CREATE UNIQUE INDEX predmet_dokumenti_predmet_redni_unique ON public.predmet_dokumenti (predmet_id, redni_broj);
"""


def dsn_admin() -> str | None:
    dsn = os.environ.get("VINDEX_PG_TEST_DSN")
    if not dsn:
        return None
    host = (urlparse(dsn).hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("VINDEX_PG_TEST_DSN mora biti lokalan izolovan klaster — odbijeno: " + host)
    return dsn


def _psycopg():
    try:
        import psycopg  # noqa: F401
        return psycopg
    except Exception:  # pragma: no cover
        return None


def potreban_pg():
    """Preskače test ako nema izolovanog PostgreSQL-a (lokalni dokaz, ne CI — NS4 izveštaj §7)."""
    if not dsn_admin() or not _psycopg():
        pytest.skip("Nema VINDEX_PG_TEST_DSN (izolovan lokalni PostgreSQL) — dokaz se izvodi lokalno.")


def _migracija(ime: str) -> str:
    return (KOREN / "migrations" / ime).read_text(encoding="utf-8")


def nova_baza(sa_ns4: bool = True) -> str:
    """Pravi svežu bazu sa stubom + osnovnim migracijama (+ NS4 migracijama). Vraća DSN te baze."""
    psycopg = _psycopg()
    admin = dsn_admin()
    ime = "ns4f_" + uuid.uuid4().hex[:12]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{ime}"')
    u = urlparse(admin)
    dsn = u._replace(path="/" + ime).geturl()
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(SUPABASE_STUB)
        for m in MIGRACIJE_OSNOVA + (MIGRACIJE_NS4 if sa_ns4 else []):
            c.execute(_migracija(m))
    return dsn


def primeni(dsn: str, ime_migracije: str) -> None:
    with _psycopg().connect(dsn, autocommit=True) as c:
        c.execute(_migracija(ime_migracije))


def obrisi_bazu(dsn: str) -> None:
    psycopg = _psycopg()
    ime = urlparse(dsn).path.lstrip("/")
    with psycopg.connect(dsn_admin(), autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{ime}" WITH (FORCE)')


def kao(conn, uloga: str, sub: str | None = None):
    """Postavlja ulogu i JWT `sub` za tekuću transakciju (kao PostgREST)."""
    conn.execute(f"SET LOCAL ROLE {uloga}")
    conn.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (sub or "",))
    conn.execute("SELECT set_config('request.jwt.claim.role', %s, true)", (uloga,))
