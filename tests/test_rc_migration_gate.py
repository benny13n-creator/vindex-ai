# -*- coding: utf-8 -*-
"""
Release Candidate — DB / MIGRATION GATE za migracije 111 i 112.

ZAŠTO OVAJ FAJL POSTOJI PORED WAVE 9 TESTOVA
────────────────────────────────────────────
Wave 9 je svaku migraciju dokazao POJEDINAČNO i nad REKONSTRUISANOM šemom:

  • `tests/test_wave9_migration_111.py` izvršava 111 nad `feature_registry`
    tabelom koja je RUČNO PREPISANA iz migracija 064/065/069/070/071, useljena
    ručno napisanim `_SEED` redovima. To je namerna izolacija — ali znači da
    je dokazana migracija nad tabelom koju je napisao test, a ne nad tabelom
    koju prave migracije ovog repoa.

  • `tests/test_wave9_usage_provenance.py` migraciju 112 proverava kao TEKST
    (regex nad `.sql` fajlom) i nad LAŽNIM Supabase klijentom. Nijedan test do
    sada nije izvršio 112 nad pravim Postgresom.

  • `tests/test_wave9_billing_invariant.py` dokazuje knjigovodstvenu
    invarijantu nad bazom koja ima 107 + 108, ali NE i 111 + 112.

Ovaj fajl zatvara tačno te rupe i ništa više. Njegov jedini metod je:

    primeni PRAVE `.sql` fajlove sa diska, redom, nad svežim PostgreSQL-om,
    pa meri rezultat u bazi.

ŠTA JE OVDE „PRAVI LANAC"
─────────────────────────
Sve migracije repoa koje DDL-om ili podacima diraju `feature_registry` ili
`feature_usage_log`, izvršene redom kojim ih vlasnik pokreće:

    064 → 065 → 066 → 069 → 070 → 071 → 075 → 083 → (107, 108) → 111 → 112

Migracije 067/068/073 su izostavljene jer te dve tabele ne dodiruju uopšte
(provereno grepom: pominju ih samo u komentarima). 107 i 108 se dodaju jer bez
njih `UsageService.consume` nema `deduct_n_credits` ni `increment_feature_usage`,
pa se naplatna strana ne bi mogla meriti nad pravom bazom.

DVA LOKALNA ŠIMA, OBA IMENOVANA
  1. `auth.role()` / `auth.uid()` — šema `auth` postoji samo u Supabase-u, a
     RLS politike migracija 064/065 je zovu. Bez šima lanac ne bi mogao ni da
     se primeni lokalno. Ne utiče na semantiku: migracije se i na produkciji
     pokreću kao vlasnik u SQL Editor-u, gde RLS ne važi.
  2. `public.user_credits` — prava definicija (`supabase_setup.sql:53`) ima FK
     na `auth.users(id)`, tabelu koju lokalni klaster nema. Koristi se ista
     minimalna definicija koju već koriste `test_wave9_billing_invariant.py` i
     `test_beta_gate_credit_race_postgres.py`, da bi 107/108 imali nad čim da
     rade.

OTKRIVANJE SERVERA
──────────────────
Isti mehanizam kao ostali PG testovi (`$VINDEX_TEST_PG_DSN`, pa 127.0.0.1:55433,
pa 55432). Fallback na 5432 je NAMERNO izostavljen — to je trajni servis sa
stvarnim podacima, a ovaj fajl pravi i briše baze. Preskakanje je činjenica o
okruženju, nikad način da se izbegne tvrdnja koja pada.
"""
import asyncio
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
MIGRATION_111 = MIGRATIONS_DIR / "111_phantom_ai_charges.sql"
MIGRATION_112 = MIGRATIONS_DIR / "112_feature_usage_provenance.sql"
VERIFY_112 = REPO_ROOT / "scripts" / "verify_migration_112.py"

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg nije instaliran — dokaz nad pravom bazom preskočen"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Otkrivanje servera ──────────────────────────────────────────────────────

def _candidate_dsns():
    env = os.getenv("VINDEX_TEST_PG_DSN")
    if env:
        return [env]
    return [
        "host=127.0.0.1 port=55433 user=postgres dbname=postgres",
        "host=127.0.0.1 port=55432 user=postgres dbname=postgres",
        # 5432 se NE proba: na ovoj mašini je to trajan servis sa stvarnim
        # podacima, a ovaj fajl pravi i briše baze. Ako klasteri nisu podignuti:
        #     python scripts/test_db.py up
    ]


def _find_server():
    for dsn in _candidate_dsns():
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return dsn
        except Exception:
            continue
    return None


_SERVER_DSN = _find_server()

pytestmark = pytest.mark.skipif(
    _SERVER_DSN is None,
    reason=(
        "nema dostupnog PostgreSQL servera (probano $VINDEX_TEST_PG_DSN, "
        "127.0.0.1:55433, 127.0.0.1:55432) — RC DB gate preskočen. "
        "Podizanje: python scripts/test_db.py up"
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# Lanac migracija — imena fajlova, ništa prepisano iz njihovog sadržaja
# ═══════════════════════════════════════════════════════════════════════════

_LANAC_PRE_111 = [
    "064_feature_registry.sql",
    "065_feature_registry_v2.sql",
    "066_digital_twin_feature.sql",
    "069_feature_registry_credit_multiplier.sql",
    "070_feature_registry_feature_type.sql",
    "071_business_groups.sql",
    "075_remove_vindex_memory.sql",
    "083_copilot_ambient_feature.sql",
    "107_beta_gate_credit_race_closure.sql",
    "108_atomic_usage_counters.sql",
]

_AUTH_SIM = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE
    AS $$ SELECT 'service_role'::text $$;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE
    AS $$ SELECT NULL::uuid $$;
"""

# Prava definicija nosi FK na `auth.users(id)` — ista minimalna verzija koju
# već koriste postojeći PG testovi naplate.
_USER_CREDITS_DDL = """
CREATE TABLE public.user_credits (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL UNIQUE,
  credits_remaining INTEGER NOT NULL DEFAULT 15,
  mesecno_korisceno INTEGER DEFAULT 0,
  mesec             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _dsn_za(dbname: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(_SERVER_DSN)
    info["dbname"] = dbname
    target = psycopg.conninfo.make_conninfo(**info)
    assert dbname in target, "test baza ne sme biti admin baza"
    return target


def _drop(dbname: str) -> None:
    with psycopg.connect(_SERVER_DSN, autocommit=True) as c:
        c.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (dbname,),
        )
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')


@pytest.fixture(scope="module")
def sablon():
    """Baza sa CELIM lancem OSIM 111 i 112 — služi kao Postgres TEMPLATE.

    Gradi se jednom po modulu; svaki test dobija svežu kopiju. Time svaki test
    kreće od identičnog pre-111/pre-112 stanja, a lanac se ne izvršava po testu.
    """
    dbname = f"vindex_rc_tmpl_{uuid.uuid4().hex[:10]}"

    with psycopg.connect(_SERVER_DSN, autocommit=True) as c:
        # Uloge na koje se pozivaju GRANT/REVOKE naredbe migracija 107/108.
        for role in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{dbname}"')

    try:
        with psycopg.connect(_dsn_za(dbname), autocommit=True) as c:
            c.execute(_AUTH_SIM)
            c.execute(_USER_CREDITS_DDL)
            for ime in _LANAC_PRE_111:
                c.execute((MIGRATIONS_DIR / ime).read_text(encoding="utf-8"))
        # Konekcija MORA biti zatvorena — CREATE DATABASE ... TEMPLATE odbija
        # šablon na koji je neko povezan.
        yield dbname
    finally:
        _drop(dbname)


@pytest.fixture
def baza(sablon):
    """Sveža kopija šablona za jedan test. Stanje: sve OSIM 111 i 112."""
    dbname = f"vindex_rc_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(_SERVER_DSN, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{dbname}" TEMPLATE "{sablon}"')
    try:
        yield _dsn_za(dbname)
    finally:
        _drop(dbname)


def _primeni(dsn: str, putanja: Path) -> None:
    """Izvršava artefakt SA DISKA, doslovno. Nikad kopija SQL-a u testu."""
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(putanja.read_text(encoding="utf-8"))


@pytest.fixture
def baza_111_112(baza):
    """Kompletno migrirano stanje: ceo lanac + 111 + 112."""
    _primeni(baza, MIGRATION_111)
    _primeni(baza, MIGRATION_112)
    return baza


# ─── Pomoćni upiti ───────────────────────────────────────────────────────────

def _upit(dsn, sql, params=None):
    with psycopg.connect(dsn, autocommit=True) as c:
        cur = c.execute(sql, params)
        imena = [d.name for d in cur.description]
        return [dict(zip(imena, r)) for r in cur.fetchall()]


def _kolone_loga(dsn) -> dict:
    return {
        r["column_name"]: (r["data_type"], r["is_nullable"])
        for r in _upit(
            dsn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='feature_usage_log'",
        )
    }


def _indeksi_loga(dsn) -> dict:
    return {
        r["indexname"]: r["indexdef"]
        for r in _upit(
            dsn,
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname='public' AND tablename='feature_usage_log'",
        )
    }


def _komentari_loga(dsn) -> dict:
    return {
        r["kolona"]: r["komentar"]
        for r in _upit(
            dsn,
            """
            SELECT a.attname AS kolona,
                   col_description(a.attrelid, a.attnum) AS komentar
              FROM pg_attribute a
              JOIN pg_class c ON c.oid = a.attrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname='public' AND c.relname='feature_usage_log' AND a.attnum > 0
            """,
        )
    }


def _red_registryja(dsn, kljuc) -> dict:
    redovi = _upit(
        dsn,
        "SELECT feature_key, krediti, chargeable, ai_model, minimum_plan, "
        "cooldown_seconds, updated_by, credit_multiplier, feature_type "
        "FROM public.feature_registry WHERE feature_key = %s",
        (kljuc,),
    )
    return redovi[0] if redovi else None


def _ubaci_redove_loga(dsn, n: int) -> list:
    """Puni `feature_usage_log` redovima koji postoje PRE migracije 112."""
    ids = []
    with psycopg.connect(dsn, autocommit=True) as c:
        for i in range(n):
            r = c.execute(
                "INSERT INTO public.feature_usage_log "
                "(user_id, feature_key, krediti_potroseni, ai_model, latency_ms) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (str(uuid.uuid4()), "ai_pravna_pitanja", i, "gpt-4o", 100 + i),
            ).fetchone()
            ids.append(r[0])
    return ids


def _snimak_loga(dsn) -> list:
    return _upit(
        dsn,
        "SELECT id, user_id, feature_key, krediti_potroseni, ai_model, latency_ms, "
        "created_at FROM public.feature_usage_log ORDER BY id",
    )


# ═══════════════════════════════════════════════════════════════════════════
# G1 — ŠEMA ODGOVARA OČEKIVANOM STANJU
# ═══════════════════════════════════════════════════════════════════════════

def _kolone_koje_111_postavlja() -> set:
    """Izvlači imena kolona iz `SET ... =` klauzula migracije 111, sa diska."""
    sql = MIGRATION_111.read_text(encoding="utf-8")
    telo = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    kolone = set()
    for stmt in re.findall(r"\bSET\b(.*?)\bWHERE\b", telo, flags=re.S | re.I):
        for m in re.finditer(r"(\w+)\s*=", stmt):
            kolone.add(m.group(1).lower())
    return kolone


def test_G1_kolone_koje_111_dira_postoje_u_lancu_iz_repoa(baza):
    """Wave 9 ovo dokazuje nad RUČNO PREPISANOM tabelom. Ovde je ista tvrdnja
    nad tabelom koju prave same migracije repoa — jedina koja odgovara onome
    što vlasnik ima na produkciji."""
    stvarne = {
        r["column_name"]
        for r in _upit(
            baza,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='feature_registry'",
        )
    }
    nedostaju = _kolone_koje_111_postavlja() - stvarne
    assert not nedostaju, (
        f"migracija 111 postavlja kolone kojih u lancu 064→083 nema: {sorted(nedostaju)} "
        "— pokretanje na produkciji bi puklo sa 42703 (undefined_column)"
    )


# Očekivano stanje posle 111, nad seed-om koji prave PRAVE migracije
# (064 INSERT + 065 estimated_cost/priority + 069 multiplier + 070 feature_type
# + 071 business_group). Vrednosti van obima 111 su tu namerno: ako ih migracija
# usput promeni, test pada.
_OCEKIVANO_POSLE_111 = {
    "confidence_audit": {
        "krediti": 0, "chargeable": False, "ai_model": None,
        "minimum_plan": "basic", "cooldown_seconds": 5,
        "updated_by": "migration_111_phantom_ai_charges",
        "credit_multiplier": 1, "feature_type": "SUBSCRIPTION",
    },
    "conflict_check": {
        "krediti": 0, "chargeable": False, "ai_model": None,
        # 111 NE dira tarifnu kapiju ovog ključa — samo `confidence_audit`.
        "minimum_plan": "professional", "cooldown_seconds": None,
        "updated_by": "migration_111_phantom_ai_charges",
        "credit_multiplier": 1, "feature_type": "SUBSCRIPTION",
    },
    "da_wallet_risk_assessment": {
        "krediti": 0, "chargeable": False, "ai_model": None,
        # NULL = otključava se isključivo preko addon-a (064:37-38).
        "minimum_plan": None, "cooldown_seconds": None,
        "updated_by": "migration_111_phantom_ai_charges",
        "credit_multiplier": 1, "feature_type": "ADDON",
    },
}


@pytest.mark.parametrize("kljuc", sorted(_OCEKIVANO_POSLE_111))
def test_G1_tacno_ocekivano_stanje_tri_kljuca_posle_111(baza, kljuc):
    pre = _red_registryja(baza, kljuc)
    assert pre is not None, f"{kljuc}: lanac migracija uopšte nije napravio ovaj red"
    assert pre["krediti"] == 1 and pre["chargeable"] is True and pre["ai_model"], (
        f"{kljuc}: pre-111 stanje iz pravih migracija nije naplativo — "
        "tvrdnja ispod bi prolazila vakuumski"
    )

    _primeni(baza, MIGRATION_111)

    post = _red_registryja(baza, kljuc)
    for polje, ocekivano in _OCEKIVANO_POSLE_111[kljuc].items():
        stvarno = post[polje]
        if isinstance(ocekivano, bool) or ocekivano is None:
            assert stvarno is ocekivano, f"{kljuc}.{polje} = {stvarno!r}, očekivano {ocekivano!r}"
        else:
            assert stvarno == ocekivano, f"{kljuc}.{polje} = {stvarno!r}, očekivano {ocekivano!r}"


def test_G1_112_dodaje_obe_kolone_sa_tacnim_tipovima(baza):
    pre = _kolone_loga(baza)
    assert "predmet_id" not in pre and "correlation_id" not in pre, (
        "kolone postoje i PRE 112 — neka ranija migracija ih je već dodala, "
        "što bi značilo dva izvora iste šeme"
    )

    _primeni(baza, MIGRATION_112)

    post = _kolone_loga(baza)
    assert post["predmet_id"] == ("uuid", "YES"), (
        f"predmet_id = {post.get('predmet_id')}; mora biti uuid (jer je "
        "public.predmeti.id UUID) i NULLABLE"
    )
    assert post["correlation_id"] == ("text", "YES"), (
        f"correlation_id = {post.get('correlation_id')}; mora biti text i NULLABLE"
    )
    # Aditivnost: ni jedna kolona iz 065 nije nestala ni promenila tip.
    for ime, tip in pre.items():
        assert post[ime] == tip, f"112 je promenila postojeću kolonu {ime}: {tip} → {post.get(ime)}"


def test_G1_112_ne_gubi_postojece_redove(baza):
    """`ADD COLUMN` bez DEFAULT-a je metapodatkovna izmena — ali to tvrdi
    zaglavlje migracije, a ovde se meri."""
    _ubaci_redove_loga(baza, 7)
    pre = _snimak_loga(baza)
    assert len(pre) == 7

    _primeni(baza, MIGRATION_112)

    post = _snimak_loga(baza)
    assert post == pre, "postojeći redovi naplate su izmenjeni ili izgubljeni"

    nove = _upit(
        baza,
        "SELECT count(*) AS n FROM public.feature_usage_log "
        "WHERE predmet_id IS NULL AND correlation_id IS NULL",
    )
    assert nove[0]["n"] == 7, (
        "stari redovi moraju imati NULL u novim kolonama — NULL znači "
        "„nije zabeleženo\", nikad „predmet ne postoji\""
    )


def test_G1_112_indeksi_i_komentari_stvarno_postoje(baza):
    pre_idx = _indeksi_loga(baza)
    _primeni(baza, MIGRATION_112)
    post_idx = _indeksi_loga(baza)

    for ime, kolona in (
        ("feature_usage_log_correlation_idx", "correlation_id"),
        ("feature_usage_log_predmet_idx", "predmet_id"),
    ):
        assert ime in post_idx, f"indeks {ime} koji 112 deklariše ne postoji u bazi"
        definicija = post_idx[ime]
        assert kolona in definicija, f"{ime} ne pokriva kolonu {kolona}"
        assert "WHERE" in definicija.upper(), (
            f"{ime} nije parcijalan — indeksirali bi se i svi NULL redovi upisani pre 112"
        )

    # Indeksi iz 065 su netaknuti.
    for ime, definicija in pre_idx.items():
        assert post_idx.get(ime) == definicija, f"112 je promenila postojeći indeks {ime}"

    komentari = _komentari_loga(baza)
    for kolona in ("predmet_id", "correlation_id"):
        assert komentari.get(kolona), (
            f"{kolona}: COMMENT ON COLUMN iz migracije 112 nije primenjen — "
            "sledeći koji otvori tabelu nema nijedno objašnjenje zašto nema FK"
        )
    assert "FOREIGN KEY" in komentari["predmet_id"].upper(), (
        "komentar na predmet_id više ne objašnjava izostanak FK — to je jedina "
        "odbrana od budućeg „popravljanja\" koje bi brisalo istoriju naplate"
    )


# ═══════════════════════════════════════════════════════════════════════════
# G2 — IDEMPOTENTNOST MIGRACIJE 112
# ═══════════════════════════════════════════════════════════════════════════
# Idempotentnost migracije 111 već dokazuju
# `test_wave9_migration_111.py::test_ponovno_pokretanje_daje_identicno_stanje` i
# `::test_tri_uzastopna_pokretanja_ostaju_stabilna`. Ovde se NE ponavlja.
# Za 112 ekvivalent nije postojao — `ADD COLUMN IF NOT EXISTS` je bio tvrdnja
# iz zaglavlja, ne merenje.

def _semantski_snimak(dsn) -> tuple:
    return (_kolone_loga(dsn), _indeksi_loga(dsn), _komentari_loga(dsn))


def test_G2_112_tri_uzastopna_pokretanja_daju_identicnu_semu(baza):
    _primeni(baza, MIGRATION_112)
    referenca = _semantski_snimak(baza)

    for pokusaj in (2, 3):
        _primeni(baza, MIGRATION_112)  # ne sme baciti
        assert _semantski_snimak(baza) == referenca, (
            f"{pokusaj}. pokretanje migracije 112 je promenilo šemu — "
            "`ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` ne drže "
            "idempotentnost koju zaglavlje tvrdi"
        )


def test_G2_112_ponovno_pokretanje_ne_dira_podatke(baza):
    _ubaci_redove_loga(baza, 5)
    _primeni(baza, MIGRATION_112)

    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(
            "UPDATE public.feature_usage_log SET correlation_id = 'CID-RC', "
            "predmet_id = %s",
            (str(uuid.uuid4()),),
        )
    pre = _upit(
        baza,
        "SELECT id, krediti_potroseni, predmet_id, correlation_id "
        "FROM public.feature_usage_log ORDER BY id",
    )

    _primeni(baza, MIGRATION_112)

    post = _upit(
        baza,
        "SELECT id, krediti_potroseni, predmet_id, correlation_id "
        "FROM public.feature_usage_log ORDER BY id",
    )
    assert post == pre, "drugo pokretanje 112 je izmenilo podatke naplate"


def test_G2_111_i_112_u_oba_redosleda_daju_isto_stanje(baza, sablon):
    """Vlasnik ih pokreće ručno, jedan po jedan. Ako se redosled zameni,
    rezultat mora biti isti — migracije diraju različite tabele, ali to je
    tvrdnja koja se ne proverava sama od sebe."""
    _primeni(baza, MIGRATION_112)
    _primeni(baza, MIGRATION_111)
    obrnuto_registry = _upit(
        baza,
        "SELECT feature_key, krediti, chargeable, ai_model, minimum_plan, cooldown_seconds "
        "FROM public.feature_registry ORDER BY feature_key",
    )
    obrnuto_sema = _semantski_snimak(baza)

    druga = f"vindex_rc_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(_SERVER_DSN, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{druga}" TEMPLATE "{sablon}"')
    try:
        dsn2 = _dsn_za(druga)
        _primeni(dsn2, MIGRATION_111)
        _primeni(dsn2, MIGRATION_112)
        assert (
            _upit(
                dsn2,
                "SELECT feature_key, krediti, chargeable, ai_model, minimum_plan, "
                "cooldown_seconds FROM public.feature_registry ORDER BY feature_key",
            )
            == obrnuto_registry
        ), "redosled 111/112 utiče na sadržaj feature_registry"
        assert _semantski_snimak(dsn2) == obrnuto_sema, (
            "redosled 111/112 utiče na šemu feature_usage_log"
        )
    finally:
        _drop(druga)


# ═══════════════════════════════════════════════════════════════════════════
# Ožičavanje pravog `UsageService` na pravu bazu (G3 i G4)
# ═══════════════════════════════════════════════════════════════════════════
# Nema mokovane politike i nema mokovane naplate: `get_policy` čita PRAVI red
# iz `feature_registry` ove baze, naplata ide na PRAVU `deduct_n_credits`
# (107), brojač na PRAVU `increment_feature_usage` (108), telemetrija u PRAVU
# `feature_usage_log` tabelu (065 + 112).

class _Sim:
    """Minimalan stand-in za Supabase klijenta — podržava tačno ono što
    `UsageService.consume` stvarno koristi. Sve ostalo diže AssertionError
    umesto da tiho prođe."""

    _RPC = {
        "deduct_n_credits": "SELECT public.deduct_n_credits(%(p_user_id)s, %(p_n)s)",
        "refund_n_credits": "SELECT public.refund_n_credits(%(p_user_id)s, %(p_n)s)",
        "increment_monthly_usage": "SELECT public.increment_monthly_usage(%(p_user_id)s, %(p_mesec)s)",
        "increment_feature_usage": (
            "SELECT public.increment_feature_usage(%(p_user_id)s, %(p_feature)s, %(p_dan)s, "
            "%(p_mesec)s, %(p_credits)s, %(p_dnevni_limit)s)"
        ),
    }

    def __init__(self, dsn):
        self._dsn = dsn
        self.rpc_log = []

    def rpc(self, name, params):
        self.rpc_log.append(name)
        sql = self._RPC[name]
        dsn = self._dsn

        class _Call:
            def execute(self_inner):
                from types import SimpleNamespace
                with psycopg.connect(dsn, autocommit=True) as c:
                    return SimpleNamespace(data=c.execute(sql, params).fetchone()[0])

        return _Call()

    def table(self, name):
        assert name in ("feature_registry", "feature_dependencies",
                        "feature_usage", "feature_usage_log"), (
            f"consume() je dodirnuo tabelu {name!r} koju ovaj dokaz ne pokriva — "
            "dopuni šim umesto da tiho prođe"
        )
        return _Upit(self._dsn, name)


class _Upit:
    """PostgREST-oblik lanac: select/eq/maybe_single/insert/execute."""

    _FILTERI = {"user_id", "feature_key", "dan", "mesec"}

    def __init__(self, dsn, tabela):
        self._dsn = dsn
        self._tabela = tabela
        self._kolone = "*"
        self._filteri = []
        self._single = False
        self._insert = None

    def select(self, sta):
        self._kolone = sta
        return self

    def eq(self, kolona, vrednost):
        assert kolona in self._FILTERI, f"nepodržan filter {kolona!r}"
        self._filteri.append((kolona, vrednost))
        return self

    def maybe_single(self):
        self._single = True
        return self

    def insert(self, payload):
        self._insert = dict(payload)
        return self

    def execute(self):
        from types import SimpleNamespace
        if self._insert is not None:
            imena = list(self._insert)
            sql = (
                f"INSERT INTO public.{self._tabela} ({', '.join(imena)}) "
                f"VALUES ({', '.join(['%s'] * len(imena))})"
            )
            with psycopg.connect(self._dsn, autocommit=True) as c:
                c.execute(sql, [self._insert[k] for k in imena])
            return SimpleNamespace(data=[{}])

        where = " AND ".join(f"{k} = %s" for k, _ in self._filteri) or "true"
        sql = f"SELECT {self._kolone} FROM public.{self._tabela} WHERE {where}"
        with psycopg.connect(self._dsn, autocommit=True) as c:
            cur = c.execute(sql, [v for _, v in self._filteri])
            imena = [d.name for d in cur.description]
            redovi = []
            for r in cur.fetchall():
                d = dict(zip(imena, r))
                # `shared/feature_registry` očekuje brojeve, ne Decimal —
                # pravi Supabase klijent vraća JSON, pa je ovo isto ponašanje.
                for broj in ("krediti", "credit_multiplier", "estimated_cost_usd",
                             "krediti_potroseni"):
                    if d.get(broj) is not None:
                        d[broj] = float(d[broj])
                redovi.append(d)
        if self._single:
            return SimpleNamespace(data=redovi[0] if redovi else None)
        return SimpleNamespace(data=redovi)


def _bilans(dsn, uid):
    r = _upit(dsn, "SELECT credits_remaining FROM public.user_credits WHERE user_id=%s", (uid,))
    return r[0]["credits_remaining"] if r else None


def _napravi_korisnika(dsn, bilans: int) -> str:
    uid = str(uuid.uuid4())
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            "INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s,%s)",
            (uid, bilans),
        )
    return uid


@pytest.fixture
def naplata(monkeypatch):
    """Fabrika: `naplata(dsn)` ožičava `UsageService` na tu bazu.

    `_claim_cooldown_atomic` je zamenjen dozvoljavajućim beležnikom — njegova
    atomičnost je predmet drugih dokaza (`shared/usage.py` TOCTOU zatvaranje),
    a ovde bi samo unosila vremensku zavisnost u merenje naplate.
    """
    def _ozici(dsn):
        import shared.deps as deps
        import shared.feature_registry as fr
        import shared.usage as usage

        sim = _Sim(dsn)
        # Sva tri modula drže SOPSTVENU referencu na `_get_supa` (from-import u
        # vreme učitavanja) — patch nad jednim ne pokriva ostale.
        monkeypatch.setattr(deps, "_get_supa", lambda: sim)
        monkeypatch.setattr(fr, "_get_supa", lambda: sim)
        monkeypatch.setattr(usage, "_get_supa", lambda: sim)
        monkeypatch.setattr(usage, "_is_founder", lambda *a, **k: False)
        monkeypatch.setattr(deps, "_is_founder", lambda *a, **k: False)
        monkeypatch.setattr(usage, "_get_credits", lambda uid: _bilans(dsn, uid) or 0)

        cooldown_pozivi = []

        async def _claim(user_id, feature, cooldown):
            cooldown_pozivi.append((user_id, feature, cooldown))
            return True

        monkeypatch.setattr(usage, "_claim_cooldown_atomic", _claim)
        fr.invalidate()

        from types import SimpleNamespace
        return SimpleNamespace(dsn=dsn, sim=sim, cooldown_pozivi=cooldown_pozivi)

    yield _ozici

    import shared.feature_registry as fr
    fr.invalidate()


# ═══════════════════════════════════════════════════════════════════════════
# G3 — PHANTOM AI CHARGE NIJE MOGUĆ NAD BAZOM IZ PRAVOG LANCA
# ═══════════════════════════════════════════════════════════════════════════
# `test_wave9_migration_111.py` §R1.3 ovo već dokazuje nad ručno prepisanom
# tabelom i ručno napisanim seed-om. Ovde je isti zaključak nad cenama koje
# proizvode PRAVE migracije 064/065/069/070 — jedini seed koji odgovara
# produkciji. Baterija je namerno kratka (3 + 2 + 1 tvrdnja), bez ponavljanja
# cooldown/telemetrija/opterećenje testova iz Wave 9.

@pytest.mark.anyio
@pytest.mark.parametrize(
    "kljuc", ["confidence_audit", "conflict_check", "da_wallet_risk_assessment"]
)
async def test_G3_grupa_A_ne_oduzima_nijedan_kredit(baza_111_112, naplata, kljuc):
    import shared.usage as usage

    stack = naplata(baza_111_112)
    uid = _napravi_korisnika(baza_111_112, 15)

    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", kljuc)

    assert preostalo == 15
    assert _bilans(baza_111_112, uid) == 15, f"{kljuc}: kredit je i dalje naplaćen"
    assert "deduct_n_credits" not in stack.sim.rpc_log, (
        f"{kljuc}: consume() je pozvao naplatu — grana `if n_credits > 0:` je uzeta"
    )


@pytest.mark.anyio
async def test_G3_negativna_kontrola_bez_111_kredit_JESTE_naplacen(baza, naplata):
    """Bez ovoga bi tvrdnje iznad mogle prolaziti vakuumski (npr. da šim uopšte
    ne stiže do naplate). Ista baza, ista mašinerija, 111 NIJE pokrenuta."""
    import shared.usage as usage

    _primeni(baza, MIGRATION_112)  # samo 112, bez 111
    stack = naplata(baza)
    uid = _napravi_korisnika(baza, 15)

    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")

    assert preostalo == 14, "pre-111 lanac mora naplaćivati — inače dokaz iznad ne meri ništa"
    assert _bilans(baza, uid) == 14
    assert "deduct_n_credits" in stack.sim.rpc_log


@pytest.mark.anyio
@pytest.mark.parametrize("kljuc,cena", [("case_commander", 2), ("zastarelost_guardian", 1)])
async def test_G3_deljeni_kljucevi_I_DALJE_naplacuju(baza_111_112, naplata, kljuc, cena):
    """POZITIVNA KONTROLA — najvažnija tvrdnja ovog bloka. `case_commander` i
    `zastarelost_guardian` su isti feature_key za AI i ne-AI endpointe. Da ih je
    migracija nulirala, poklonila bi stvarnu GPT potrošnju — skuplja greška od
    one koja se ispravlja."""
    import shared.usage as usage

    stack = naplata(baza_111_112)
    uid = _napravi_korisnika(baza_111_112, 15)

    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", kljuc)

    assert preostalo == 15 - cena, (
        f"{kljuc}: naplaćeno {15 - preostalo} umesto {cena} — deljeni ključ je "
        "obesnaplaćen ili mu je cena promenjena"
    )
    assert _bilans(baza_111_112, uid) == 15 - cena
    assert "deduct_n_credits" in stack.sim.rpc_log


# ═══════════════════════════════════════════════════════════════════════════
# G4 — KNJIGOVODSTVENA INVARIJANTA POSLE SVE ČETIRI MIGRACIJE (107+108+111+112)
# ═══════════════════════════════════════════════════════════════════════════
# `test_wave9_billing_invariant.py` istu invarijantu dokazuje nad bazom sa 107 +
# 108. Ova kombinacija — sa 111 i 112 u ISTOJ bazi, i sa cenama iz pravog
# Registry-ja umesto iz mokovane politike — nije postojala.

def _proveri_invarijantu(dsn, uid, pocetni, uspesnih, cena, oznaka):
    trenutni = _bilans(dsn, uid)
    assert trenutni >= 0, f"{oznaka}: bilans je otišao u minus ({trenutni})"
    assert uspesnih * cena + trenutni == pocetni, (
        f"{oznaka}: knjigovodstvo ne štima — {uspesnih} x {cena} + {trenutni} != {pocetni}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kljuc,cena,pocetni,zahteva",
    [
        # Cene NISU prepisane iz koda — dolaze iz pravog Registry-ja:
        # ai_pravna_pitanja krediti=1 x credit_multiplier=1 (064/069).
        ("ai_pravna_pitanja", 1, 20, 40),
        # strategija krediti=1 x credit_multiplier=6 (069) = 6 po pozivu.
        ("strategija", 6, 20, 25),
    ],
)
async def test_G4_invarijanta_pod_konkurencijom_sa_sve_cetiri_migracije(
    baza_111_112, naplata, kljuc, cena, pocetni, zahteva
):
    from fastapi import HTTPException
    import shared.usage as usage

    naplata(baza_111_112)
    uid = _napravi_korisnika(baza_111_112, pocetni)

    async def jedan():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", kljuc)
            return "OK"
        except HTTPException as e:
            return f"HTTP{e.status_code}"

    ishodi = await asyncio.gather(*[jedan() for _ in range(zahteva)])
    uspesnih = ishodi.count("OK")

    assert set(ishodi) <= {"OK", "HTTP402"}, f"neočekivani statusi: {set(ishodi)}"
    assert uspesnih == pocetni // cena, (
        f"{kljuc}: bilans {pocetni} po ceni {cena} finansira {pocetni // cena} "
        f"operacija, prošlo je {uspesnih}"
    )
    _proveri_invarijantu(baza_111_112, uid, pocetni, uspesnih, cena, kljuc)


@pytest.mark.anyio
async def test_G4_cena_nula_iz_111_ne_curi_pod_opterecenjem(baza_111_112, naplata):
    """Oblik koji pravi migracija 111, ali nad PRAVIM redom Registry-ja i nad
    bazom koja ima i 112: dugme „↻ Osveži" na ekranu Podešavanja ne sme ništa
    da naplati ni pod opterećenjem."""
    import shared.usage as usage

    stack = naplata(baza_111_112)
    uid = _napravi_korisnika(baza_111_112, 30)

    ishodi = await asyncio.gather(
        *[usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")
          for _ in range(40)]
    )

    assert all(r == 30 for r in ishodi), f"cena 0 je ipak nešto naplatila: {sorted(set(ishodi))}"
    _proveri_invarijantu(baza_111_112, uid, 30, 0, 0, "cena-nula")
    assert "deduct_n_credits" not in stack.sim.rpc_log


@pytest.mark.anyio
async def test_G4_naplata_upisuje_provenance_u_STVARNU_tabelu(baza_111_112, naplata):
    """Wave 9 provenance testovi mere payload nad LAŽNIM Supabase klijentom.
    Ovde `_log_usage_event` piše u pravu `feature_usage_log` posle prave 112 —
    jedini dokaz da migracija i kod pristaju jedno uz drugo."""
    import shared.ai_provenance as prov
    import shared.usage as usage
    from shared.ai_provenance import set_request_context

    naplata(baza_111_112)
    uid = _napravi_korisnika(baza_111_112, 10)
    # UUID, a ne „PRED-42": `feature_usage_log.predmet_id` je `uuid` (112), a
    # `predmeti.id` je UUID (supabase_setup.sql:301) — v. nalaz RC-112-DEBT-001.
    predmet = str(uuid.uuid4())

    t_req = prov._request_ctx.set({})
    try:
        set_request_context(user_id=uid, correlation_id="RC-CID-112")
        await usage.UsageService.consume(
            uid, "advokat@vindex.rs", "ai_pravna_pitanja", predmet_id=predmet
        )
    finally:
        prov._request_ctx.reset(t_req)

    redovi = _upit(
        baza_111_112,
        "SELECT feature_key, krediti_potroseni, predmet_id, correlation_id "
        "FROM public.feature_usage_log WHERE user_id = %s",
        (uid,),
    )
    assert len(redovi) == 1, f"očekivan tačno 1 red telemetrije, nađeno {len(redovi)}"
    red = redovi[0]
    assert str(red["predmet_id"]) == predmet, "predmet_id nije stigao do baze"
    assert red["correlation_id"] == "RC-CID-112", "correlation_id nije stigao do baze"
    assert float(red["krediti_potroseni"]) == 1.0, "naplatni podatak je izmenjen"
    # Lanac iz zaglavlja 112 je time zatvoren i nad pravom bazom:
    # user → operation → predmet → correlation_id.
    assert _bilans(baza_111_112, uid) == 9, "telemetrija je promenila naplaćeni iznos"


@pytest.mark.anyio
async def test_G4_bez_konteksta_red_telemetrije_i_dalje_ulazi(baza_111_112, naplata):
    """Fail-soft strana istog puta: bez konteksta red mora ući, sa NULL
    kolonama — ponašanje identično stanju pre 112."""
    import shared.ai_provenance as prov
    import shared.usage as usage

    naplata(baza_111_112)
    uid = _napravi_korisnika(baza_111_112, 10)

    t_req = prov._request_ctx.set({})
    t_case = prov._case_ctx.set({})
    try:
        await usage.UsageService.consume(uid, "advokat@vindex.rs", "ai_pravna_pitanja")
    finally:
        prov._request_ctx.reset(t_req)
        prov._case_ctx.reset(t_case)

    redovi = _upit(
        baza_111_112,
        "SELECT predmet_id, correlation_id, krediti_potroseni "
        "FROM public.feature_usage_log WHERE user_id = %s",
        (uid,),
    )
    assert len(redovi) == 1, "red telemetrije je izgubljen kad konteksta nema"
    assert redovi[0]["predmet_id"] is None and redovi[0]["correlation_id"] is None
    assert _bilans(baza_111_112, uid) == 9


# ═══════════════════════════════════════════════════════════════════════════
# G5 — NEMA DUPLIH NI KONFLIKTNIH ŠEMA ARTEFAKATA
# ═══════════════════════════════════════════════════════════════════════════

def _bez_komentara(putanja: Path) -> str:
    tekst = putanja.read_text(encoding="utf-8", errors="replace")
    return "\n".join(l for l in tekst.splitlines() if not l.lstrip().startswith("--"))


def test_G5_samo_112_deklarise_provenance_kolone():
    """Ako bi neka druga migracija dodavala `predmet_id`/`correlation_id` na
    `feature_usage_log` (npr. kao `text` ili sa DEFAULT-om), redosled
    pokretanja bi odlučivao kakva je kolona — a to se ne bi videlo ni u jednom
    postojećem testu."""
    pat = re.compile(
        r"ALTER\s+TABLE\s+(?:public\.)?feature_usage_log\b(.*?);", flags=re.S | re.I
    )
    deklaracije = {}
    for putanja in sorted(MIGRATIONS_DIR.glob("*.sql")):
        for blok in pat.findall(_bez_komentara(putanja)):
            for m in re.finditer(
                r"ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)\s+([\w ]+)", blok, flags=re.I
            ):
                deklaracije.setdefault(m.group(1).lower(), set()).add(
                    (putanja.name, re.sub(r"\s+", " ", m.group(2)).strip().lower())
                )

    for kolona in ("predmet_id", "correlation_id"):
        izvori = deklaracije.get(kolona, set())
        assert len(izvori) == 1, (
            f"{kolona} na feature_usage_log deklarisan na više mesta: {sorted(izvori)}"
        )
        fajl, tip = next(iter(izvori))
        assert fajl == "112_feature_usage_provenance.sql", (
            f"{kolona} dolazi iz {fajl}, a očekivana je isključivo migracija 112"
        )
        assert tip.startswith("uuid" if kolona == "predmet_id" else "text"), (
            f"{kolona}: deklarisan tip {tip!r}"
        )


def test_G5_nema_dva_indeksa_istog_imena_sa_razlicitom_definicijom():
    """Postgres `CREATE INDEX IF NOT EXISTS` gleda SAMO ime. Dve migracije koje
    isto ime vežu za različite kolone daju bazu u kojoj indeks postoji, ali ne
    onaj koji druga migracija misli da je napravila — i nijedna ne puca."""
    pat = re.compile(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
        r"([A-Za-z0-9_\"]+)\s+ON\s+(.*?);",
        flags=re.S | re.I,
    )
    definicije = {}
    for putanja in sorted(MIGRATIONS_DIR.glob("*.sql")):
        for m in pat.finditer(_bez_komentara(putanja)):
            ime = m.group(1).strip('"').lower()
            definicija = re.sub(r"\s+", " ", m.group(2)).strip().lower()
            definicije.setdefault(ime, set()).add(definicija)

    konflikti = {k: sorted(v) for k, v in definicije.items() if len(v) > 1}
    assert not konflikti, f"isto ime indeksa, različite definicije: {konflikti}"

    # Indeksi koje 112 uvodi moraju biti nova imena, ne preuzeta.
    for ime in ("feature_usage_log_correlation_idx", "feature_usage_log_predmet_idx"):
        assert ime in definicije, f"{ime} nije pronađen ni u jednoj migraciji"


def test_G5_feature_analytics_view_radi_posle_112(baza):
    """VIEW iz 065 bira imenovane kolone, pa ga dodavanje novih ne obara — to
    zaglavlje 112 tvrdi. Ovde se izvršava."""
    kolone_pre = {
        r["column_name"]
        for r in _upit(
            baza,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='feature_analytics'",
        )
    }
    assert kolone_pre, "feature_analytics VIEW ne postoji ni pre 112 — lanac je nepotpun"

    _ubaci_redove_loga(baza, 3)
    _primeni(baza, MIGRATION_112)

    redovi = _upit(baza, "SELECT * FROM public.feature_analytics ORDER BY feature_key")
    assert len(redovi) == 1, f"VIEW je vratio {len(redovi)} redova, očekivan 1 agregat"
    assert redovi[0]["feature_key"] == "ai_pravna_pitanja"
    assert redovi[0]["poziva"] == 3, "agregacija po VIEW-u je pogrešna posle 112"

    kolone_posle = {
        r["column_name"]
        for r in _upit(
            baza,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='feature_analytics'",
        )
    }
    assert kolone_posle == kolone_pre, (
        "112 je promenila skup kolona VIEW-a — svaki potrošač analitike bi to osetio"
    )


def test_G5_111_ne_dira_nijedan_red_van_svoja_tri(baza):
    """Nad seed-om koji prave PRAVE migracije (69+ redova), ne nad uzorkom od
    12 koji drži Wave 9."""
    kolone = ("feature_key, krediti, chargeable, ai_model, minimum_plan, "
              "cooldown_seconds, updated_by, credit_multiplier, feature_type, status")
    pre = {
        r["feature_key"]: r
        for r in _upit(baza, f"SELECT {kolone} FROM public.feature_registry")
    }
    assert len(pre) > 60, f"lanac je napravio samo {len(pre)} redova — očekivan ceo Registry"

    _primeni(baza, MIGRATION_111)

    post = {
        r["feature_key"]: r
        for r in _upit(baza, f"SELECT {kolone} FROM public.feature_registry")
    }
    assert set(pre) == set(post), "migracija 111 je dodala ili obrisala red"

    obim = {"confidence_audit", "conflict_check", "da_wallet_risk_assessment"}
    for kljuc in sorted(set(pre) - obim):
        assert post[kljuc] == pre[kljuc], f"{kljuc}: red van obima migracije 111 je izmenjen"

    dirnuti = {
        r["feature_key"]
        for r in _upit(
            baza,
            "SELECT feature_key FROM public.feature_registry "
            "WHERE updated_by = 'migration_111_phantom_ai_charges'",
        )
    }
    assert dirnuti == obim, f"obim izmene je {sorted(dirnuti)}, očekivano {sorted(obim)}"


# ═══════════════════════════════════════════════════════════════════════════
# G6 — READ-ONLY OWNER PROVERA: scripts/verify_migration_112.py
# ═══════════════════════════════════════════════════════════════════════════
# Skripta se pokreće kao PODPROCES, tačno onako kako će je vlasnik pokrenuti.
# Provera u istom procesu ne bi merila ni izlazni kod ni to da connection
# string ne procuri u ispis.

def _pokreni_verify(dsn: str | None, *, bez_psycopg: bool = False):
    env = {k: v for k, v in os.environ.items() if k not in ("SUPABASE_DB_URL", "DATABASE_URL")}
    if dsn:
        env["SUPABASE_DB_URL"] = dsn
    argv = [sys.executable]
    if bez_psycopg:
        # Nema deinstalacije: `-c` skript ubacuje blokadu uvoza u `sys.modules`
        # pa pokreće skriptu, čime se meri STVARNA grana bez psycopg.
        argv += [
            "-c",
            "import sys, runpy\n"
            "class _B:\n"
            "    def find_module(self, name, path=None):\n"
            "        if name == 'psycopg': raise ImportError('psycopg blokiran za test')\n"
            "        return None\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name == 'psycopg': raise ImportError('psycopg blokiran za test')\n"
            "        return None\n"
            "sys.meta_path.insert(0, _B())\n"
            "sys.modules.pop('psycopg', None)\n"
            f"sys.argv = [{str(VERIFY_112)!r}]\n"
            f"runpy.run_path({str(VERIFY_112)!r}, run_name='__main__')\n",
        ]
    else:
        argv += [str(VERIFY_112)]
    return subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(REPO_ROOT), timeout=120,
    )


def test_G6_migrirana_baza_daje_izlazni_kod_nula(baza_111_112):
    r = _pokreni_verify(baza_111_112)
    assert r.returncode == 0, (
        f"skripta je pala nad ispravno migriranom bazom:\n{r.stdout}\n{r.stderr}"
    )
    assert "REZULTAT: PASS" in r.stdout
    assert r.stdout.count("[PASS]") == 4, f"očekivane 4 PASS tačke:\n{r.stdout}"


def test_G6_nemigrirana_baza_daje_izlazni_kod_jedan(baza):
    """Bez ove tvrdnje skripta bi mogla da vraća 0 uvek — i vlasnikova provera
    ne bi merila ništa."""
    r = _pokreni_verify(baza)
    assert r.returncode == 1, f"nemigrirana baza mora dati kod 1, dala {r.returncode}\n{r.stdout}"
    assert "REZULTAT: FAIL" in r.stdout
    assert "predmet_id" in r.stdout and "correlation_id" in r.stdout


def test_G6_bez_env_promenljive_daje_izlazni_kod_dva():
    r = _pokreni_verify(None)
    assert r.returncode == 2, f"bez env promenljive očekivan kod 2, dobijen {r.returncode}"
    assert "SUPABASE_DB_URL" in r.stderr


def test_G6_bez_psycopg_daje_izlazni_kod_dva(baza_111_112):
    r = _pokreni_verify(baza_111_112, bez_psycopg=True)
    assert r.returncode == 2, f"bez psycopg očekivan kod 2, dobijen {r.returncode}\n{r.stderr}"
    assert "psycopg" in r.stderr


def test_G6_connection_string_se_nikad_ne_ispisuje(baza_111_112):
    """Apsolutno pravilo ovog sprinta. Vlasnik će skriptu pokrenuti sa
    produkcionim DSN-om i verovatno nalepiti izlaz — DSN ne sme biti u njemu."""
    ceo_izlaz = ""
    for dsn, ocekivan_kod in ((baza_111_112, 0),):
        r = _pokreni_verify(dsn)
        assert r.returncode == ocekivan_kod
        ceo_izlaz += r.stdout + r.stderr

    # Ni ceo DSN, ni njegovi delovi koji bi na produkciji bili tajni.
    assert baza_111_112 not in ceo_izlaz, "ceo connection string je ispisan"
    for komad in psycopg.conninfo.conninfo_to_dict(baza_111_112).values():
        if isinstance(komad, str) and len(komad) > 4:
            assert komad not in ceo_izlaz, f"deo connection string-a ({komad!r}) je ispisan"


def test_G6_skripta_ne_menja_bazu(baza_111_112):
    """`default_transaction_read_only=on` je tvrdnja iz dokumentacije skripte.
    Ovde se meri: šema I podaci moraju biti bajt-identični posle pokretanja."""
    _ubaci_redove_loga(baza_111_112, 4)
    sema_pre = _semantski_snimak(baza_111_112)
    podaci_pre = _snimak_loga(baza_111_112)
    registry_pre = _upit(
        baza_111_112,
        "SELECT feature_key, krediti, chargeable, updated_by FROM public.feature_registry "
        "ORDER BY feature_key",
    )

    assert _pokreni_verify(baza_111_112).returncode == 0

    assert _semantski_snimak(baza_111_112) == sema_pre, "skripta je promenila šemu"
    assert _snimak_loga(baza_111_112) == podaci_pre, "skripta je promenila redove naplate"
    assert (
        _upit(
            baza_111_112,
            "SELECT feature_key, krediti, chargeable, updated_by FROM public.feature_registry "
            "ORDER BY feature_key",
        )
        == registry_pre
    ), "skripta je promenila feature_registry"


@pytest.mark.parametrize(
    "kvar,sql",
    [
        ("nedostaje_indeks", "DROP INDEX public.feature_usage_log_correlation_idx"),
        (
            "dodat_foreign_key",
            "ALTER TABLE public.feature_usage_log "
            "ADD CONSTRAINT rc_test_fk FOREIGN KEY (predmet_id) "
            "REFERENCES public.business_groups(id)",
        ),
        (
            "pogresan_tip",
            "ALTER TABLE public.feature_usage_log "
            "ALTER COLUMN predmet_id TYPE text USING predmet_id::text",
        ),
        (
            "kolona_je_NOT_NULL",
            "ALTER TABLE public.feature_usage_log "
            "ALTER COLUMN correlation_id SET NOT NULL",
        ),
    ],
)
def test_G6_skripta_hvata_svaki_pojedinacni_kvar(baza_111_112, kvar, sql):
    """Bez ovoga bi tačke 1-3 skripte mogle biti prazne — pokazale bi PASS zato
    što ništa ne mere. Svaki kvar se uvodi pojedinačno i mora dati kod 1."""
    with psycopg.connect(baza_111_112, autocommit=True) as c:
        c.execute(sql)

    r = _pokreni_verify(baza_111_112)
    assert r.returncode == 1, (
        f"kvar {kvar!r} nije prijavljen — skripta je vratila {r.returncode}:\n{r.stdout}"
    )
    assert "[FAIL]" in r.stdout
