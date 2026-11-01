# -*- coding: utf-8 -*-
"""
Early Access, Faza A — rezervacija AI budžeta nad STVARNIM PostgreSQL-om.

`test_ai_cost_protection.py` dokazuje logiku brane uz lažnu bazu čija je atomičnost
brava u Pythonu. Ovaj fajl dokazuje da ista rezervacija (`shared/ai_budget.py` →
`UsageService.rezervisi_za_operaciju` → RPC) drži invarijantu i nad pravim SQL telima:
migracije 107 (`deduct_n_credits`) i 108 (`increment_feature_usage`) izvršavaju se
DOSLOVNO, a 20 niti rezerviše istovremeno, svaka svojom vezom.

Invarijanta:  uspešnih_rezervacija × cena + konačno_stanje == početno_stanje,
              konačno_stanje ≥ 0, i nijedna rezervacija preko dnevnog limita.

Pokretanje: VINDEX_TEST_PG_DSN ili throwaway klaster na 127.0.0.1:55432
(`python scripts/test_db.py up`). Bez servera se preskače — to je činjenica okruženja,
ne način da se zaobiđe pad.
"""
import os
import sys
import threading
import time
import types
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

psycopg = pytest.importorskip("psycopg", reason="psycopg nije instaliran")

REPO = Path(__file__).resolve().parent.parent


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


@pytest.fixture(scope="module")
def pg():
    ime = f"vindex_aibudzet_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_DSN, autocommit=True) as c:
        for uloga in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (uloga,)).fetchone():
                c.execute(f'CREATE ROLE "{uloga}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{ime}"')
    dsn = _DSN.replace("dbname=postgres", f"dbname={ime}")
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("""
                CREATE TABLE public.user_credits (
                  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                  user_id UUID NOT NULL UNIQUE,
                  credits_remaining INTEGER NOT NULL DEFAULT 15,
                  mesecno_korisceno INTEGER, mesec TEXT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
                CREATE TABLE public.feature_registry (feature_key text PRIMARY KEY);
                INSERT INTO public.feature_registry VALUES ('t_ai'), ('t_besplatno');
                CREATE TABLE public.feature_usage (
                  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  user_id uuid NOT NULL,
                  feature_key text NOT NULL REFERENCES public.feature_registry(feature_key),
                  dan date NOT NULL DEFAULT CURRENT_DATE,
                  mesec text NOT NULL,
                  broj_koriscenja integer NOT NULL DEFAULT 0,
                  krediti_potroseni numeric NOT NULL DEFAULT 0,
                  updated_at timestamptz NOT NULL DEFAULT now(),
                  UNIQUE (user_id, feature_key, dan));
            """)
            for m in ("107_beta_gate_credit_race_closure.sql", "108_atomic_usage_counters.sql"):
                c.execute((REPO / "migrations" / m).read_text(encoding="utf-8"))   # DOSLOVNO
        yield dsn
    finally:
        with psycopg.connect(_DSN, autocommit=True) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (ime,))
            c.execute(f'DROP DATABASE IF EXISTS "{ime}"')


class _Res:
    def __init__(self, data):
        self.data = data


class PgSupa:
    """Samo pozivi koje rezervacija stvarno pravi; svaki poziv svojom vezom (kao PostgREST)."""

    def __init__(self, dsn):
        self.dsn = dsn

    def rpc(self, ime, p):
        dsn = self.dsn

        def _ex():
            with psycopg.connect(dsn, autocommit=True) as c:
                if ime == "deduct_n_credits":
                    return _Res(c.execute("SELECT public.deduct_n_credits(%s, %s)", (p["p_user_id"], p["p_n"])).fetchone()[0])
                if ime == "refund_n_credits":
                    return _Res(c.execute("SELECT public.refund_n_credits(%s, %s)", (p["p_user_id"], p["p_n"])).fetchone()[0])
                if ime == "increment_monthly_usage":
                    return _Res(c.execute("SELECT public.increment_monthly_usage(%s, %s)", (p["p_user_id"], p["p_mesec"])).fetchone()[0])
                if ime == "increment_feature_usage":
                    return _Res(c.execute(
                        "SELECT public.increment_feature_usage(%s, %s, %s, %s, %s, %s)",
                        (p["p_user_id"], p["p_feature"], p["p_dan"], p["p_mesec"], p["p_credits"], p["p_dnevni_limit"]),
                    ).fetchone()[0])
                raise AssertionError(f"neočekivan RPC {ime}")
        return types.SimpleNamespace(execute=_ex)

    def table(self, ime):
        dsn, f = self.dsn, {}

        class _Q:
            def select(self, *_a, **_k):
                return self

            def eq(self, k, v):
                f[k] = v
                return self

            def __getattr__(self, _n):
                return lambda *a, **k: self

            def execute(self):
                if ime == "user_credits":
                    with psycopg.connect(dsn, autocommit=True) as c:
                        r = c.execute("SELECT credits_remaining FROM public.user_credits WHERE user_id = %s",
                                      (f["user_id"],)).fetchone()
                    return _Res([{"credits_remaining": r[0]}] if r else [])
                if ime == "feature_usage":
                    with psycopg.connect(dsn, autocommit=True) as c:
                        r = c.execute("SELECT broj_koriscenja FROM public.feature_usage WHERE user_id=%s AND feature_key=%s",
                                      (f["user_id"], f["feature_key"])).fetchall()
                    return _Res([{"broj_koriscenja": x[0]} for x in r] if "dan" not in f else
                                ({"broj_koriscenja": r[0][0]} if r else None))
                return _Res([{}])
        return _Q()


@pytest.fixture
def okruzenje(pg, monkeypatch):
    from shared import deps, feature_registry
    from shared import usage as usage_mod
    supa = PgSupa(pg)
    monkeypatch.setattr(deps, "_get_supa", lambda: supa)
    monkeypatch.setattr(usage_mod, "_get_supa", lambda: supa)
    baza = {"aktivno": True, "status": "ACTIVE", "dnevni_limit": None, "mesecni_limit": None,
            "cooldown_seconds": None, "credit_multiplier": 1}
    monkeypatch.setattr(feature_registry, "_CACHE", {
        "t_ai": {**baza, "feature_key": "t_ai", "krediti": 2},
        "t_besplatno": {**baza, "feature_key": "t_besplatno", "krediti": 0, "dnevni_limit": 3},
    })
    monkeypatch.setattr(feature_registry, "_CACHE_LOADED_AT", time.monotonic() + 10 ** 9)
    return pg


def _korisnik(dsn, stanje):
    uid = str(uuid.uuid4())
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s, %s)", (uid, stanje))
    return uid


def _stanje(dsn, uid):
    with psycopg.connect(dsn, autocommit=True) as c:
        return c.execute("SELECT credits_remaining FROM public.user_credits WHERE user_id = %s", (uid,)).fetchone()[0]


def _trka(uid, feature, n=20):
    from shared import ai_budget
    uspeh, odbijeno, kodovi = [], [], []
    start = threading.Barrier(n)

    def _nit():
        op = ai_budget.Operacija(user_id=uid, email=f"{uid}@vindex.test", feature=feature)
        start.wait()
        try:
            ai_budget._osiguraj_rezervaciju(op)
            uspeh.append(op.hold)
        except ai_budget.AIBudzetOdbijen as e:
            odbijeno.append(e)
            kodovi.append(e.kod)

    niti = [threading.Thread(target=_nit) for _ in range(n)]
    for t in niti:
        t.start()
    for t in niti:
        t.join()
    return uspeh, odbijeno, kodovi


def test_20_paralelnih_rezervacija_nad_stvarnim_sql(okruzenje):
    uid = _korisnik(okruzenje, 10)
    uspeh, odbijeno, kodovi = _trka(uid, "t_ai")
    konacno = _stanje(okruzenje, uid)
    assert len(uspeh) == 5, (len(uspeh), kodovi)
    assert len(odbijeno) == 15 and set(kodovi) == {"NO_CREDITS"}
    assert konacno == 0
    assert sum(uspeh) + konacno == 10


def test_dnevni_limit_besplatne_funkcije_nad_stvarnim_sql(okruzenje):
    uid = _korisnik(okruzenje, 0)
    uspeh, odbijeno, kodovi = _trka(uid, "t_besplatno")
    assert len(uspeh) == 3, (len(uspeh), kodovi)
    assert set(kodovi) == {"DAILY_LIMIT"}
    with psycopg.connect(okruzenje, autocommit=True) as c:
        broj = c.execute("SELECT broj_koriscenja FROM public.feature_usage WHERE user_id = %s", (uid,)).fetchone()[0]
    assert broj == 3, "brojač ne sme preći limit ni pod trkom"
