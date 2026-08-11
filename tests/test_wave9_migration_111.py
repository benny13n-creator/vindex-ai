# -*- coding: utf-8 -*-
"""
Wave 9 / R1 — migracija 111 (`migrations/111_phantom_ai_charges.sql`) izvršena
nad STVARNIM PostgreSQL-om, ne pročitana kao tekst.

ZAŠTO OVAJ FAJL POSTOJI PORED `tests/test_phantom_ai_charges.py`
────────────────────────────────────────────────────────────────
`test_phantom_ai_charges.py` je STATIČKA provera: čita `.sql` kao string i
regexom tvrdi da se u njemu pojavljuju/ne pojavljuju određeni ključevi. Takva
provera ne može da uhvati:

  • kolonu koja u `feature_registry` ne postoji (migracija bi pukla na
    produkciji, a tekst bi izgledao savršeno),
  • kršenje CHECK ograničenja (`minimum_plan IN ('basic','professional',
    'enterprise')`),
  • neidempotentnost (drugo pokretanje menja stanje),
  • stvarni obim izmene — koliko je redova zaista dirnuto.

Ovaj fajl izvršava `.sql` DOSLOVNO, sa diska, nad pravim Postgresom, nad šemom
`feature_registry` rekonstruisanom iz migracija 064/065/069/070/071 ovog repoa,
useljenom stvarnim pre-111 produkcionim vrednostima iz `064_feature_registry.sql`.

Nikad ne postoji kopija SQL-a u testu — ako se `.sql` pokvari, test pada.

OTKRIVANJE SERVERA
──────────────────
Isti mehanizam koji već koriste `tests/test_beta_gate_credit_race_postgres.py`
i `tests/test_atomic_usage_counters_postgres.py` (`$VINDEX_TEST_PG_DSN`, pa
127.0.0.1:55433, 55432, 5432). Preskakanje je činjenica o okruženju, nikad
način da se izbegne tvrdnja koja pada.
"""
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
MIGRATION_111 = MIGRATIONS_DIR / "111_phantom_ai_charges.sql"
MIGRATION_107 = MIGRATIONS_DIR / "107_beta_gate_credit_race_closure.sql"
MIGRATION_108 = MIGRATIONS_DIR / "108_atomic_usage_counters.sql"

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
        # Wave 10 — FALLBACK NA 5432 UKLONJEN.
        #
        # Izmereno: 5432 na ovoj mašini je TRAJAN PostgreSQL servis koji sluša na
        # 0.0.0.0 i nosi stvarne podatke. Ovi testovi PRAVE i BRIŠU baze — na
        # throwaway klasteru je to bezopasno, na trajnom servisu nije.
        # „Loopback" nije isto što i „potrošno".
        #
        # Posledica uklanjanja: ako klasteri nisu podignuti, test se preskače
        # umesto da tiho koristi pogrešnu bazu. Podizanje je jedna komanda:
        #     python scripts/test_db.py up
        # (v. docs/beta_war/TEST_DB_BOOTSTRAP.md)
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
        "127.0.0.1:55433, 127.0.0.1:55432, 127.0.0.1:5432) — dokaz migracije 111 preskočen"
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# Rekonstrukcija šeme `feature_registry` iz migracija ovog repoa
# ═══════════════════════════════════════════════════════════════════════════
# Definicije kolona su prepisane iz:
#   064_feature_registry.sql:18-32              (CREATE TABLE)
#   065_feature_registry_v2.sql:20-29           (ALTER ... ADD COLUMN)
#   069_feature_registry_credit_multiplier.sql:20-21
#   070_feature_registry_feature_type.sql:38-41
#   071_business_groups.sql:81-82
#
# Namerno izostavljeno, uz razlog:
#   • RLS politike (064:44-49) — koriste `auth.role()`, šema `auth` postoji samo
#     u Supabase-u. Ne utiču na semantiku UPDATE-a koji migracija 111 izvršava
#     (migracija se pokreće kao vlasnik u SQL Editor-u).
#   • FK `business_group_id -> business_groups(id)` (071:82) — tabela
#     `business_groups` nije predmet ove migracije; kolona je zadržana kao UUID
#     da bi broj i imena kolona bili tačni.
#
# `test_sema_pokriva_sve_kolone_deklarisane_u_migracijama` niže dokazuje da
# ova rekonstrukcija nije izmišljena: parsira SVE migracije u repou i traži
# kolonu koja ovde nedostaje.
_FEATURE_REGISTRY_DDL = """
CREATE TABLE public.feature_registry (
    feature_key         text PRIMARY KEY,
    naziv               text NOT NULL,
    kategorija          text NOT NULL DEFAULT 'ostalo',
    minimum_plan        text CHECK (minimum_plan IN ('basic', 'professional', 'enterprise') OR minimum_plan IS NULL),
    addon               text,
    krediti             numeric NOT NULL DEFAULT 0,
    krediti_po_minutu   numeric,
    dnevni_limit        integer,
    mesecni_limit       integer,
    ai_model            text,
    aktivno             boolean NOT NULL DEFAULT true,
    opis                text,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    updated_by          text,
    cooldown_seconds    integer,
    priority            text NOT NULL DEFAULT 'MEDIUM'
        CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
    estimated_cost_usd  numeric,
    version             text NOT NULL DEFAULT 'v1',
    status              text NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'BETA', 'DEPRECATED', 'INTERNAL', 'COMING_SOON')),
    visible             text NOT NULL DEFAULT 'visible'
        CHECK (visible IN ('visible', 'hidden', 'internal', 'enterprise_only')),
    credit_multiplier   numeric NOT NULL DEFAULT 1,
    feature_type        text NOT NULL DEFAULT 'SUBSCRIPTION'
        CHECK (feature_type IN ('FOUNDATION', 'SUBSCRIPTION', 'ADDON', 'INTERNAL')),
    chargeable          boolean NOT NULL DEFAULT true,
    business_group_id   uuid
);
"""

# Tabele koje migracije 107/108 (naplata + brojači) traže — potrebne su samo
# za §R1.3, gde `UsageService.consume` mora da radi nad pravom bazom.
_BILLING_DDL = """
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


# ═══════════════════════════════════════════════════════════════════════════
# Stanje PRE migracije — prepisano iz `064_feature_registry.sql` (INSERT na
# liniji 87) i `065_feature_registry_v2.sql`. `chargeable`/`credit_multiplier`
# uzimaju podrazumevane vrednosti (true / 1) jer 070/069 ne diraju ove redove
# osim `firm_memory`/`knowledge_hygiene`.
# ═══════════════════════════════════════════════════════════════════════════
#
# (feature_key, naziv, kategorija, minimum_plan, addon, krediti,
#  krediti_po_minutu, dnevni_limit, mesecni_limit, ai_model, cooldown_seconds,
#  chargeable, credit_multiplier, estimated_cost_usd)
_SEED = [
    # ── GRUPA A — meta migracije 111 ──────────────────────────────────────
    ("confidence_audit", "AI Pouzdanost / Confidence Audit", "kvalitet",
     "professional", None, 1, None, None, None, "gpt-4o-mini", None, True, 1, 0.006),
    ("conflict_check", "Provera sukoba interesa", "compliance",
     "professional", None, 1, None, None, None, "gpt-4o-mini", None, True, 1, 0.006),
    ("da_wallet_risk_assessment", "Wallet Risk Assessment", "digital_assets",
     None, "digital_assets", 1, None, None, None, "gpt-4o", None, True, 1, 0.018),

    # ── GRUPA B — DELJENI ključevi, migracija 111 ih NE SME dirati ────────
    # Naplatna mesta ovih ključeva uključuju endpointe koji STVARNO zovu GPT.
    # krediti=0 ovde bi poklonio stvarnu potrošnju modela.
    ("case_commander", "Case Commander", "litigation",
     "professional", None, 2, None, None, None, "gpt-4o", None, True, 1, 0.036),
    ("zastarelost_guardian", "Zastarelost Guardian", "litigation",
     "professional", None, 1, None, None, None, "gpt-4o", None, True, 1, 0.018),

    # ── NAMERNO BESPLATNE POSLOVNE ODLUKE — krediti=0 ali chargeable=true ─
    # (070:29-34 izričito definiše ovu razliku)
    ("morning_briefing", "Jutarnji brifing", "dnevni_rad",
     "professional", None, 0, None, 5, None, "gpt-4o-mini", None, True, 1, 0.003),
    ("voice", "Glasovne komande", "ai_osnovno",
     "professional", None, 0, 2, None, None, "whisper+tts", 3, True, 1, 0.015),
    ("sudska_praksa", "Sudska praksa", "ai_osnovno",
     "basic", None, 0, None, None, None, "gpt-4o-mini", 2, True, 1, 0.003),

    # ── Kontrolni uzorak ostatka tabele (obim izmene) ─────────────────────
    ("ai_pravna_pitanja", "AI pravna pitanja", "ai_osnovno",
     "basic", None, 1, None, None, None, "gpt-4o", None, True, 1, 0.018),
    ("strategija", "Strategija predmeta", "litigation",
     "professional", None, 2, None, None, None, "gpt-4o", None, True, 6, 0.108),
    # Presedan iz 070:62-66 — već popravljen ključ; migracija 111 ga ne pominje.
    ("firm_memory", "Memorija kancelarije", "kvalitet",
     "professional", None, 0, None, None, None, None, None, False, 1, None),
]

_SEED_SQL = """
INSERT INTO public.feature_registry
  (feature_key, naziv, kategorija, minimum_plan, addon, krediti,
   krediti_po_minutu, dnevni_limit, mesecni_limit, ai_model, cooldown_seconds,
   chargeable, credit_multiplier, estimated_cost_usd, updated_by)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'seed_pre_111')
"""

# Kolone koje se porede pri dokazu idempotencije. `updated_at` je namerno
# izostavljen — migracija ga postavlja na now() na svakom pokretanju, što je
# očekivano i nije promena stanja.
_STATE_COLUMNS = [
    "feature_key", "naziv", "kategorija", "minimum_plan", "addon", "krediti",
    "krediti_po_minutu", "dnevni_limit", "mesecni_limit", "ai_model",
    "aktivno", "opis", "updated_by", "cooldown_seconds", "priority",
    "estimated_cost_usd", "version", "status", "visible", "credit_multiplier",
    "feature_type", "chargeable", "business_group_id",
]


# ═══════════════════════════════════════════════════════════════════════════
# Fikstura — izolovana baza po modulu, sveža `feature_registry` po testu
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def pg_dsn():
    dbname = f"vindex_mig111_{uuid.uuid4().hex[:12]}"
    admin = _SERVER_DSN

    with psycopg.connect(admin, autocommit=True) as c:
        # Uloge na koje se pozivaju GRANT/REVOKE naredbe migracije 107.
        for role in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{dbname}"')

    # DSN se parsira, ne pattern-matchuje (isti razlog kao u
    # test_atomic_usage_counters_postgres.py: str.replace ne radi za URL DSN
    # i tiho ostavlja šemu u admin bazi).
    _info = psycopg.conninfo.conninfo_to_dict(admin)
    _info["dbname"] = dbname
    target = psycopg.conninfo.make_conninfo(**_info)
    assert dbname in target, "test baza ne sme biti admin baza"

    try:
        with psycopg.connect(target, autocommit=True) as c:
            c.execute(_FEATURE_REGISTRY_DDL)
            c.execute(_BILLING_DDL)
            c.execute(MIGRATION_107.read_text(encoding="utf-8"))
            c.execute(MIGRATION_108.read_text(encoding="utf-8"))
        yield target
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (dbname,))
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')


@pytest.fixture
def registry(pg_dsn):
    """Vraća `feature_registry` na tačno pre-111 produkciono stanje."""
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("TRUNCATE public.feature_registry")
        for row in _SEED:
            c.execute(_SEED_SQL, row)
    return pg_dsn


def _apply_111(dsn) -> None:
    """Izvršava artefakt sa diska, doslovno. Nikad kopija SQL-a u testu."""
    sql = MIGRATION_111.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql)


def _row(dsn, key) -> dict:
    with psycopg.connect(dsn, autocommit=True) as c:
        cur = c.execute(
            f"SELECT {', '.join(_STATE_COLUMNS)} FROM public.feature_registry WHERE feature_key = %s",
            (key,),
        )
        got = cur.fetchone()
        return dict(zip(_STATE_COLUMNS, got)) if got else None


def _snapshot(dsn) -> dict:
    with psycopg.connect(dsn, autocommit=True) as c:
        cur = c.execute(
            f"SELECT {', '.join(_STATE_COLUMNS)} FROM public.feature_registry ORDER BY feature_key"
        )
        return {r[0]: dict(zip(_STATE_COLUMNS, r)) for r in cur.fetchall()}


def _touched(dsn) -> set:
    with psycopg.connect(dsn, autocommit=True) as c:
        return {
            r[0] for r in c.execute(
                "SELECT feature_key FROM public.feature_registry "
                "WHERE updated_by = 'migration_111_phantom_ai_charges'"
            ).fetchall()
        }


# ═══════════════════════════════════════════════════════════════════════════
# R1.1(d) — kolone koje migracija dira MORAJU postojati u šemi
# ═══════════════════════════════════════════════════════════════════════════

def _columns_set_by_migration() -> set:
    """Izvlači imena kolona iz `SET ... =` klauzula migracije 111."""
    sql = MIGRATION_111.read_text(encoding="utf-8")
    # Ukloni komentare da regex ne pokupi kolone pomenute u proznom delu.
    body = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    cols = set()
    for stmt in re.findall(r"\bSET\b(.*?)\bWHERE\b", body, flags=re.S | re.I):
        for m in re.finditer(r"(\w+)\s*=", stmt):
            cols.add(m.group(1).lower())
    return cols


def test_migracija_dira_ocekivane_kolone():
    """Ako se skup kolona promeni, i provera postojanja niže mora da se osveži."""
    assert _columns_set_by_migration() == {
        "krediti", "chargeable", "ai_model", "minimum_plan",
        "cooldown_seconds", "updated_at", "updated_by",
    }


def test_sve_kolone_koje_migracija_dira_postoje_u_semi(pg_dsn):
    """Kolona koja ne postoji u `feature_registry` znači da migracija PUCA na
    produkciji, dok statička tekstualna provera i dalje prolazi."""
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        actual = {
            r[0] for r in c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='feature_registry'"
            ).fetchall()
        }
    missing = _columns_set_by_migration() - actual
    assert not missing, (
        f"migracija 111 postavlja kolone koje ne postoje u feature_registry: {sorted(missing)} "
        "— pokretanje na produkciji bi puklo sa 42703 (undefined_column)"
    )


def test_sema_pokriva_sve_kolone_deklarisane_u_migracijama(pg_dsn):
    """Dokaz da `_FEATURE_REGISTRY_DDL` nije izmišljen: parsira SVE migracije u
    repou i traži kolonu `feature_registry` koju ova rekonstrukcija nema."""
    declared = set()
    pat = re.compile(
        r"ALTER\s+TABLE\s+(?:public\.)?feature_registry\b(.*?);",
        flags=re.S | re.I,
    )
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for block in pat.findall(text):
            for m in re.finditer(r"ADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)", block, flags=re.I):
                declared.add(m.group(1).lower())

    with psycopg.connect(pg_dsn, autocommit=True) as c:
        actual = {
            r[0] for r in c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='feature_registry'"
            ).fetchall()
        }
    missing = declared - actual
    assert not missing, (
        f"migracije u repou dodaju kolone koje rekonstruisana šema nema: {sorted(missing)} "
        "— test bi lažno prolazio nad nepotpunom tabelom"
    )


def test_minimum_plan_basic_prolazi_check_ogranicenje(registry):
    """064:22 ograničava `minimum_plan` na ('basic','professional','enterprise')
    ili NULL. Migracija 111 upisuje 'basic' — ovo dokazuje da to ograničenje
    ne obara migraciju."""
    _apply_111(registry)
    assert _row(registry, "confidence_audit")["minimum_plan"] == "basic"


# ═══════════════════════════════════════════════════════════════════════════
# R1 — post-stanje za sva tri ključa grupe A
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("key", ["confidence_audit", "conflict_check", "da_wallet_risk_assessment"])
def test_grupa_A_vise_ne_naplacuje(registry, key):
    pre = _row(registry, key)
    assert pre["krediti"] == 1 and pre["chargeable"] is True and pre["ai_model"], \
        "seed nije u pre-111 stanju — test bi prolazio vakuumski"

    _apply_111(registry)

    post = _row(registry, key)
    assert post["krediti"] == 0, f"{key}: i dalje naplaćuje {post['krediti']} kredita"
    assert post["chargeable"] is False, f"{key}: chargeable mora biti false"
    assert post["ai_model"] is None, (
        f"{key}: Registry i dalje tvrdi model {post['ai_model']!r} za funkciju bez AI poziva — "
        "to je tačno kolona na koju se oslanjao masovni prolaz iz 73083099"
    )
    assert post["updated_by"] == "migration_111_phantom_ai_charges"


def test_confidence_audit_tarifna_kapija_i_cooldown(registry):
    pre = _row(registry, "confidence_audit")
    assert pre["minimum_plan"] == "professional" and pre["cooldown_seconds"] is None

    _apply_111(registry)

    post = _row(registry, "confidence_audit")
    assert post["minimum_plan"] == "basic", (
        "basic korisnik i dalje dobija 403 pri otvaranju ekrana Podešavanja"
    )
    assert post["cooldown_seconds"] == 5, "budžetski ventil (klauzula D) nije primenjen"


def test_obim_izmene_je_tacno_tri_reda(registry):
    """Ni jedan red više. `updated_by` je jedini marker kojim se obim meri."""
    _apply_111(registry)
    assert _touched(registry) == {
        "confidence_audit", "conflict_check", "da_wallet_risk_assessment",
    }
    assert len(_touched(registry)) == 3


# ═══════════════════════════════════════════════════════════════════════════
# R1.1(b) — KONTROLNA GRUPA B: najvažnija tvrdnja u fajlu
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("key,cena,model", [
    ("case_commander", 2, "gpt-4o"),
    ("zastarelost_guardian", 1, "gpt-4o"),
])
def test_deljeni_kljucevi_ostaju_NETAKNUTI(registry, key, cena, model):
    """`case_commander` i `zastarelost_guardian` su ISTI feature_key za AI i
    ne-AI endpointe. `krediti=0` ovde bi POKLONIO stvarnu GPT potrošnju —
    skuplja greška od one koja se ispravlja. Ako neko proširi IN listu
    migracije, ovaj test pada."""
    pre = _row(registry, key)
    _apply_111(registry)
    post = _row(registry, key)

    assert post["krediti"] == cena > 0, (
        f"{key}: cena je pala na {post['krediti']} — migracija je proširena na deljeni "
        "ključ i sada poklanja stvarnu GPT potrošnju besplatno"
    )
    assert post["chargeable"] is True, f"{key}: chargeable je oboren na false"
    assert post["ai_model"] == model, (
        f"{key}: ai_model obrisan, a taj ključ STVARNO zove {model}"
    )
    assert post == pre, f"{key}: red je izmenjen, a ne sme biti dirnut uopšte"


# ═══════════════════════════════════════════════════════════════════════════
# R1.1(c) — namerno besplatne poslovne odluke
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("key", ["morning_briefing", "voice", "sudska_praksa"])
def test_namerno_besplatne_odluke_ostaju_chargeable(registry, key):
    """070:29-34: `chargeable=false` znači „nema AI poziv uopšte", a NE
    „trenutno besplatno po ceni". Ova tri su drugo, ne prvo."""
    pre = _row(registry, key)
    _apply_111(registry)
    post = _row(registry, key)

    assert post["chargeable"] is True, (
        f"{key}: namerno besplatna poslovna odluka pretvorena u 'nema AI poziv' — "
        "to briše razliku koju 070 izričito definiše"
    )
    assert post["ai_model"] == pre["ai_model"], f"{key}: ai_model izmenjen"
    assert post == pre


def test_nijedan_drugi_red_nije_dirnut(registry):
    """Cela tabela osim tri ključa grupe A mora biti bajt-identična."""
    pre = _snapshot(registry)
    _apply_111(registry)
    post = _snapshot(registry)

    meta = {"confidence_audit", "conflict_check", "da_wallet_risk_assessment"}
    assert set(pre) == set(post), "migracija je dodala ili obrisala red"
    for key in sorted(set(pre) - meta):
        assert post[key] == pre[key], f"{key}: red van obima migracije je izmenjen"


# ═══════════════════════════════════════════════════════════════════════════
# R1.1(a) — IDEMPOTENCIJA
# ═══════════════════════════════════════════════════════════════════════════

def test_ponovno_pokretanje_daje_identicno_stanje(registry):
    _apply_111(registry)
    posle_prvog = _snapshot(registry)
    _apply_111(registry)
    posle_drugog = _snapshot(registry)
    assert posle_drugog == posle_prvog, (
        "drugo pokretanje migracije menja stanje — nije idempotentna kako zaglavlje tvrdi"
    )


def test_tri_uzastopna_pokretanja_ostaju_stabilna(registry):
    _apply_111(registry)
    ref = _snapshot(registry)
    for _ in range(2):
        _apply_111(registry)
    assert _snapshot(registry) == ref


def test_cooldown_klauzula_ne_snizava_vecu_postojecu_vrednost(registry):
    """Klauzula D nosi `AND (cooldown_seconds IS NULL OR cooldown_seconds < 5)`.
    Ako je admin preko Feature Console-a već postavio strožiji cooldown,
    migracija ga ne sme spustiti na 5."""
    with psycopg.connect(registry, autocommit=True) as c:
        c.execute("UPDATE public.feature_registry SET cooldown_seconds = 30 "
                  "WHERE feature_key = 'confidence_audit'")
    _apply_111(registry)
    assert _row(registry, "confidence_audit")["cooldown_seconds"] == 30, (
        "migracija je oborila strožiji cooldown koji je admin ranije postavio"
    )


def test_migracija_je_transakciona(registry):
    """Zaglavlje se oslanja na BEGIN/COMMIT — sve četiri klauzule su jedna
    jedinica. Bez toga bi delimičan pad ostavio Registry u mešanom stanju
    (npr. krediti=0 ali minimum_plan i dalje 'professional')."""
    sql = MIGRATION_111.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    assert re.search(r"^\s*BEGIN\s*;", body, flags=re.M | re.I), "nedostaje BEGIN"
    assert re.search(r"^\s*COMMIT\s*;", body, flags=re.M | re.I), "nedostaje COMMIT"


def test_migracija_ne_sadrzi_DDL(registry):
    """111 je čisto UPDATE migracija. DDL bi zahtevao drugačiju proceduru
    (zaključavanje tabele) i drugačiju proveru pre pokretanja."""
    sql = MIGRATION_111.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    for zabranjeno in ("ALTER TABLE", "DROP TABLE", "CREATE TABLE", "DELETE FROM", "TRUNCATE"):
        assert zabranjeno not in body.upper(), f"neočekivan DDL/DML u migraciji 111: {zabranjeno}"


# ═══════════════════════════════════════════════════════════════════════════
# R1.3 — phantom charge više nije moguć: STVARNI `UsageService.consume`
#        nad STVARNIM redom iz migrirane baze
# ═══════════════════════════════════════════════════════════════════════════
# Ovo nije mock politike. `shared/feature_registry.get_policy` čita
# `feature_registry` preko `_get_supa().table(...).select("*")`; shim niže
# rutira taj poziv na PRAVU tabelu ove test baze, posle stvarno izvršene
# migracije 111. Naplata ide na pravu `deduct_n_credits` iz migracije 107,
# brojač na pravu `increment_feature_usage` iz migracije 108.

class _RegistryAndRpcShim:
    """Minimalni stand-in za Supabase klijenta: samo
    `.table("feature_registry").select("*").execute()` i `.rpc(...)`."""

    _RPC = {
        "deduct_n_credits": "SELECT public.deduct_n_credits(%(p_user_id)s, %(p_n)s)",
        "refund_n_credits": "SELECT public.refund_n_credits(%(p_user_id)s, %(p_n)s)",
        "increment_monthly_usage": "SELECT public.increment_monthly_usage(%(p_user_id)s, %(p_mesec)s)",
        "increment_feature_usage": (
            "SELECT public.increment_feature_usage(%(p_user_id)s, %(p_feature)s, %(p_dan)s, "
            "%(p_mesec)s, %(p_credits)s, %(p_dnevni_limit)s)"
        ),
    }

    def __init__(self, dsn, rpc_log):
        self._dsn = dsn
        self.rpc_log = rpc_log

    def rpc(self, name, params):
        self.rpc_log.append(name)
        sql = self._RPC[name]
        dsn = self._dsn

        class _Call:
            def execute(self_inner):
                from types import SimpleNamespace
                with psycopg.connect(dsn, autocommit=True) as c:
                    val = c.execute(sql, params).fetchone()[0]
                return SimpleNamespace(data=val)

        return _Call()

    def table(self, name):
        assert name == "feature_registry", (
            f"consume() je dodirnuo tabelu {name!r} koju ovaj dokaz ne pokriva — "
            "dopuni shim umesto da tiho prođe"
        )
        dsn = self._dsn
        cols = _STATE_COLUMNS

        class _Sel:
            def select(self_inner, _what):
                return self_inner

            def execute(self_inner):
                from types import SimpleNamespace
                with psycopg.connect(dsn, autocommit=True) as c:
                    rows = c.execute(
                        f"SELECT {', '.join(cols)} FROM public.feature_registry"
                    ).fetchall()
                data = []
                for r in rows:
                    d = dict(zip(cols, r))
                    for num in ("krediti", "credit_multiplier", "estimated_cost_usd"):
                        if d.get(num) is not None:
                            d[num] = float(d[num])
                    data.append(d)
                return SimpleNamespace(data=data)

        return _Sel()


def _make_user(dsn, balance: int) -> str:
    uid = str(uuid.uuid4())
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.user_credits (user_id, credits_remaining) VALUES (%s,%s)",
                  (uid, balance))
    return uid


def _balance(dsn, uid) -> int:
    with psycopg.connect(dsn, autocommit=True) as c:
        r = c.execute("SELECT credits_remaining FROM public.user_credits WHERE user_id=%s",
                      (uid,)).fetchone()
    return r[0] if r else None


@pytest.fixture
def consume_stack(registry, monkeypatch):
    """Ožičava `UsageService.consume` na PRAVU bazu i PRAVI red iz Registry-ja.

    Vraća objekat sa: `.rpc_log` (imena RPC-jeva koje je consume pozvao),
    `.cooldown_calls` (argumenti cooldown gejta), `.telemetry` (argumenti
    telemetrije). Cooldown claim je zamenjen beležnikom jer njegov PostgREST
    lanac (.update().eq().lt()) nije predmet ovog dokaza — atomičnost tog
    claim-a već pokrivaju drugi testovi; ovde se dokazuje da consume() I DALJE
    prolazi kroz taj gejt sa vrednošću koju je migracija upisala.
    """
    import shared.deps as deps
    import shared.feature_registry as fr
    import shared.usage as usage

    rpc_log: list[str] = []
    shim = _RegistryAndRpcShim(registry, rpc_log)

    # Sva tri modula drže SOPSTVENU referencu na `_get_supa` (from-import u
    # vreme učitavanja), pa patch nad `shared.deps` sam po sebi ne pokriva
    # `shared/usage.py::_increment_usage` — bez ovoga bi taj poziv otišao na
    # pravi Supabase klijent, pao, i fail-soft grana bi vratila 0, zbog čega bi
    # tvrdnja o dnevnom brojaču tiho merila ništa.
    monkeypatch.setattr(deps, "_get_supa", lambda: shim)
    monkeypatch.setattr(fr, "_get_supa", lambda: shim)
    monkeypatch.setattr(usage, "_get_supa", lambda: shim)
    monkeypatch.setattr(usage, "_is_founder", lambda *a, **k: False)
    monkeypatch.setattr(usage, "_get_credits", lambda uid: _balance(registry, uid) or 0)
    fr.invalidate()

    cooldown_calls: list[tuple] = []

    async def _claim(user_id, feature, cooldown):
        cooldown_calls.append((user_id, feature, cooldown))
        return True

    monkeypatch.setattr(usage, "_claim_cooldown_atomic", _claim)

    telemetry: list[tuple] = []

    async def _log(*args):
        telemetry.append(args)

    monkeypatch.setattr(usage, "_log_usage_event", _log)

    class _Stack:
        pass

    s = _Stack()
    s.rpc_log = rpc_log
    s.cooldown_calls = cooldown_calls
    s.telemetry = telemetry
    s.dsn = registry
    yield s
    fr.invalidate()


@pytest.mark.anyio
@pytest.mark.parametrize("key", ["confidence_audit", "conflict_check", "da_wallet_risk_assessment"])
async def test_R13_posle_migracije_nijedan_kredit_se_ne_oduzima(consume_stack, key):
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 15)

    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", key)

    assert preostalo == 15
    assert _balance(consume_stack.dsn, uid) == 15, f"{key}: kredit je i dalje naplaćen"
    assert "deduct_n_credits" not in consume_stack.rpc_log, (
        f"{key}: consume() je i dalje pozvao naplatu — grana `if n_credits > 0:` je uzeta"
    )


@pytest.mark.anyio
async def test_R13_negativna_kontrola_pre_migracije_kredit_JESTE_naplacen(consume_stack):
    """Bez ovog testa gornji bi mogao da prolazi vakuumski (npr. da shim uopšte
    ne stiže do naplate). Isti ključ, ista mašinerija, migracija NIJE pokrenuta."""
    import shared.usage as usage

    uid = _make_user(consume_stack.dsn, 15)
    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")

    assert preostalo == 14, "pre-111 stanje mora naplaćivati — inače dokaz iznad ne meri ništa"
    assert _balance(consume_stack.dsn, uid) == 14
    assert "deduct_n_credits" in consume_stack.rpc_log


@pytest.mark.anyio
async def test_R13_pozitivna_kontrola_deljeni_kljuc_i_dalje_naplacuje(consume_stack):
    """`case_commander` STVARNO zove GPT — posle migracije mora i dalje da košta."""
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 15)

    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", "case_commander")

    assert preostalo == 13, "case_commander je prestao da naplaćuje — GPT potrošnja je poklonjena"
    assert _balance(consume_stack.dsn, uid) == 13
    assert "deduct_n_credits" in consume_stack.rpc_log


@pytest.mark.anyio
async def test_R13_cooldown_gejt_i_dalje_radi_sa_vrednoscu_iz_migracije(consume_stack):
    """`shared/usage.py:321` — cooldown claim se dešava PRE naplate i ne zavisi
    od cene. Migracija je upisala 5s; consume() mora da ga koristi."""
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 15)

    await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")

    assert consume_stack.cooldown_calls, "cooldown gejt uopšte nije pozvan"
    assert consume_stack.cooldown_calls[0][2] == 5, (
        f"cooldown gejt pozvan sa {consume_stack.cooldown_calls[0][2]}, migracija je upisala 5"
    )


@pytest.mark.anyio
async def test_R13_cooldown_odbija_bez_ijedne_naplate(consume_stack, monkeypatch):
    """Ako claim ne uspe, consume() baca 429 — i ne sme dodirnuti ni kredite
    ni brojač."""
    from fastapi import HTTPException
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 15)

    async def _deny(*a, **k):
        return False

    monkeypatch.setattr(usage, "_claim_cooldown_atomic", _deny)
    monkeypatch.setattr(usage, "_seconds_since_last_call", lambda *a, **k: _async_none())

    with pytest.raises(HTTPException) as exc:
        await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")

    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "COOLDOWN"
    assert _balance(consume_stack.dsn, uid) == 15
    assert consume_stack.rpc_log == [], f"odbijen poziv je ipak dirnuo bazu: {consume_stack.rpc_log}"


async def _async_none():
    return None


@pytest.mark.anyio
async def test_R13_brojac_i_telemetrija_i_dalje_rade_pri_ceni_nula(consume_stack):
    """`shared/usage.py:396` gejtuje SAMO odbitak sa `if n_credits > 0:`.
    Autoritativni dnevni brojač (108) i telemetrija ostaju — to je razlog zašto
    je izabrano `krediti=0` umesto uklanjanja `consume()` poziva."""
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 15)

    await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")

    assert "increment_feature_usage" in consume_stack.rpc_log, "dnevni brojač nije pozvan"
    with psycopg.connect(consume_stack.dsn, autocommit=True) as c:
        row = c.execute(
            "SELECT broj_koriscenja, krediti_potroseni FROM public.feature_usage "
            "WHERE user_id=%s AND feature_key='confidence_audit'", (uid,)
        ).fetchone()
    assert row is not None, "upotreba nije zabeležena — telemetrijska kuka je izgubljena"
    assert row[0] == 1
    assert row[1] == 0.0, "brojač je zabeležio potrošnju kredita za funkciju koja ne naplaćuje"

    assert consume_stack.telemetry, "feature_usage_log događaj nije upisan"
    args = consume_stack.telemetry[0]
    assert args[2] == 0.0, f"telemetrija prijavljuje potrošnju {args[2]} za besplatnu funkciju"
    assert args[3] is None, (
        f"telemetrija i dalje prijavljuje ai_model={args[3]!r} za funkciju koja nikad ne "
        "dodirne model — to je tačno laž koju klauzula B briše"
    )


@pytest.mark.anyio
async def test_R13_korisnik_sa_nula_kredita_moze_da_otvori_podesavanja(consume_stack):
    """Kompletan scenario iz zaglavlja migracije: korisnik bez ijednog kredita
    otvara ekran Podešavanja. Pre 111 → 402. Posle → prolazi."""
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 0)

    preostalo = await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")
    assert preostalo == 0
    assert _balance(consume_stack.dsn, uid) == 0


@pytest.mark.anyio
async def test_R13_pedeset_konkurentnih_poziva_ne_uzimaju_nijedan_kredit(consume_stack):
    """Dugme „↻ Osveži" u `index.html:3561` je tačno na tom ekranu. Ni pod
    opterećenjem cena ne sme da procuri."""
    import asyncio as _asyncio
    import shared.usage as usage

    _apply_111(consume_stack.dsn)
    uid = _make_user(consume_stack.dsn, 15)

    async def one():
        try:
            return await usage.UsageService.consume(uid, "advokat@vindex.rs", "confidence_audit")
        except Exception as exc:  # noqa: BLE001 — svaki izuzetak je nalaz
            return f"ERR:{type(exc).__name__}"

    res = await _asyncio.gather(*[one() for _ in range(50)])
    assert all(r == 15 for r in res), f"neočekivani ishodi: {sorted(set(map(str, res)))}"
    assert _balance(consume_stack.dsn, uid) == 15
    assert "deduct_n_credits" not in consume_stack.rpc_log
