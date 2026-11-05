# -*- coding: utf-8 -*-
"""
Migracija 146 (`ai_osnovna_obrada`) nad STVARNIM PostgreSQL-om.

Šema `feature_registry` se gradi DOSLOVNO iz migracija koje je kreiraju i menjaju
(064, 065, 069, 070, 071, 128), uz minimalne Supabase stub-ove (`auth`, uloge).
Zatim se 146 izvršava doslovno, kako bi je operater pokrenuo u SQL Editor-u.

Ugovor (odluka osnivača 2026-11-05: dnevni_limit = 100):
  - prvo izvršenje pravi tačno jedan red: 0 kredita, dnevni limit 100, aktivan;
  - ponovno izvršenje ne menja ništa (idempotentno, bez duplikata);
  - nijedan drugi red registra se ne menja;
  - postojeći red `ai_osnovna_obrada` se NE prepisuje (ON CONFLICT DO NOTHING);
  - greška usred migracije ne ostavlja delimično stanje.

Pokretanje: VINDEX_TEST_PG_DSN ili throwaway klaster (`python scripts/test_db.py up`).
Bez servera se preskače — to je činjenica okruženja, ne dokaz.
"""
import os
import re
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg", reason="psycopg nije instaliran")

REPO = Path(__file__).resolve().parent.parent
M146 = REPO / "migrations" / "146_ai_osnovna_obrada.sql"
LANAC = (
    "064_feature_registry.sql",
    "065_feature_registry_v2.sql",
    "069_feature_registry_credit_multiplier.sql",
    "070_feature_registry_feature_type.sql",
    "071_business_groups.sql",
    "128_rollout_entitlement.sql",
)


def _server():
    for dsn in [os.getenv("VINDEX_TEST_PG_DSN") or "", "host=127.0.0.1 port=55432 user=postgres dbname=postgres"]:
        if not dsn:
            continue
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return dsn
        except Exception:
            continue
    return None


_DSN = _server()
pytestmark = pytest.mark.skipif(_DSN is None, reason="nema PostgreSQL test servera ($VINDEX_TEST_PG_DSN / 55432)")


@pytest.fixture
def db():
    ime = f"vindex_m146_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_DSN, autocommit=True) as c:
        for uloga in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (uloga,)).fetchone():
                c.execute(f'CREATE ROLE "{uloga}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{ime}"')
    veza = psycopg.connect(_DSN.replace("dbname=postgres", f"dbname={ime}"), autocommit=True)
    try:
        veza.execute("""
            CREATE SCHEMA auth;
            CREATE TABLE auth.users (id uuid PRIMARY KEY);
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS 'SELECT NULL::uuid';
            CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql AS 'SELECT NULL::text';
            CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql AS 'SELECT NULL::jsonb';
            CREATE TABLE public.profiles (id uuid PRIMARY KEY, subscription_type text, email text,
                                          credits_remaining int DEFAULT 0);
        """)
        for m in LANAC:
            veza.execute((REPO / "migrations" / m).read_text(encoding="utf-8"))   # DOSLOVNO
        yield veza
    finally:
        veza.close()
        with psycopg.connect(_DSN, autocommit=True) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (ime,))
            c.execute(f'DROP DATABASE IF EXISTS "{ime}"')


def _registar(veza) -> dict:
    return {r[0]: r[1] for r in veza.execute(
        "SELECT feature_key, to_jsonb(f) FROM public.feature_registry f ORDER BY 1").fetchall()}


def _primeni_146(veza) -> None:
    veza.execute(M146.read_text(encoding="utf-8"))


def test_prvo_izvrsenje_pravi_jedan_red_sa_odobrenim_limitom(db):
    pre = _registar(db)
    assert "ai_osnovna_obrada" not in pre and len(pre) > 0

    _primeni_146(db)

    posle = _registar(db)
    assert set(posle) - set(pre) == {"ai_osnovna_obrada"}
    red = posle["ai_osnovna_obrada"]
    assert red["krediti"] == 0
    assert red["dnevni_limit"] == 100
    assert red["mesecni_limit"] is None
    assert red["aktivno"] is True
    assert red["status"] == "ACTIVE"
    assert red["business_group_id"] is None          # ne ulazi u javnu matricu cena
    assert db.execute("SELECT count(*) FROM public.feature_registry "
                      "WHERE feature_key = 'ai_osnovna_obrada'").fetchone()[0] == 1


def test_ponovno_izvrsenje_je_idempotentno_i_ne_dira_druge_redove(db):
    pre = _registar(db)
    _primeni_146(db)
    prvo = _registar(db)
    _primeni_146(db)
    drugo = _registar(db)

    assert drugo == prvo
    assert {k: v for k, v in prvo.items() if k != "ai_osnovna_obrada"} == pre


def test_postojeci_red_se_ne_prepisuje(db):
    db.execute("""
        INSERT INTO public.feature_registry (feature_key, naziv, kategorija, krediti, dnevni_limit, updated_by)
        VALUES ('ai_osnovna_obrada', 'rucno', 'ai_osnovno', 0, 300, 'operater')
    """)
    pre = _registar(db)

    _primeni_146(db)

    assert _registar(db) == pre                        # 300 ostaje; provera iz migracije to otkriva
    assert pre["ai_osnovna_obrada"]["dnevni_limit"] == 300


def test_greska_usred_migracije_ne_ostavlja_delimicno_stanje(db):
    pre = _registar(db)
    db.execute("""
        CREATE FUNCTION public._test_odbij() RETURNS trigger LANGUAGE plpgsql AS
          $$ BEGIN RAISE EXCEPTION 'simulirana greska'; END $$;
        CREATE TRIGGER _test_odbij BEFORE INSERT ON public.feature_registry
          FOR EACH ROW EXECUTE FUNCTION public._test_odbij();
    """)

    with pytest.raises(psycopg.errors.RaiseException):
        _primeni_146(db)
    db.execute("ROLLBACK")                             # operater posle greške: transakcija je prekinuta
    db.execute("DROP TRIGGER _test_odbij ON public.feature_registry")

    assert _registar(db) == pre


def test_upit_za_proveru_u_migraciji_ocekuje_100():
    tekst = M146.read_text(encoding="utf-8")
    assert re.search(r"Očekivano: 1 red, krediti 0, dnevni_limit 100\b", tekst)
    assert not re.search(r"dnevni_limit\s*=?\s*300", tekst)
