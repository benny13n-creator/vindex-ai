# -*- coding: utf-8 -*-
"""
Wave 9 / R2 — kanonska knjigovodstvena invarijanta naplate, nad PRAVIM PostgreSQL-om:

    uspesno_naplacene_operacije x jedinicna_cena + trenutni_bilans == pocetni_bilans
    i  trenutni_bilans >= 0

ŠTA VEĆ POSTOJI (i zato se OVDE NE PONAVLJA)
────────────────────────────────────────────
`tests/test_beta_gate_credit_race_postgres.py` (migracija 107) pokriva:
  • `deduct_n_credits` direktno: T1-T6, NULL/negativan iznos, drenaža do nule,
  • scenarije A-E konkurentnih odbitaka (10x2, 100x3, 1x50, 10x50, mešane veličine),
  • ukršteni deduct/refund NA NIVOU RPC-a,
  • rollback / commit / kompenzujući povraćaj,
  • retry i duplikat zahteva na nivou RPC-a,
  • ACL i idempotenciju same migracije,
  • §12: `UsageService.consume` nad pravom bazom — cena 12 i cena 1, konkurentno,
  • INV-006: odbijena naplata ne troši mesečnu kvotu.

`tests/test_atomic_usage_counters_postgres.py` (migracija 108) pokriva dnevni i
mesečni brojač i njihovu konkurentnost — ali u SVOJOJ bazi, bez migracije 107.

ŠTA OVAJ FAJL DODAJE (rupe, ne duplikati)
─────────────────────────────────────────
  A) Matrica kvara kroz PRAVI `UsageService` sloj: izuzetak / timeout / 5xx /
     malformisan odgovor / BLOCK odbrambenog zida — svaki mora vratiti TAČNO
     ono što je naplaćeno. Postojeći testovi mere povraćaj samo na nivou RPC-a.
  B) Konkurentni MEŠANI ishodi (deo uspe, deo padne pa vrati) — invarijanta pod
     opterećenjem kad se naplate i povraćaji preklapaju kroz Python sloj.
  C) Svi padnu: N parova consume+refund → bilans mora biti IDENTIČAN početnom.
     Ovo je detektor izgubljenog ažuriranja na povraćajnoj strani, kroz
     `UsageService.refund`, gde živi logika razrešavanja iznosa (multiplier).
  D) Tačna granica bilansa kroz Python sloj (cena-1 / cena / cena+1).
     Postojeći testovi granicu mere na nivou RPC-a (T1-T3), a kroz `consume`
     samo grubo (5 < 12 i 20 >= 12).
  E) Cena 0 i bilans 0 — oblik koji migracija 111 pravi. Nijedan postojeći
     test ne meri da funkcija cene 0 ne dira bilans pod opterećenjem.
  F) MIGRACIJE 107 I 108 U ISTOJ BAZI, kroz `consume`: dnevni limit odbija bez
     naplate. Nijedan postojeći test ne instalira obe migracije zajedno, pa
     interakcija dnevne kapije i naplate do sada nije bila dokazana.
  G) Dokumentovana asimetrija: odbijena naplata IPAK troši dnevni slot
     (brojanje se dešava PRE naplate, shared/usage.py). Zakucano da bi buduća
     promena bila svesna odluka, ne slučajnost.
  H) Retry posle 5xx: naplata → povraćaj → ponovna naplata → uspeh.
  I) Duplikat klika sa bilansom tačno za dve operacije.
  K) Ukršteni consume/refund kroz PRAVI Python sloj (postojeći test to radi
     sirovim RPC pozivima, zaobilazeći razrešavanje iznosa u `refund`).
  L) Bilans 0 pod konkurentnim opterećenjem — svaki zahtev 402, ništa ne mrda.

Ne uvodi se nikakva nova billing arhitektura. Koristi se isključivo
`deduct_n_credits` / `refund_n_credits` iz migracije 107 i
`increment_feature_usage` / `increment_monthly_usage` iz 108, izvršene sa diska.
"""
import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_107 = REPO_ROOT / "migrations" / "107_beta_gate_credit_race_closure.sql"
MIGRATION_108 = REPO_ROOT / "migrations" / "108_atomic_usage_counters.sql"

psycopg = pytest.importorskip("psycopg", reason="psycopg nije instaliran — dokaz nad pravom bazom preskočen")


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Otkrivanje servera (isti obrazac kao postojeći PG testovi) ──────────────

def _candidate_dsns():
    env = os.getenv("VINDEX_TEST_PG_DSN")
    if env:
        return [env]
    return [
        "host=127.0.0.1 port=55433 user=postgres dbname=postgres",
        "host=127.0.0.1 port=55432 user=postgres dbname=postgres",
        "host=127.0.0.1 port=5432 user=postgres dbname=postgres",
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
        "127.0.0.1:55433, 127.0.0.1:55432, 127.0.0.1:5432) — dokaz invarijante naplate preskočen"
    ),
)


_SCHEMA = """
CREATE TABLE public.user_credits (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL UNIQUE,
  credits_remaining INTEGER NOT NULL DEFAULT 15,
  mesecno_korisceno INTEGER DEFAULT 0,
  mesec             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE public.feature_usage (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL,
  feature_key       TEXT NOT NULL,
  dan               DATE NOT NULL,
  mesec             TEXT,
  broj_koriscenja   INTEGER NOT NULL DEFAULT 0,
  krediti_potroseni DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, feature_key, dan)
);
"""


@pytest.fixture(scope="module")
def pg_dsn():
    """Izolovana baza sa OBE naplatne migracije (107 + 108), izvršene sa diska."""
    dbname = f"vindex_w9inv_{uuid.uuid4().hex[:12]}"
    admin = _SERVER_DSN

    with psycopg.connect(admin, autocommit=True) as c:
        for role in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{dbname}"')

    _info = psycopg.conninfo.conninfo_to_dict(admin)
    _info["dbname"] = dbname
    target = psycopg.conninfo.make_conninfo(**_info)
    assert dbname in target, "test baza ne sme biti admin baza"

    try:
        with psycopg.connect(target, autocommit=True) as c:
            c.execute(_SCHEMA)
            c.execute(MIGRATION_107.read_text(encoding="utf-8"))
            c.execute(MIGRATION_108.read_text(encoding="utf-8"))
        yield target
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (dbname,))
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')


def _balance(dsn, uid):
    with psycopg.connect(dsn, autocommit=True) as c:
        r = c.execute("SELECT credits_remaining FROM public.user_credits WHERE user_id=%s", (uid,)).fetchone()
    return r[0] if r else None


def _daily(dsn, uid, feature):
    with psycopg.connect(dsn, autocommit=True) as c:
        r = c.execute(
            "SELECT broj_koriscenja, krediti_potroseni FROM public.feature_usage "
            "WHERE user_id=%s AND feature_key=%s AND dan=%s",
            (uid, feature, date.today()),
        ).fetchone()
    return r if r else (0, 0.0)


@pytest.fixture
def make_user(pg_dsn):
    def _make(balance: int) -> str:
        uid = str(uuid.uuid4())
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            c.execute(
                "INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s,%s)",
                (uid, balance),
            )
        return uid
    return _make


# ═══════════════════════════════════════════════════════════════════════════
# Shim — jedini most ka bazi. Nema mockovane naplate.
# ═══════════════════════════════════════════════════════════════════════════

class _PgShim:
    """Minimalni stand-in za Supabase klijenta: `.rpc(...)` ide na prave
    funkcije iz 107/108, a `.table("feature_usage")` na pravu tabelu.

    Namerno podržava SAMO ono što `UsageService.consume`/`refund` stvarno
    koriste. Sve ostalo diže AssertionError umesto da tiho prođe — tiho
    prolaženje je tačno ono što je omogućilo da ranjivo telo funkcije živi u
    produkciji dok je CI bio zelen.
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

    def __init__(self, dsn):
        self._dsn = dsn
        self.rpc_log = []

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
        assert name == "feature_usage", (
            f"naplatni put je dodirnuo tabelu {name!r} koju ovaj dokaz ne pokriva"
        )
        return _FeatureUsageQuery(self._dsn)


class _FeatureUsageQuery:
    """Minimalan PostgREST-oblik lanac koji koriste `_get_usage_row` i
    `_get_monthly_count`: .select(...).eq(...).eq(...)[.maybe_single()].execute()"""

    _DOZVOLJENE = {"user_id", "feature_key", "dan", "mesec"}

    def __init__(self, dsn):
        self._dsn = dsn
        self._cols = "*"
        self._filters = []
        self._single = False

    def select(self, what):
        self._cols = what
        return self

    def eq(self, col, val):
        assert col in self._DOZVOLJENE, f"nepodržan filter {col!r}"
        self._filters.append((col, val))
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        where = " AND ".join(f"{c} = %s" for c, _ in self._filters) or "true"
        sql = f"SELECT {self._cols} FROM public.feature_usage WHERE {where}"
        with psycopg.connect(self._dsn, autocommit=True) as c:
            cur = c.execute(sql, [v for _, v in self._filters])
            imena = [d.name for d in cur.description]
            rows = [dict(zip(imena, r)) for r in cur.fetchall()]
        return SimpleNamespace(data=(rows[0] if rows else None) if self._single else rows)


@pytest.fixture
def billing(pg_dsn, monkeypatch):
    """Ožičava `UsageService.consume`/`refund` na pravu bazu.

    `cooldown_seconds` je svuda None u politikama niže — `_claim_cooldown_atomic`
    je zaseban mehanizam sa sopstvenim dokazima i nije predmet ove invarijante.
    """
    import shared.deps as deps
    import shared.usage as usage

    shim = _PgShim(pg_dsn)
    monkeypatch.setattr(deps, "_get_supa", lambda: shim)
    # `shared/usage.py` drži sopstvenu referencu (from-import), pa patch nad
    # `shared.deps` sam po sebi ne pokriva `_increment_usage`/`_get_usage_row`.
    monkeypatch.setattr(usage, "_get_supa", lambda: shim)
    monkeypatch.setattr(usage, "_is_founder", lambda *a, **k: False)
    monkeypatch.setattr(deps, "_is_founder", lambda *a, **k: False)
    monkeypatch.setattr(usage, "_get_credits", lambda uid: _balance(pg_dsn, uid) or 0)

    async def _noop_log(*a, **k):
        return None

    monkeypatch.setattr(usage, "_log_usage_event", _noop_log)

    def _policy(krediti, multiplier=1, dnevni_limit=None, mesecni_limit=None):
        async def _get(_feature):
            return {
                "krediti": krediti, "credit_multiplier": multiplier,
                "dnevni_limit": dnevni_limit, "mesecni_limit": mesecni_limit,
                "cooldown_seconds": None, "ai_model": "gpt-4o",
                "estimated_cost_usd": None,
            }
        return _get

    return SimpleNamespace(dsn=pg_dsn, policy=_policy, shim=shim, monkeypatch=monkeypatch)


FEATURE = "ai_pravna_pitanja"


def _proveri_invarijantu(dsn, uid, pocetni, uspesnih, cena, oznaka):
    trenutni = _balance(dsn, uid)
    assert trenutni >= 0, f"{oznaka}: bilans je otišao u minus ({trenutni})"
    assert uspesnih * cena + trenutni == pocetni, (
        f"{oznaka}: knjigovodstvo ne štima — {uspesnih} x {cena} + {trenutni} != {pocetni}"
    )
    return trenutni


# ═══════════════════════════════════════════════════════════════════════════
# A) MATRICA KVARA kroz pravi UsageService sloj
# ═══════════════════════════════════════════════════════════════════════════
# Obrazac koji produkcija koristi: naplati, uradi posao, na kvar vrati tačan
# iznos (`routers/precedenti.py:178`, `routers/evidence.py:485-487`).
# Ovde se kvar ubacuje NAMERNO, a povraćaj mora biti egzaktan za svaki tip.

class _TimeoutKvar(Exception):
    """Provajder nije odgovorio u roku."""


class _PetXXKvar(Exception):
    """Provajder je vratio 5xx."""


class _MalformisanOdgovor(Exception):
    """Odgovor se ne parsira (JSON/šema)."""


class _FirewallBlock(Exception):
    """Odbrambeni zid odgovora je blokirao izlaz pre isporuke korisniku."""


_TIPOVI_KVARA = [
    ("obican_izuzetak", RuntimeError("neočekivana greška u obradi")),
    ("timeout", _TimeoutKvar("čekanje na model isteklo")),
    ("peti_xx", _PetXXKvar("502 Bad Gateway")),
    ("malformisan", _MalformisanOdgovor("model vratio nevalidan JSON")),
    ("firewall_block", _FirewallBlock("BLOCK — odgovor nije isporučen")),
]


@pytest.mark.anyio
@pytest.mark.parametrize("oznaka,kvar", _TIPOVI_KVARA, ids=[t[0] for t in _TIPOVI_KVARA])
async def test_A_svaki_tip_kvara_vraca_tacno_naplaceno(billing, make_user, oznaka, kvar):
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(2, 6))  # 12 kredita

    uid = make_user(60)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija", multiplier=6)
    assert _balance(billing.dsn, uid) == 48, f"{oznaka}: naplata se nije desila, test ne meri ništa"

    try:
        raise kvar
    except Exception:
        # Bezbedan oblik poziva: vrati TAČNO ono što je consume naplatio.
        await usage.UsageService.refund(uid, "advokat@vindex.rs", "strategija", credits=12)

    _proveri_invarijantu(billing.dsn, uid, 60, uspesnih=0, cena=12, oznaka=oznaka)
    assert _balance(billing.dsn, uid) == 60


@pytest.mark.anyio
async def test_A_ng_uspesan_posao_zadrzava_naplatu(billing, make_user):
    """Bez ovoga bi matrica iznad bila zadovoljena i time da se NIKAD ne naplati."""
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(2, 6))

    uid = make_user(60)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija", multiplier=6)
    _proveri_invarijantu(billing.dsn, uid, 60, uspesnih=1, cena=12, oznaka="uspeh")
    assert _balance(billing.dsn, uid) == 48


# ═══════════════════════════════════════════════════════════════════════════
# B) KONKURENTNI MEŠANI ISHODI
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_B_konkurentni_mesani_ishodi_odrzavaju_invarijantu(billing, make_user):
    """30 istovremenih zahteva na bilansu koji finansira najviše 12: svaki
    treći „padne" posle naplate i vrati kredite. Naplate i povraćaji se
    preklapaju u vremenu — tačno interleaving koji postojeći testovi ne rade
    kroz Python sloj."""
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(5, 1))

    POCETNI, CENA = 60, 5
    uid = make_user(POCETNI)

    async def zahtev(i):
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
        except HTTPException as e:
            return "402" if e.status_code == 402 else f"HTTP{e.status_code}"
        if i % 3 == 0:
            await usage.UsageService.refund(uid, "advokat@vindex.rs", FEATURE, credits=CENA)
            return "VRACENO"
        return "NAPLACENO"

    ishodi = await asyncio.gather(*[zahtev(i) for i in range(30)])

    assert all(r in ("402", "VRACENO", "NAPLACENO") for r in ishodi), f"neočekivano: {set(ishodi)}"
    naplaceno = ishodi.count("NAPLACENO")
    odobreno = naplaceno + ishodi.count("VRACENO")

    assert odobreno >= 1, "nijedan zahtev nije prošao — test ne meri ništa"
    # UKUPAN broj odobrenih NIJE ograničen početnim bilansom: povraćaji vraćaju
    # kredite u opticaj i finansiraju naredne zahteve. Ograničene su samo
    # ZADRŽANE naplate — one su jedine koje su trajno uzele novac.
    assert naplaceno * CENA <= POCETNI, (
        f"{naplaceno} zadržanih naplata x {CENA} prelazi početni bilans {POCETNI}"
    )
    _proveri_invarijantu(billing.dsn, uid, POCETNI, naplaceno, CENA, "mesani")


# ═══════════════════════════════════════════════════════════════════════════
# C) SVI PADNU → bilans mora biti IDENTIČAN početnom
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_C_kad_svi_padnu_bilans_je_netaknut(billing, make_user):
    """Detektor izgubljenog ažuriranja na POVRAĆAJNOJ strani, kroz
    `UsageService.refund` (gde se razrešava iznos), a ne sirovim RPC pozivom.
    Ako povraćaj izgubi ijedno ažuriranje, korisnik trajno gubi kredite za
    posao koji nikad nije dobio."""
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(1, 1))

    POCETNI, CENA, N = 40, 1, 24
    uid = make_user(POCETNI)

    async def par(_i):
        await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
        await usage.UsageService.refund(uid, "advokat@vindex.rs", FEATURE, credits=CENA)

    await asyncio.gather(*[par(i) for i in range(N)])

    assert _balance(billing.dsn, uid) == POCETNI, (
        f"{N} parova naplata+povraćaj ostavilo bilans {_balance(billing.dsn, uid)} "
        f"umesto {POCETNI} — kredit je nestao ili je iskovan"
    )
    _proveri_invarijantu(billing.dsn, uid, POCETNI, uspesnih=0, cena=CENA, oznaka="svi_padnu")


# ═══════════════════════════════════════════════════════════════════════════
# D) TAČNA GRANICA BILANSA kroz Python sloj
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
@pytest.mark.parametrize("bilans,prolazi", [(11, False), (12, True), (13, True)])
async def test_D_granica_bilansa(billing, make_user, bilans, prolazi):
    """Cena je 12. Bilans 11 mora 402 bez ijedne izmene; 12 mora proći i
    ostaviti tačno 0; 13 mora proći i ostaviti tačno 1."""
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(2, 6))

    uid = make_user(bilans)

    if prolazi:
        preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")
        assert preostalo == bilans - 12
        _proveri_invarijantu(billing.dsn, uid, bilans, 1, 12, f"granica-{bilans}")
    else:
        with pytest.raises(HTTPException) as exc:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")
        assert exc.value.status_code == 402
        _proveri_invarijantu(billing.dsn, uid, bilans, 0, 12, f"granica-{bilans}")


@pytest.mark.anyio
async def test_D_granica_pod_opterecenjem_finansira_tacno_jedan(billing, make_user):
    """Bilans tačno za JEDNU operaciju, 25 istovremenih zahteva."""
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(2, 6))

    uid = make_user(12)

    async def one():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija")
            return "OK"
        except HTTPException as e:
            return f"HTTP{e.status_code}"

    ishodi = await asyncio.gather(*[one() for _ in range(25)])
    assert ishodi.count("OK") == 1, f"tačno jedan sme proći, prošlo {ishodi.count('OK')}"
    assert set(ishodi) <= {"OK", "HTTP402"}, f"neočekivani statusi: {set(ishodi)}"
    _proveri_invarijantu(billing.dsn, uid, 12, 1, 12, "granica-opterecenje")


# ═══════════════════════════════════════════════════════════════════════════
# E) CENA 0 — oblik koji pravi migracija 111
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_E_cena_nula_ne_dira_bilans_ni_pri_nuli_kredita(billing, make_user):
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(0, 1))

    uid = make_user(0)
    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")
    assert preostalo == 0
    assert "deduct_n_credits" not in billing.shim.rpc_log
    _proveri_invarijantu(billing.dsn, uid, 0, 0, 0, "cena-nula")


@pytest.mark.anyio
async def test_E_cena_nula_pod_opterecenjem_ne_curi(billing, make_user):
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(0, 1))

    uid = make_user(30)

    async def one():
        return await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")

    ishodi = await asyncio.gather(*[one() for _ in range(40)])
    assert all(r == 30 for r in ishodi), f"cena 0 je ipak nešto naplatila: {sorted(set(ishodi))}"
    _proveri_invarijantu(billing.dsn, uid, 30, 0, 0, "cena-nula-opterecenje")


@pytest.mark.anyio
async def test_E_povracaj_za_cenu_nula_ne_kuje_kredit(billing, make_user):
    """`refund` sa cenom 0 mora biti no-op — inače bi svaki neuspeh besplatne
    funkcije poklanjao kredit."""
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(0, 1))

    uid = make_user(7)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")
    await usage.UsageService.refund(uid, "advokat@vindex.rs", "confidence_audit")
    assert _balance(billing.dsn, uid) == 7, "povraćaj za besplatnu funkciju je iskovao kredit"


# ═══════════════════════════════════════════════════════════════════════════
# F) MIGRACIJE 107 + 108 ZAJEDNO — dnevni limit odbija BEZ naplate
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_F_dnevni_limit_odbija_bez_naplate_pod_opterecenjem(billing, make_user):
    """Nijedan postojeći test ne instalira 107 i 108 u istu bazu, pa dosad nije
    bilo dokazano da dnevna kapija (108) odbija PRE naplate (107) i da odbijen
    zahtev ne skida kredite. Bilans je namerno velik — kapija mora biti dnevni
    limit, ne novac."""
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(2, 1, dnevni_limit=3))

    POCETNI, CENA, LIMIT = 100, 2, 3
    uid = make_user(POCETNI)
    feature = f"limitiran_{uuid.uuid4().hex[:8]}"

    async def one():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", feature)
            return "OK"
        except HTTPException as e:
            return f"HTTP{e.status_code}"

    ishodi = await asyncio.gather(*[one() for _ in range(20)])
    odobreno = ishodi.count("OK")

    assert odobreno == LIMIT, f"dnevni limit {LIMIT} propustio {odobreno}"
    assert set(ishodi) <= {"OK", "HTTP429"}, f"neočekivani statusi: {set(ishodi)}"
    assert _daily(billing.dsn, uid, feature)[0] == LIMIT
    _proveri_invarijantu(billing.dsn, uid, POCETNI, odobreno, CENA, "dnevni-limit")
    assert _balance(billing.dsn, uid) == POCETNI - LIMIT * CENA


# ═══════════════════════════════════════════════════════════════════════════
# G) DOKUMENTOVANA ASIMETRIJA — zakucana namerno, ne slučajno
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_G_odbijena_naplata_IPAK_trosi_dnevni_slot_DOKUMENTOVANO(billing, make_user):
    """`shared/usage.py` broji upotrebu PRE naplate (migracija 108, nalaz B2),
    uz izričito obrazloženje: za funkcije cene 0 dnevni brojač je JEDINA zaštita
    budžeta, pa mora biti autoritativan i ići prvi. Posledica je da zahtev koji
    kasnije padne na 402 ipak potroši dnevni slot — konzervativno na štetu
    korisnika, ne firme.

    Ovaj test NE tvrdi da je to poželjno; zakucava ga da bi promena bila svesna
    odluka. Novac je pritom netaknut — to je deo koji mora da važi."""
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(1, 1, dnevni_limit=10))

    uid = make_user(1)
    feature = f"asimetrija_{uuid.uuid4().hex[:8]}"

    await usage.UsageService.consume(uid, "advokat@vindex.rs", feature)
    assert _balance(billing.dsn, uid) == 0

    with pytest.raises(HTTPException) as exc:
        await usage.UsageService.consume(uid, "advokat@vindex.rs", feature)
    assert exc.value.status_code == 402

    broj, potroseno = _daily(billing.dsn, uid, feature)
    assert broj == 2, (
        f"dnevni brojač je {broj}; dokumentovano ponašanje je 2 (broji se pre naplate). "
        "Ako je sada 1, redosled u consume() je promenjen — proveri da li je to bila svesna odluka."
    )
    assert potroseno == 2.0, "brojač beleži nameravanu, ne stvarno naplaćenu potrošnju"
    _proveri_invarijantu(billing.dsn, uid, 1, uspesnih=1, cena=1, oznaka="asimetrija")
    assert _balance(billing.dsn, uid) == 0, "novac je netaknut — to je deo koji MORA da važi"


# ═══════════════════════════════════════════════════════════════════════════
# H) RETRY POSLE 5xx
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_H_retry_posle_5xx_naplacuje_tacno_jednom(billing, make_user):
    """Prvi pokušaj: naplaćeno pa vraćeno (5xx). Drugi: naplaćeno i uspelo.
    Ukupno mora otići TAČNO jedna cena, ne dve."""
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(3, 1))

    POCETNI, CENA = 20, 3
    uid = make_user(POCETNI)

    await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
    assert _balance(billing.dsn, uid) == POCETNI - CENA
    await usage.UsageService.refund(uid, "advokat@vindex.rs", FEATURE, credits=CENA)
    assert _balance(billing.dsn, uid) == POCETNI

    await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
    _proveri_invarijantu(billing.dsn, uid, POCETNI, uspesnih=1, cena=CENA, oznaka="retry")


@pytest.mark.anyio
async def test_H_retry_bura_od_pet_pokusaja_ostavlja_jednu_cenu(billing, make_user):
    """Četiri neuspela pokušaja (svaki naplati pa vrati) i peti uspešan."""
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(3, 1))

    POCETNI, CENA = 20, 3
    uid = make_user(POCETNI)

    for _ in range(4):
        await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
        await usage.UsageService.refund(uid, "advokat@vindex.rs", FEATURE, credits=CENA)
    await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)

    _proveri_invarijantu(billing.dsn, uid, POCETNI, uspesnih=1, cena=CENA, oznaka="retry-bura")


# ═══════════════════════════════════════════════════════════════════════════
# I) DUPLIKAT KLIKA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_I_duplikat_klika_ne_moze_da_prekoraci_bilans(billing, make_user):
    """Proizvod NEMA ključ idempotentnosti na naplati (zakucano u
    test_retry_charges_twice_by_design_and_stays_consistent) — dva klika su dve
    naplative operacije. Zaštita koja mora da važi je da bilans ne može biti
    prekoračen: bilans tačno za dve, deset istovremenih klikova → tačno dve."""
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(4, 1))

    POCETNI, CENA = 8, 4
    uid = make_user(POCETNI)

    async def klik():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
            return "OK"
        except HTTPException as e:
            return f"HTTP{e.status_code}"

    ishodi = await asyncio.gather(*[klik() for _ in range(10)])
    assert ishodi.count("OK") == 2, f"bilans za dve operacije propustio {ishodi.count('OK')}"
    _proveri_invarijantu(billing.dsn, uid, POCETNI, 2, CENA, "duplikat")
    assert _balance(billing.dsn, uid) == 0


# ═══════════════════════════════════════════════════════════════════════════
# K) UKRŠTENI consume/refund kroz PRAVI Python sloj
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_K_ukrsteni_consume_i_refund_kroz_pravi_sloj(billing, make_user):
    """Postojeći ekvivalent (`test_concurrent_deduct_and_refund_cannot_lose_an_update`)
    poziva RPC direktno i time preskače razrešavanje iznosa u
    `UsageService.refund` — tačno mesto gde je živela greška CREDIT-REFUND-002
    (povraćaj po registry multiplieru za naplatu sa multiplier=1, kovanje 5
    kredita po kvaru). Ovde se oba puta voze kroz pravi Python sloj, istovremeno."""
    from fastapi import HTTPException
    import shared.usage as usage
    # Registry kaže multiplier 6, pozivalac naplaćuje sa multiplier=1 —
    # obrazac iz routers/strategija.py.
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(1, 6))

    POCETNI, CENA = 50, 1
    uid = make_user(POCETNI)
    naplaceno = {"n": 0}
    kljucanica = asyncio.Lock()

    async def naplati():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija", multiplier=1)
        except HTTPException:
            return
        async with kljucanica:
            naplaceno["n"] += 1

    async def vrati():
        # Bezbedan oblik: eksplicitan iznos, isti koji je naplaćen.
        await usage.UsageService.consume(uid, "advokat@vindex.rs", "strategija", multiplier=1)
        await usage.UsageService.refund(uid, "advokat@vindex.rs", "strategija", credits=CENA)

    poslovi = [naplati() for _ in range(15)] + [vrati() for _ in range(15)]
    await asyncio.gather(*poslovi, return_exceptions=False)

    _proveri_invarijantu(billing.dsn, uid, POCETNI, naplaceno["n"], CENA, "ukrsteno")


# ═══════════════════════════════════════════════════════════════════════════
# L) BILANS 0 POD OPTEREĆENJEM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_L_bilans_nula_odbija_sve_i_nista_ne_menja(billing, make_user):
    from fastapi import HTTPException
    import shared.usage as usage
    billing.monkeypatch.setattr(usage, "get_policy", billing.policy(1, 1))

    uid = make_user(0)

    async def one():
        try:
            await usage.UsageService.consume(uid, "advokat@vindex.rs", FEATURE)
            return "OK"
        except HTTPException as e:
            return f"HTTP{e.status_code}"

    ishodi = await asyncio.gather(*[one() for _ in range(20)])
    assert set(ishodi) == {"HTTP402"}, f"bilans 0 je propustio zahtev: {set(ishodi)}"
    _proveri_invarijantu(billing.dsn, uid, 0, 0, 1, "bilans-nula")
    assert _balance(billing.dsn, uid) == 0
