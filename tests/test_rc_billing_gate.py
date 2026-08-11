# -*- coding: utf-8 -*-
"""
Release Candidate — BILLING / ATOMICITY GATE.

Šest naplatnih ugovora dokazanih nad PRAVIM PostgreSQL-om, kroz PRAVI
`UsageService.consume` / `refund`, bez ijedne mokovane naplate:

    1. SUCCESS      AI uspeh        -> TAČNO jedna naplata
    2. FAILURE      AI pad          -> NULA naplate
    3. RETRY        retry koji uspe -> tačno jedna uspešna naplata, ne dve
    4. CONCURRENCY  N konkurentnih  -> bilans nikad ispod nule,
                                       uspešne x cena + bilans == početni
    5. ZERO BALANCE 0 kredita       -> skup AI posao NE POČINJE
    6. PHANTOM      ne-AI endpoint  -> ne troši AI kredit (migracija 111)

ŠTA JE VEĆ DOKAZANO DRUGDE — CITIRANO, NE PREPISANO
───────────────────────────────────────────────────
Ovaj fajl NE ponavlja tvrdnje koje već stoje. Za svaki ugovor postojeći dokaz
je imenovan uz test, a ovde se dodaje samo ono što nedostaje:

  • `tests/test_wave9_billing_invariant.py` (22)  — invarijanta nad 107+108,
    matrica kvara, granica bilansa, ukršteni consume/refund, bilans 0.
  • `tests/test_wave9_migration_111.py` (30)      — phantom charge, cooldown,
    besplatni ključevi, idempotencija 111.
  • `tests/test_rc_migration_gate.py` (35)        — 107+108+111+112 zajedno,
    šema/indeksi/komentari 112, provenance upis nad pravom tabelom.
  • `tests/test_wave6_preflight_balance.py`       — pre-flight kapija ispred
    skupog posla u `routers/strategija.py`.
  • `tests/test_wave7_failure_matrix.py`          — naplata po tipu kvara.
  • `tests/test_p1_charge_on_failure.py`          — dedupe, idempotency key.

RUPA KOJU OVAJ FAJL ZATVARA — TELEMETRIJA JE ŽIVA
─────────────────────────────────────────────────
Svaki postojeći dokaz naplate nad pravom bazom ISKLJUČUJE deo pravog puta:

  • `test_wave9_billing_invariant.py` gasi `_log_usage_event`
    (`monkeypatch.setattr(usage, "_log_usage_event", _noop_log)`), pa telemetrija
    tamo NE postoji.
  • `test_rc_migration_gate.py` gasi `_claim_cooldown_atomic` i meri telemetriju
    samo za ISPRAVAN UUID (`test_G4_naplata_upisuje_provenance_u_STVARNU_tabelu`).

Ovde NIJEDNO od toga nije ugašeno: cene dolaze iz pravog `feature_registry`,
naplata iz prave `deduct_n_credits` (107), brojač iz prave
`increment_feature_usage` (108), cooldown iz pravog `_claim_cooldown_atomic`, a
telemetrija se STVARNO upisuje u pravu `feature_usage_log` (065 + 112). Zato
svaki ugovor ovde meri i NOVAC i BROJ REDOVA TELEMETRIJE — druga polovina koju
nijedan postojeći test ne meri, a na kojoj živi nalaz RC-112-DEBT-001.

RC-112-DEBT-001 — POTVRĐEN MERENJEM, POPRAVLJEN
───────────────────────────────────────────────
Sonda nad pravim PostgreSQL-om (klaster 127.0.0.1:55433):

    INSERT ... predmet_id = 'PRED-42'
      -> psycopg.errors.InvalidTextRepresentation, SQLSTATE 22P02
      -> 'invalid input syntax for type uuid: "PRED-42"'
      -> _nedostaje_kolona(exc)        = False
      -> _is_missing_column_error(exc) = False
      -> redova u feature_usage_log    = 0     (CEO red naplate izgubljen)
    Kontrola: isti upis BEZ provenance polja uspeva (1 red).
    Kontrola: PGRST204 se i dalje ispravno prepoznaje (True).

Popravka je u `shared/usage.py::_provenance_polja` / `_kanonski_uuid`: vrednost
koja nije UUID se izostavlja iz telemetrije umesto da obori ceo red. Blok §U7
niže pada bez te popravke.

OTKRIVANJE SERVERA
──────────────────
Isti mehanizam kao ostali PG testovi ($VINDEX_TEST_PG_DSN, pa 127.0.0.1:55433,
pa 55432). Fallback na 5432 je NAMERNO izostavljen — to je trajni servis sa
stvarnim podacima, a ovaj fajl pravi i briše baze. Preskakanje je činjenica o
okruženju, nikad način da se izbegne tvrdnja koja pada.
    Podizanje: python scripts/test_db.py up
"""
import asyncio
import inspect
import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"

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
        # 5432 se NE proba — v. zaglavlje modula.
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
        "127.0.0.1:55433, 127.0.0.1:55432) — RC billing gate preskočen. "
        "Podizanje: python scripts/test_db.py up"
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# Baza — ceo lanac migracija koji naplata stvarno zahteva
# ═══════════════════════════════════════════════════════════════════════════
# Isti lanac koji `test_rc_migration_gate.py` već dokazuje kao primenljiv;
# ovde se koristi kao TEMELJ za merenje naplate, a ne kao predmet merenja.

_LANAC = [
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
    "111_phantom_ai_charges.sql",
    "112_feature_usage_provenance.sql",
]

# Šema `auth` postoji samo u Supabase-u, a RLS politike migracija 064/065 je
# zovu. Ne utiče na semantiku: migracije se i na produkciji pokreću kao vlasnik.
_AUTH_SIM = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE
    AS $$ SELECT 'service_role'::text $$;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE
    AS $$ SELECT NULL::uuid $$;
"""

# Prava definicija (`supabase_setup.sql:53`) nosi FK na `auth.users(id)` —
# ista minimalna verzija koju već koriste postojeći PG testovi naplate.
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
    """Baza sa CELIM lancem — Postgres TEMPLATE, gradi se jednom po modulu."""
    dbname = f"vindex_rcbill_tmpl_{uuid.uuid4().hex[:10]}"

    with psycopg.connect(_SERVER_DSN, autocommit=True) as c:
        for role in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{dbname}"')

    try:
        with psycopg.connect(_dsn_za(dbname), autocommit=True) as c:
            c.execute(_AUTH_SIM)
            c.execute(_USER_CREDITS_DDL)
            for ime in _LANAC:
                c.execute((MIGRATIONS_DIR / ime).read_text(encoding="utf-8"))
        yield dbname
    finally:
        _drop(dbname)


@pytest.fixture
def baza(sablon):
    """Sveža, potpuno migrirana kopija šablona za jedan test."""
    dbname = f"vindex_rcbill_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(_SERVER_DSN, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{dbname}" TEMPLATE "{sablon}"')
    try:
        yield _dsn_za(dbname)
    finally:
        _drop(dbname)


# ─── Pomoćni upiti ───────────────────────────────────────────────────────────

def _upit(dsn, sql, params=None):
    with psycopg.connect(dsn, autocommit=True) as c:
        cur = c.execute(sql, params)
        imena = [d.name for d in cur.description]
        return [dict(zip(imena, r)) for r in cur.fetchall()]


def _bilans(dsn, uid):
    r = _upit(dsn, "SELECT credits_remaining FROM public.user_credits WHERE user_id=%s", (uid,))
    return r[0]["credits_remaining"] if r else None


def _cena_iz_registryja(dsn, kljuc) -> int:
    """Cena kakvu je `consume` razrešava: krediti x credit_multiplier.

    Čita se IZ BAZE, ne prepisuje u test. Da je prepisana, promena cene u
    Admin Console-u bi prošla nezapaženo — a upravo to je klasa greške koju
    ovaj gate treba da hvata."""
    r = _upit(
        dsn,
        "SELECT krediti, credit_multiplier FROM public.feature_registry WHERE feature_key=%s",
        (kljuc,),
    )
    assert r, f"feature_key {kljuc!r} nema red u feature_registry"
    return int(float(r[0]["krediti"]) * max(float(r[0]["credit_multiplier"] or 1), 1))


def _telemetrija(dsn, uid):
    return _upit(
        dsn,
        "SELECT feature_key, krediti_potroseni, predmet_id, correlation_id "
        "FROM public.feature_usage_log WHERE user_id=%s ORDER BY created_at",
        (uid,),
    )


def _napravi_korisnika(dsn, bilans: int) -> str:
    uid = str(uuid.uuid4())
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            "INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s,%s)",
            (uid, bilans),
        )
    return uid


def _proveri_invarijantu(dsn, uid, pocetni, uspesnih, cena, oznaka):
    trenutni = _bilans(dsn, uid)
    assert trenutni >= 0, f"{oznaka}: bilans je otišao ispod nule ({trenutni})"
    assert uspesnih * cena + trenutni == pocetni, (
        f"{oznaka}: knjigovodstvo ne štima — {uspesnih} x {cena} + {trenutni} != {pocetni}"
    )
    return trenutni


# ═══════════════════════════════════════════════════════════════════════════
# Šim — jedini most ka bazi. Nema mokovane naplate ni mokovane telemetrije.
# ═══════════════════════════════════════════════════════════════════════════

class _Sim:
    """Minimalan stand-in za Supabase klijenta.

    Podržava TAČNO ono što `UsageService.consume`/`refund` stvarno koriste, i
    ništa više — nepoznata tabela ili filter diže AssertionError umesto da tiho
    prođe. Tiho prolaženje je tačno ono što je omogućilo da RC-112-DEBT-001
    preživi 87 postojećih naplatnih testova.
    """

    _RPC = {
        "deduct_n_credits": "SELECT public.deduct_n_credits(%(p_user_id)s, %(p_n)s)",
        "refund_n_credits": "SELECT public.refund_n_credits(%(p_user_id)s, %(p_n)s)",
        "increment_monthly_usage": "SELECT public.increment_monthly_usage(%(p_user_id)s, %(p_mesec)s)",
        "increment_feature_usage": (
            "SELECT public.increment_feature_usage(%(p_user_id)s, %(p_feature)s, %(p_dan)s, "
            "%(p_mesec)s, %(p_credits)s, %(p_dnevni_limit)s)"
        ),
    }

    _TABELE = {"feature_registry", "feature_dependencies", "feature_usage", "feature_usage_log"}

    def __init__(self, dsn):
        self._dsn = dsn
        self.rpc_log = []
        self.upisi_loga = 0
        # Ubacivanje kvara u telemetriju (dokaz fail-soft ugovora, §U7).
        self.log_insert_pada = None

    def rpc(self, name, params):
        self.rpc_log.append(name)
        sql = self._RPC[name]
        dsn = self._dsn

        class _Call:
            def execute(self_inner):
                with psycopg.connect(dsn, autocommit=True) as c:
                    return SimpleNamespace(data=c.execute(sql, params).fetchone()[0])

        return _Call()

    def table(self, name):
        assert name in self._TABELE, (
            f"naplatni put je dodirnuo tabelu {name!r} koju ovaj dokaz ne pokriva — "
            "dopuni šim umesto da tiho prođe"
        )
        return _Upit(self._dsn, name, self)


class _Upit:
    """PostgREST-oblik lanac: select/eq/lt/order/limit/maybe_single/insert/update."""

    _FILTERI = {"user_id", "feature_key", "dan", "mesec"}

    def __init__(self, dsn, tabela, sim):
        self._dsn = dsn
        self._tabela = tabela
        self._sim = sim
        self._kolone = "*"
        self._filteri = []
        self._lt = []
        self._single = False
        self._insert = None
        self._update = None
        self._order = None
        self._limit = None

    def select(self, sta):
        self._kolone = sta
        return self

    def eq(self, kolona, vrednost):
        assert kolona in self._FILTERI, f"nepodržan filter {kolona!r}"
        self._filteri.append((kolona, vrednost))
        return self

    def lt(self, kolona, vrednost):
        self._lt.append((kolona, vrednost))
        return self

    def order(self, kolona, desc=False):
        self._order = (kolona, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self):
        self._single = True
        return self

    def insert(self, payload):
        self._insert = dict(payload)
        return self

    def update(self, payload):
        self._update = dict(payload)
        return self

    def _where(self):
        delovi = [f"{k} = %s" for k, _ in self._filteri]
        delovi += [f"{k} < %s" for k, _ in self._lt]
        params = [v for _, v in self._filteri] + [v for _, v in self._lt]
        return (" AND ".join(delovi) or "true"), params

    def execute(self):
        if self._insert is not None:
            if self._tabela == "feature_usage_log":
                self._sim.upisi_loga += 1
                if self._sim.log_insert_pada is not None:
                    raise self._sim.log_insert_pada
            imena = list(self._insert)
            sql = (
                f"INSERT INTO public.{self._tabela} ({', '.join(imena)}) "
                f"VALUES ({', '.join(['%s'] * len(imena))})"
            )
            with psycopg.connect(self._dsn, autocommit=True) as c:
                c.execute(sql, [self._insert[k] for k in imena])
            return SimpleNamespace(data=[{}])

        if self._update is not None:
            where, params = self._where()
            postavke = ", ".join(f"{k} = %s" for k in self._update)
            sql = f"UPDATE public.{self._tabela} SET {postavke} WHERE {where} RETURNING id"
            with psycopg.connect(self._dsn, autocommit=True) as c:
                cur = c.execute(sql, list(self._update.values()) + params)
                redovi = [{"id": r[0]} for r in cur.fetchall()]
            return SimpleNamespace(data=redovi)

        where, params = self._where()
        sql = f"SELECT {self._kolone} FROM public.{self._tabela} WHERE {where}"
        if self._order:
            sql += f" ORDER BY {self._order[0]} {'DESC' if self._order[1] else 'ASC'}"
        if self._limit:
            sql += f" LIMIT {int(self._limit)}"
        with psycopg.connect(self._dsn, autocommit=True) as c:
            cur = c.execute(sql, params)
            imena = [d.name for d in cur.description]
            redovi = []
            for r in cur.fetchall():
                d = dict(zip(imena, r))
                # Pravi Supabase klijent vraća JSON brojeve, ne Decimal.
                for broj in ("krediti", "credit_multiplier", "estimated_cost_usd",
                             "krediti_potroseni"):
                    if d.get(broj) is not None:
                        d[broj] = float(d[broj])
                # `created_at` se u `_seconds_since_last_call` parsira iz stringa.
                if d.get("created_at") is not None:
                    d["created_at"] = d["created_at"].isoformat()
                redovi.append(d)
        if self._single:
            return SimpleNamespace(data=redovi[0] if redovi else None)
        return SimpleNamespace(data=redovi)


@pytest.fixture
def naplata(baza, monkeypatch):
    """Ožičava PRAVI `UsageService` na PRAVU bazu.

    Namerno NIJE ugašeno ništa od pravog puta — ni `_log_usage_event`
    (za razliku od `test_wave9_billing_invariant.py`), ni
    `_claim_cooldown_atomic` (za razliku od `test_rc_migration_gate.py`).
    Jedini patch-evi su most ka bazi (`_get_supa`, `_get_credits`) i
    `_is_founder`, jer founder po definiciji ne plaća pa ne bi bilo šta meriti.
    """
    import shared.deps as deps
    import shared.feature_registry as fr
    import shared.usage as usage

    sim = _Sim(baza)
    # Sva tri modula drže SOPSTVENU referencu na `_get_supa` (from-import u
    # vreme učitavanja) — patch nad jednim ne pokriva ostale.
    monkeypatch.setattr(deps, "_get_supa", lambda: sim)
    monkeypatch.setattr(fr, "_get_supa", lambda: sim)
    monkeypatch.setattr(usage, "_get_supa", lambda: sim)
    monkeypatch.setattr(usage, "_is_founder", lambda *a, **k: False)
    monkeypatch.setattr(deps, "_is_founder", lambda *a, **k: False)
    monkeypatch.setattr(usage, "_get_credits", lambda uid: _bilans(baza, uid) or 0)
    fr.invalidate()

    yield SimpleNamespace(dsn=baza, sim=sim, monkeypatch=monkeypatch)

    fr.invalidate()


EMAIL = "advokat@vindex.rs"
# Dve prave cene iz pravog Registry-ja: 1 (dominantna) i 6 (najskuplja).
FEATURE = "ai_pravna_pitanja"
SKUPA = "strategija"


# ═══════════════════════════════════════════════════════════════════════════
# §U1 — SUCCESS: AI uspeh -> TAČNO jedna naplata
# ═══════════════════════════════════════════════════════════════════════════
# Novac je već dokazan: `test_wave9_billing_invariant.py::test_A_ng_uspesan_posao_
# zadrzava_naplatu` i `test_wave7_failure_matrix.py::test_ng_uspesan_posao_SE_
# naplacuje`. Ovde se NE ponavlja iznos nego se dodaje druga polovina koju
# nijedan od njih ne meri: da uspeh ostavlja TAČNO JEDAN red telemetrije
# naplate, sa iznosom koji odgovara skinutom novcu.

@pytest.mark.anyio
@pytest.mark.parametrize("kljuc", [FEATURE, SKUPA])
async def test_U1_uspeh_naplacuje_tacno_jednom_i_belezi_tacno_jedan_dogadjaj(naplata, kljuc):
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, kljuc)
    assert cena > 0, f"{kljuc}: test ne meri ništa ako je cena 0"
    pocetni = cena * 3
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    # Produkcioni obrazac: AI posao PA naplata (`routers/precedenti.py:178`).
    ai_pozvan = {"n": 0}

    async def _ai_posao():
        ai_pozvan["n"] += 1
        return "odgovor"

    await _ai_posao()
    preostalo = await usage.UsageService.consume(uid, EMAIL, kljuc)

    assert ai_pozvan["n"] == 1
    assert preostalo == pocetni - cena, f"{kljuc}: `consume` prijavio pogrešan preostatak"
    _proveri_invarijantu(naplata.dsn, uid, pocetni, 1, cena, f"U1-{kljuc}")

    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == 1, (
        f"{kljuc}: jedna uspešna operacija ostavila {len(redovi)} redova telemetrije — "
        "duplirana ili izgubljena naplatna telemetrija"
    )
    assert redovi[0]["feature_key"] == kljuc
    assert float(redovi[0]["krediti_potroseni"]) == float(cena), (
        "telemetrija prijavljuje drugi iznos od onog koji je stvarno skinut"
    )


@pytest.mark.anyio
async def test_U1_dva_uspeha_daju_dve_naplate_i_dva_dogadjaja(naplata):
    """Negativna kontrola za test iznad: da `consume` uopšte ne naplaćuje ili da
    telemetrija uvek piše jedan red, tvrdnja `== 1` bi prolazila vakuumski."""
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, FEATURE)
    pocetni = cena * 5
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    await usage.UsageService.consume(uid, EMAIL, FEATURE)
    await usage.UsageService.consume(uid, EMAIL, FEATURE)

    _proveri_invarijantu(naplata.dsn, uid, pocetni, 2, cena, "U1-dva")
    assert len(_telemetrija(naplata.dsn, uid)) == 2


# ═══════════════════════════════════════════════════════════════════════════
# §U2 — FAILURE: AI pad -> NULA naplate
# ═══════════════════════════════════════════════════════════════════════════
# Matrica tipova kvara (timeout / 5xx / malformisan / firewall) je već
# dokazana: `test_wave9_billing_invariant.py::test_A_svaki_tip_kvara_vraca_
# tacno_naplaceno` i `test_wave7_failure_matrix.py::test_a_gpt_pad_ne_naplacuje`.
# Ovde se dokazuju dva OBRASCA kojima proizvod postiže nulu, oba nad živom
# telemetrijom — što nijedan od ta dva testa nema.

@pytest.mark.anyio
async def test_U2_pad_AI_posla_pre_naplate_ne_ostavlja_ni_kredit_ni_dogadjaj(naplata):
    """Obrazac „naplati POSLE posla" (`routers/evidence.py:485-487`).

    Ako AI padne, `consume` se nikad ne dosegne: ni novac ni naplatni događaj
    ne smeju postojati. Mutacija koja premesti naplatu ISPRED posla obara baš
    ovaj test.
    """
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, SKUPA)
    pocetni = cena * 3
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    class _PadModela(Exception):
        pass

    async def _ai_posao():
        raise _PadModela("502 od provajdera")

    async def _operacija():
        """Doslovan produkcioni redosled: prvo posao, pa naplata."""
        rezultat = await _ai_posao()
        await usage.UsageService.consume(uid, EMAIL, SKUPA)
        return rezultat

    with pytest.raises(_PadModela):
        await _operacija()

    assert _bilans(naplata.dsn, uid) == pocetni, "pad AI posla je ipak nešto naplatio"
    _proveri_invarijantu(naplata.dsn, uid, pocetni, 0, cena, "U2-pre-naplate")
    assert _telemetrija(naplata.dsn, uid) == [], (
        "operacija koja nikad nije isporučena upisana je kao naplatni događaj"
    )


def test_U2_naplata_STVARNO_stoji_posle_AI_posla_a_ne_posle_pre_flight_provere():
    """RC-BILLING-002 — popravlja MERENJE, ne kod.

    `tests/test_wave6_preflight_balance.py::test_d_consime_i_dalje_stoji_POSLE_AI_posla`
    postoji tačno da bi uhvatio premeštanje `consume` ispred AI posla. IZMERENO:
    ne hvata ga. Taj test radi

        poz_thread = src.index("asyncio.to_thread(")

    a PRVI `asyncio.to_thread(` u `post_kompletna_analiza` više NIJE AI posao —
    to je `asyncio.to_thread(_get_credits, uid)` iz same pre-flight kapije
    (pozicija 1002 naspram 2065 za AI posao). Pošto pre-flight po konstrukciji
    uvek prethodi naplati, uslov `poz_thread < poz_consume` je zadovoljen bez
    obzira gde AI posao stoji.

    Ironija je merljiva: pre-flight kapija dodata u Wave 6 je obesmislila
    sopstveni Wave 6 test redosleda. Kad je test pisan, prvi `to_thread` JESTE
    bio AI posao, pa je bio ispravan; dodavanje kapije ga je tiho razoružalo.

    Dokaz: mutacija koja premešta `consume` ispred `with _ai_case_ctx(...)` u
    `_run_analiza` obara 8 testova u `test_wave7_failure_matrix.py`, a
    `test_d` prolazi. Ovaj test pada.

    Ovde se meri POZICIJA STVARNOG AI POSLA (`orkestrator_kompletna_analiza_sync`),
    ne bilo kog `to_thread`. `test_wave6` se NE dira — samo se rupa zatvara ovde.
    """
    import routers.strategija as rs

    src = inspect.getsource(rs.post_kompletna_analiza)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))

    poz_ai_posao = src.index("orkestrator_kompletna_analiza_sync")
    poz_consume = src.index("UsageService.consume")

    assert poz_ai_posao < poz_consume, (
        "atomični odbitak je premešten ISPRED stvarnog AI posla "
        "(`orkestrator_kompletna_analiza_sync`) — time se gubi ugovor "
        "'ne naplaćuj ako AI padne': korisnik plaća i kad analiza pukne"
    )


@pytest.mark.anyio
async def test_U2_kompenzujuci_povracaj_vraca_tacno_naplaceno_ali_trag_ostaje(naplata):
    """Obrazac „naplati pa vrati na kvar" (`routers/precedenti.py:178`).

    Novac mora biti netaknut — to `test_wave9_billing_invariant.py::test_A_*`
    već dokazuje. NOVO ovde: red telemetrije NE sme nestati. Naplata koja se
    desila pa je poništena je i dalje događaj koji se desio; brisanje traga bi
    onemogućilo da se povraćaj ikad dokaže korisniku.
    """
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, SKUPA)
    pocetni = cena * 3
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    await usage.UsageService.consume(uid, EMAIL, SKUPA)
    assert _bilans(naplata.dsn, uid) == pocetni - cena, "naplata se nije desila, test ne meri ništa"

    # Bezbedan oblik povraćaja: eksplicitan iznos, isti koji je naplaćen
    # (v. CREDIT-REFUND-002 u `shared/usage.py`).
    await usage.UsageService.refund(uid, EMAIL, SKUPA, credits=cena)

    _proveri_invarijantu(naplata.dsn, uid, pocetni, 0, cena, "U2-povracaj")
    assert _bilans(naplata.dsn, uid) == pocetni
    assert len(_telemetrija(naplata.dsn, uid)) == 1, (
        "trag o naplati koja je poništena je izbrisan — povraćaj se više ne može dokazati"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §U3 — RETRY: retry koji uspe -> tačno jedna uspešna naplata, ne dve
# ═══════════════════════════════════════════════════════════════════════════
# Novčana strana je dokazana: `test_wave9_billing_invariant.py::test_H_retry_
# posle_5xx_naplacuje_tacno_jednom` i `test_H_retry_bura_od_pet_pokusaja_*`.
# NOVO ovde: razlika između BROJA NAPLATNIH DOGAĐAJA i NETO NAPLATE. Retry
# proizvodi više događaja a tačno jednu neto naplatu; ako bi neko „očistio"
# telemetriju da se poklopi sa neto iznosom, izgubio bi se dokaz da je povraćaj
# uopšte izvršen.

@pytest.mark.anyio
async def test_U3_retry_koji_uspe_ostavlja_tacno_jednu_neto_naplatu(naplata):
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, FEATURE)
    pocetni = cena * 6
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    # Pokušaj 1: naplaćen, posao pao, kredit vraćen.
    await usage.UsageService.consume(uid, EMAIL, FEATURE)
    await usage.UsageService.refund(uid, EMAIL, FEATURE, credits=cena)
    assert _bilans(naplata.dsn, uid) == pocetni, "povraćaj posle prvog pokušaja nije potpun"

    # Pokušaj 2: naplaćen i uspeo.
    await usage.UsageService.consume(uid, EMAIL, FEATURE)

    _proveri_invarijantu(naplata.dsn, uid, pocetni, 1, cena, "U3-retry")
    assert _bilans(naplata.dsn, uid) == pocetni - cena, (
        "retry je naplaćen dvaput — korisnik plaća dva puta za jedan isporučen odgovor"
    )
    assert len(_telemetrija(naplata.dsn, uid)) == 2, (
        "oba pokušaja moraju ostati u logu — jedan naplaćen pa vraćen, jedan zadržan"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §U4 — CONCURRENCY: bilans ne pada ispod minimuma, knjigovodstvo štima
# ═══════════════════════════════════════════════════════════════════════════
# `test_rc_migration_gate.py::test_G4_invarijanta_pod_konkurencijom_sa_sve_cetiri_
# migracije` već dokazuje invarijantu i broj propuštenih zahteva pod
# konkurencijom, ali sa UGAŠENIM cooldown-om i BEZ merenja telemetrije.
# NOVO ovde: pod istim opterećenjem broj naplatnih događaja mora se TAČNO
# poklopiti sa brojem uspešnih naplata — ni jedan fantomski, ni jedan izgubljen.

@pytest.mark.anyio
@pytest.mark.parametrize("kljuc,zahteva", [(FEATURE, 40), (SKUPA, 25)])
async def test_U4_konkurencija_cuva_invarijantu_i_broj_dogadjaja(naplata, kljuc, zahteva):
    from fastapi import HTTPException
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, kljuc)
    pocetni = cena * 5
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    async def jedan():
        try:
            await usage.UsageService.consume(uid, EMAIL, kljuc)
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
    _proveri_invarijantu(naplata.dsn, uid, pocetni, uspesnih, cena, f"U4-{kljuc}")

    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == uspesnih, (
        f"{kljuc}: {uspesnih} naplata pod opterećenjem ostavilo {len(redovi)} redova "
        "telemetrije — odbijeni zahtevi se knjiže kao naplata ili se naplata gubi"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §U5 — ZERO BALANCE: 0 kredita -> skup AI posao NE POČINJE
# ═══════════════════════════════════════════════════════════════════════════
# `tests/test_wave6_preflight_balance.py` dokazuje da pre-flight kapija u
# `routers/strategija.py` ne pokreće posao za bilans 0/1/5, i da `consume`
# ostaje POSLE posla. Ovaj fajl to NE ponavlja.
#
# NOVO ovde su dve rupe koje wave 6 po konstrukciji ne može da vidi:
#   1. wave 6 prag (`_CENA = 6`) PREPISUJE u test. Ako se cena u
#      `feature_registry` promeni preko Admin Console-a, kapija bi gejtovala na
#      pogrešan iznos, a wave 6 bi i dalje bio zelen. Ovde se prag poredi sa
#      cenom PROČITANOM IZ BAZE.
#   2. wave 6 meri samo rutu. Ovde se meri i naplatni sloj: odbijen zahtev ne
#      sme ostaviti naplatni događaj.

def _preflight_prag() -> int:
    """Čita prag pre-flight kapije iz IZVORA rute, bez komentara i docstring-a.

    Isti oprez kao `test_wave6_preflight_balance.py::test_d`: prva verzija tog
    testa merila je pojavu naziva u sopstvenom komentaru. Ovde se komentari
    uklanjaju pre merenja."""
    import routers.strategija as rs

    src = inspect.getsource(rs.post_kompletna_analiza)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    m = re.search(r"_CENA_KOMPLETNE\s*=\s*(\d+)", src)
    assert m, "pre-flight kapija (`_CENA_KOMPLETNE`) više ne postoji u post_kompletna_analiza"
    return int(m.group(1))


def test_U5_preflight_prag_je_JEDNAK_ceni_iz_registryja(baza):
    """Kapija koja gejtuje na drugi iznos od onog koji se naplaćuje je rupa u
    oba smera: preniska propušta posao koji se ne može platiti, previsoka
    odbija korisnika koji ima dovoljno kredita."""
    prag = _preflight_prag()
    cena = _cena_iz_registryja(baza, SKUPA)
    assert prag == cena, (
        f"pre-flight kapija gejtuje na {prag} kredita, a `consume` naplaćuje {cena} "
        f"(feature_registry: krediti x credit_multiplier za '{SKUPA}'). "
        "Prag je hardkodiran u routers/strategija.py i razišao se sa Registry-jem."
    )


@pytest.mark.anyio
async def test_U5_nula_kredita_ne_pokrece_skup_posao(baza):
    """Ista tvrdnja kao wave 6 `test_a`, ali sa pragom PROČITANIM IZ BAZE.

    Ključna tvrdnja nije „vraća 402" nego „posao NIJE pokrenut" — posao je ono
    što košta firmu."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi import HTTPException
    import routers.strategija as rs

    cena = _cena_iz_registryja(baza, SKUPA)
    poslovi = {"n": 0}

    def _job(*a, **k):
        poslovi["n"] += 1
        return ("job-1", False)

    req = rs.OrkestratorRequest(opis_predmeta="X" * 150)
    with patch("shared.deps._get_credits", return_value=0), \
         patch("shared.permissions._is_founder", return_value=False), \
         patch("routers.jobs.create_job_deduped", new=_job), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await rs.post_kompletna_analiza.__wrapped__(
                req=req, request=MagicMock(), background_tasks=MagicMock(),
                user={"user_id": "u-rc", "email": EMAIL},
            )

    assert exc.value.status_code == 402
    assert poslovi["n"] == 0, (
        f"sa 0 kredita (cena {cena}) posao je POKRENUT — GPT-4o pozivi bi se izvršili "
        "i naplatili firmi, a korisnik ne bi dobio ništa"
    )


@pytest.mark.anyio
async def test_U5_odbijen_zahtev_ne_ostavlja_naplatni_dogadjaj(naplata):
    """Naplatni sloj, ne ruta: 0 kredita -> 402 -> nijedan red u logu naplate.

    `test_wave9_billing_invariant.py::test_L` dokazuje da novac ostaje netaknut.
    NOVO: odbijen zahtev ne sme se pojaviti u `feature_usage_log`, inače bi
    izveštaji o potrošnji prikazivali naplate koje se nikad nisu desile."""
    from fastapi import HTTPException
    import shared.usage as usage

    uid = _napravi_korisnika(naplata.dsn, 0)

    with pytest.raises(HTTPException) as exc:
        await usage.UsageService.consume(uid, EMAIL, SKUPA)

    assert exc.value.status_code == 402
    assert _bilans(naplata.dsn, uid) == 0
    assert "deduct_n_credits" not in naplata.sim.rpc_log, (
        "naplata je pozvana iako bilans ne pokriva cenu"
    )
    assert _telemetrija(naplata.dsn, uid) == [], (
        "odbijen zahtev je upisan kao naplatni događaj"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §U6 — PHANTOM: ne-AI endpoint ne troši AI kredit (migracija 111)
# ═══════════════════════════════════════════════════════════════════════════
# Da grupa A ne skida kredit dokazuju već `test_wave9_migration_111.py::
# test_R13_posle_migracije_nijedan_kredit_se_ne_oduzima` i
# `test_rc_migration_gate.py::test_G3_grupa_A_ne_oduzima_nijedan_kredit`.
# NOVO ovde: 111 je namerno izabrala `krediti=0` UMESTO uklanjanja `consume()`
# poziva, baš da bi telemetrija i kuka za buduće limite OSTALE (v. zaglavlje
# migracije 111, odeljak „ZAŠTO krediti=0 A NE UKLANJANJE consume()"). Ta
# namera do sada nije bila dokazana nad pravom tabelom: mora postojati red sa
# iznosom 0.

@pytest.mark.anyio
@pytest.mark.parametrize(
    "kljuc", ["confidence_audit", "conflict_check", "da_wallet_risk_assessment"]
)
async def test_U6_ne_AI_kljuc_ne_trosi_kredit_ali_belezi_dogadjaj(naplata, kljuc):
    import shared.usage as usage

    assert _cena_iz_registryja(naplata.dsn, kljuc) == 0, (
        f"{kljuc}: migracija 111 nije primenjena — test ne meri ono što tvrdi"
    )
    uid = _napravi_korisnika(naplata.dsn, 15)

    preostalo = await usage.UsageService.consume(uid, EMAIL, kljuc)

    assert preostalo == 15
    assert _bilans(naplata.dsn, uid) == 15, f"{kljuc}: AI kredit je i dalje naplaćen"
    assert "deduct_n_credits" not in naplata.sim.rpc_log, (
        f"{kljuc}: `consume` je ušao u granu naplate"
    )
    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == 1, (
        f"{kljuc}: migracija 111 je zadržala `consume()` upravo da bi telemetrija "
        f"ostala, a red nije upisan ({len(redovi)})"
    )
    assert float(redovi[0]["krediti_potroseni"]) == 0.0


@pytest.mark.anyio
async def test_U6_pozitivna_kontrola_deljeni_kljuc_I_DALJE_naplacuje(naplata):
    """Bez ovoga bi §U6 prolazio i da je naplata svuda mrtva.

    `case_commander` je isti feature_key za AI i ne-AI endpointe — da ga je 111
    nulirala, poklonila bi stvarnu GPT potrošnju."""
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, "case_commander")
    assert cena > 0, "deljeni ključ je obesnaplaćen — 111 je proširena preko svog obima"
    uid = _napravi_korisnika(naplata.dsn, 15)

    await usage.UsageService.consume(uid, EMAIL, "case_commander")

    assert _bilans(naplata.dsn, uid) == 15 - cena
    assert "deduct_n_credits" in naplata.sim.rpc_log


# ═══════════════════════════════════════════════════════════════════════════
# §U7 — RC-112-DEBT-001 + FAIL-SOFT UGOVOR TELEMETRIJE
# ═══════════════════════════════════════════════════════════════════════════
# Nalaz predan od Agenta 2, POTVRĐEN merenjem nad pravim PostgreSQL-om pre
# popravke (v. zaglavlje modula za sirov ispis sonde).
#
# Ugovor koji ovaj blok štiti ima dve strane, obe obavezne:
#   (a) neupotrebljiv metapodatak NE SME da odnese ceo red telemetrije naplate;
#   (b) telemetrija NIKAD, ni u kom obliku kvara, ne sme da obori naplatu.

@pytest.mark.anyio
async def test_U7_nevalidan_predmet_id_NE_gubi_red_telemetrije(naplata):
    """RC-112-DEBT-001 — pada bez popravke u `shared/usage.py`.

    Bez popravke: 22P02 iz Postgres-a -> `_nedostaje_kolona` vraća False ->
    uski fallback se ne aktivira -> spoljni `except` proguta -> 0 redova.
    """
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, FEATURE)
    uid = _napravi_korisnika(naplata.dsn, 10)

    await usage.UsageService.consume(uid, EMAIL, FEATURE, predmet_id="PRED-42")

    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == 1, (
        "RC-112-DEBT-001: `predmet_id` koji nije UUID odneo je CEO red telemetrije "
        "naplate (user_id, feature_key, krediti_potroseni) — a ne samo sebe"
    )
    assert redovi[0]["predmet_id"] is None, (
        "neupotrebljiva vrednost je ipak upisana — NULL je jedina istinita "
        "tvrdnja u ovom slučaju (znači: nije zabeleženo)"
    )
    assert float(redovi[0]["krediti_potroseni"]) == float(cena)


@pytest.mark.anyio
async def test_U7_nevalidan_predmet_id_ne_dira_naplatu(naplata):
    """Fail-soft strana (b): iznos i bilans moraju biti identični kao da
    `predmet_id` nikad nije ni prosleđen."""
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, FEATURE)
    pocetni = 10
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    preostalo = await usage.UsageService.consume(uid, EMAIL, FEATURE, predmet_id="PRED-42")

    assert preostalo == pocetni - cena
    _proveri_invarijantu(naplata.dsn, uid, pocetni, 1, cena, "U7-naplata")


@pytest.mark.anyio
async def test_U7_correlation_id_prezivljava_nevalidan_predmet_id(naplata):
    """Zašto je popravka u `_provenance_polja`, a NE proširenje
    `_nedostaje_kolona` na 22P02: fallback bi odbacio OBA provenance polja, a
    `correlation_id` je taj koji tranzitivno vodi do predmeta preko
    `ai_forensics` (zaglavlje migracije 112). Sačuvati ga znači sačuvati lanac
    dokaza čak i kad je `predmet_id` neupotrebljiv."""
    import shared.ai_provenance as prov
    import shared.usage as usage
    from shared.ai_provenance import set_request_context

    uid = _napravi_korisnika(naplata.dsn, 10)

    t_req = prov._request_ctx.set({})
    try:
        set_request_context(user_id=uid, correlation_id="RC-CID-DEBT-001")
        await usage.UsageService.consume(uid, EMAIL, FEATURE, predmet_id="PRED-42")
    finally:
        prov._request_ctx.reset(t_req)

    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == 1
    assert redovi[0]["correlation_id"] == "RC-CID-DEBT-001", (
        "correlation_id je odbačen zajedno sa neispravnim predmet_id-jem — "
        "lanac naplata -> AI provenance je prekinut bez potrebe"
    )
    assert redovi[0]["predmet_id"] is None


@pytest.mark.anyio
async def test_U7_validan_predmet_id_i_dalje_stize_do_baze(naplata):
    """NEGATIVNA KONTROLA popravke. `test_rc_migration_gate.py::test_G4_naplata_
    upisuje_provenance_u_STVARNU_tabelu` ovo dokazuje za zatečeni kod; ovde je
    to zaštita da popravka ne počne da odbacuje i ISPRAVNE vrednosti — inače bi
    §U7 bio zadovoljen i time da se `predmet_id` nikad ne upisuje."""
    import shared.usage as usage

    uid = _napravi_korisnika(naplata.dsn, 10)
    predmet = str(uuid.uuid4())

    await usage.UsageService.consume(uid, EMAIL, FEATURE, predmet_id=predmet)

    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == 1
    assert str(redovi[0]["predmet_id"]) == predmet, "ispravan predmet_id nije stigao do baze"


@pytest.mark.anyio
async def test_U7_nevalidan_argument_NE_pada_na_predmet_iz_konteksta(naplata):
    """Svesna odluka u popravci, zakucana da ne bi bila slučajnost.

    Ako pozivalac EKSPLICITNO imenuje predmet a vrednost je neupotrebljiva,
    tiho preuzimanje predmeta iz contextvar-a bi naplatu pripisalo DRUGOM
    predmetu. Pogrešna atribucija je gora od NULL-a: NULL znači „nije
    zabeleženo", a pogrešan UUID tvrdi neistinu koju forenzika ne može
    razlikovati od istine."""
    import shared.ai_provenance as prov
    import shared.usage as usage

    uid = _napravi_korisnika(naplata.dsn, 10)
    drugi_predmet = str(uuid.uuid4())

    t_case = prov._case_ctx.set({"predmet_id": drugi_predmet})
    try:
        await usage.UsageService.consume(uid, EMAIL, FEATURE, predmet_id="PRED-42")
    finally:
        prov._case_ctx.reset(t_case)

    redovi = _telemetrija(naplata.dsn, uid)
    assert len(redovi) == 1
    assert redovi[0]["predmet_id"] is None, (
        f"naplata je pripisana predmetu {drugi_predmet} koji pozivalac NIJE imenovao"
    )


@pytest.mark.anyio
async def test_U7_potpun_pad_telemetrije_NE_obara_naplatu(naplata):
    """FAIL-SOFT UGOVOR (c) — obavezan bez obzira na popravku.

    Ovo je razlog zašto je RC-112-DEBT-001 gubitak PODATKA a ne gubitak novca:
    ceo `_log_usage_event` je omotan spoljnim `except`-om. Ovde se u upis
    telemetrije ubacuje tvrd kvar baze (ne 22P02, ne PGRST204 — nešto što
    nijedan fallback ne prepoznaje) i tvrdi se da naplata svejedno stoji."""
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, FEATURE)
    pocetni = 10
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    naplata.sim.log_insert_pada = RuntimeError("konekcija ka bazi telemetrije je pukla")

    preostalo = await usage.UsageService.consume(uid, EMAIL, FEATURE)

    assert preostalo == pocetni - cena, "pad telemetrije je oborio naplatu"
    _proveri_invarijantu(naplata.dsn, uid, pocetni, 1, cena, "U7-fail-soft")
    assert naplata.sim.upisi_loga >= 1, "telemetrija nije ni pokušana — test ne meri ništa"
    assert _telemetrija(naplata.dsn, uid) == [], "ubačeni kvar se nije desio"


@pytest.mark.anyio
async def test_U7_pad_citanja_provenance_konteksta_NE_obara_naplatu(naplata):
    """Druga strana istog fail-soft ugovora: kvar u ČITANJU konteksta
    (a ne u upisu) takođe ne sme da dodirne naplatu."""
    import shared.ai_provenance as prov
    import shared.usage as usage

    cena = _cena_iz_registryja(naplata.dsn, FEATURE)
    pocetni = 10
    uid = _napravi_korisnika(naplata.dsn, pocetni)

    def _pukni():
        raise RuntimeError("contextvar sloj je pukao")

    naplata.monkeypatch.setattr(prov, "current_context", _pukni)

    preostalo = await usage.UsageService.consume(uid, EMAIL, FEATURE)

    assert preostalo == pocetni - cena, "pad čitanja konteksta je oborio naplatu"
    _proveri_invarijantu(naplata.dsn, uid, pocetni, 1, cena, "U7-kontekst")
    assert len(_telemetrija(naplata.dsn, uid)) == 1, (
        "red telemetrije je izgubljen zbog kvara u čitanju konteksta"
    )


# ─── Jedinična strana popravke ───────────────────────────────────────────────

def test_U7_kanonski_uuid_prihvata_samo_ono_sto_Postgres_prihvata():
    """`_kanonski_uuid` vraća KANONSKI oblik, ne original.

    Python-ov `uuid.UUID` prihvata i zapise koje Postgres odbija (`urn:uuid:`
    prefiks, vitičaste zagrade, oblik bez crtica). Da se propušta original, ovaj
    isti defekt bi preživeo u užem obliku — INSERT bi opet pao na 22P02."""
    from shared.usage import _kanonski_uuid

    kanon = "12345678-1234-5678-1234-567812345678"
    for oblik in (kanon, kanon.upper(), kanon.replace("-", ""),
                  "{" + kanon + "}", "urn:uuid:" + kanon):
        assert _kanonski_uuid(oblik) == kanon, f"oblik {oblik!r} nije normalizovan"

    for los in ("PRED-42", "", "   ", "42", None, 42, [], {},
                "12345678-1234-5678-1234-56781234567"):
        assert _kanonski_uuid(los) is None, f"vrednost {los!r} je propuštena kao UUID"
