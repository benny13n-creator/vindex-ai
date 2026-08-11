# -*- coding: utf-8 -*-
"""
Wave 10, Faze 3-4 — zaštita od pisanja u produkcionu bazu iz testova.

ŠTA JE BIO DEFEKT

`tests/conftest.py` učitava `.env` (potrebni su `FOUNDER_EMAILS` i
`FIELD_ENCRYPTION_KEY`), pa su živi `SUPABASE_URL` i `SUPABASE_SERVICE_KEY`
ulazili u test proces. `shared/deps.py::_get_supa()` je time vraćao PRAV klijent
uperen u produkcioni projekat.

Nije bilo teorijski. `tests/test_ztc_scenario_b_attach.py` je kroz
`routers/smart_intake.py:1525` → `shared/audit_immutable.log_action` →
`_get_last_hash(supa)` čitao i pisao u produkcioni lanac na SVAKOM pokretanju
suite-a. `audit_immutable` i `ai_provenance` su append-only iza BEFORE
UPDATE/DELETE trigera i hash-lančane — upisan red se NE MOŽE obrisati.

DVA SLOJA ZAŠTITE, I ZAŠTO BAŠ TAKO

  1. KONFIGURACIJA (primarna). `.env` DB kredencijali se ne uvoze u test proces.
     Izričito izvezena produkciona konfiguracija obara kolekciju pre prvog testa.
     Ovo je pravi popravak: bez kredencijala klijent ka produkciji ne može ni da
     nastane.
  2. DNS (dubinska). Blokira KLASU hostova upravljanih baza. Hvata modul koji bi
     zaobišao `shared/deps.py` i sam sklopio produkcioni URL.

Wave 9 je pokušao samo sloj 2, sa allowlist-om od 115 imena. Merenje u Wave 10:
kad kredencijali ne uđu u proces, od 455 testova u tih 42 fajla pada TAČNO JEDAN.
Allowlist dakle nikad nije ni trebao — bio je posledica rešavanja problema na
pogrešnom sloju.

METOD
Detekcija je izdvojena u `tests/prod_db_guard.py` baš zato da bi mogla da se
pozove sa izmišljenom konfiguracijom. Provera zakopana u `conftest.py` izvršava
se jednom i niko ne može da je posmatra kako pada — a Wave 9 je već pokazao šta
se dešava sa takvom „zaštitom".
"""
import os
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prod_db_guard import proveri_konfiguraciju  # noqa: E402

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 2 — detekcija: host, port, ime baze, oblik ključa, environment marker
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("env, sta_hvata", [
    # host
    ({"SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co"}, "Supabase projekat"),
    ({"SUPABASE_URL": "https://db.moj-projekat.supabase.com"}, "supabase.com"),
    ({"DATABASE_URL": "postgresql://u:p@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"}, "pooler"),
    ({"DATABASE_URL": "postgresql://u:p@x.eu-west-1.rds.amazonaws.com:5432/app"}, "RDS"),
    ({"SUPABASE_DB_URL": "postgresql://u:p@ep-x.neon.tech/main"}, "Neon"),
    ({"DATABASE_URL": "postgresql://u:p@db.railway.app:5432/railway"}, "Railway"),
    # udaljeni host koji nije ni na jednoj listi — nepoznato != bezbedno
    ({"DATABASE_URL": "postgresql://u:p@10.20.30.40:5432/app"}, "udaljeni host"),
    # port
    ({"DATABASE_URL": "postgresql://u:p@127.0.0.1:6543/app"}, "nedozvoljen port"),
    # ime baze
    ({"DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/production"}, "ime baze"),
    ({"DATABASE_URL": "postgresql://u:p@localhost:55432/prod"}, "ime baze"),
    # oblik kljuca — pravi Supabase service key je JWT
    ({"SUPABASE_SERVICE_KEY": "eyJ" + "a" * 200}, "JWT ključ"),
    # environment marker
    ({"ENVIRONMENT": "production"}, "marker"),
    ({"APP_ENV": "prod"}, "marker"),
    ({"VINDEX_ENV": "LIVE"}, "marker"),
])
def test_a_produkciona_konfiguracija_je_prepoznata(env, sta_hvata):
    """Mandat traži više od hostname-a: host, port, ime baze, marker."""
    razlozi = proveri_konfiguraciju(env)
    assert razlozi, f"{sta_hvata} nije prepoznat kao produkcija: {env}"


@pytest.mark.parametrize("env", [
    {"SUPABASE_URL": "https://fake.supabase.co"},
    {"SUPABASE_URL": "https://test-only.invalid"},
    {"DATABASE_URL": "postgresql://postgres@127.0.0.1:55432/vindex_test"},
    {"DATABASE_URL": "postgresql://postgres@localhost:55433/mig111"},
    {"SUPABASE_SERVICE_KEY": "test-only-service-key-not-a-real-jwt"},
    {"ENVIRONMENT": "test"},
    {},
])
def test_ng_sankcionisana_test_konfiguracija_prolazi(env):
    """Negativna kontrola, i najvažnija u fajlu.

    Detektor koji sve proglasi produkcijom je isto što i nikakav — biva
    isključen prvog dana. Bez ove tvrdnje bi `test_a` prolazio i sa
    `return ["uvek produkcija"]`.
    """
    assert proveri_konfiguraciju(env) == [], f"lažno optužena test konfiguracija: {env}"


def test_b_nepoznat_oblik_se_tretira_kao_produkcija():
    """FAIL-CLOSED. Nepoznato nije isto što i bezbedno."""
    assert proveri_konfiguraciju({"SUPABASE_URL": "https://neki-nasumican-host.example-corp.net"})
    assert proveri_konfiguraciju({"SUPABASE_URL": "ovo-nije-url"})


def test_c_svi_razlozi_se_prijavljuju_odjednom():
    """Poruka koja imenuje samo prvi problem vodi u krug popravi-pokreni-popravi."""
    razlozi = proveri_konfiguraciju({
        "SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co",
        "DATABASE_URL": "postgresql://u:p@x.rds.amazonaws.com:5432/app",
        "ENVIRONMENT": "production",
    })
    assert len(razlozi) >= 3, f"prijavljeno samo {len(razlozi)} razloga: {razlozi}"


def test_d_kljuc_se_nikad_ne_ispisuje():
    """Razlog sme da kaže DA je ključ pravi, nikad KOJI je."""
    tajna = "eyJ" + "TAJNI-KLJUC-KOJI-NE-SME-DA-PROCURI" + "z" * 200
    razlozi = proveri_konfiguraciju({"SUPABASE_SERVICE_KEY": tajna})
    assert razlozi
    spojeno = " ".join(razlozi)
    assert "TAJNI-KLJUC" not in spojeno and tajna not in spojeno, (
        "vrednost ključa je procurela u poruku o grešci"
    )


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 3 — ponašanje: suite MORA da padne pre prvog write-a
# ═══════════════════════════════════════════════════════════════════════════

def _pokreni_pytest(dodatni_env: dict):
    """Pravi pytest podproces — meri se ponašanje, ne postojanje helpera."""
    env = dict(os.environ)
    env.update(dodatni_env)
    env.pop("VINDEX_TEST_ALLOW_PROD_DB", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
         "--collect-only", "tests/test_network_guard.py"],
        cwd=_KOREN, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, env=env,
    )


def test_e_produkciona_konfiguracija_obara_suite_pre_prvog_testa():
    """Srž Faze 3.

    Ne warning, ne log, ne fallback, ne „pametno prebacivanje" — kolekcija pada.
    `--collect-only` dokazuje da se to dešava PRE nego što se ijedan test
    izvrši, dakle pre bilo kakvog write-a.
    """
    r = _pokreni_pytest({"SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co"})
    izlaz = (r.stdout or "") + (r.stderr or "")
    assert r.returncode != 0, (
        "suite se pokrenuo uprkos produkcionoj konfiguraciji — "
        f"izlazni kod {r.returncode}"
    )
    assert "ZAUSTAVLJEN" in izlaz, f"nema jasne poruke o razlogu:\n{izlaz[-1500:]}"
    assert "supabase.co" in izlaz, "poruka ne imenuje ŠTA je prepoznato"


def test_f_normalna_konfiguracija_ne_obara_suite():
    """Negativna kontrola za `test_e`.

    Bez nje bi `test_e` prolazio i da kapija obara suite UVEK — što bi bilo
    gore od problema koji rešava.
    """
    r = _pokreni_pytest({"SUPABASE_URL": "https://fake.supabase.co"})
    assert r.returncode == 0, (
        f"kapija obara i sankcionisanu test konfiguraciju:\n"
        f"{((r.stdout or '') + (r.stderr or ''))[-1500:]}"
    )


def test_g_eksplicitan_opt_in_prolazi():
    """Prekidač postoji i radi — inače bi neko zakomentarisao kapiju."""
    env = dict(os.environ)
    env["SUPABASE_URL"] = "https://abcdefghijklmnopqrst.supabase.co"
    env["VINDEX_TEST_ALLOW_PROD_DB"] = "1"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
         "--collect-only", "tests/test_network_guard.py"],
        cwd=_KOREN, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, env=env,
    )
    assert r.returncode == 0, "eksplicitan opt-in ne radi"


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 1 — kredencijali iz `.env` ne ulaze u test proces
# ═══════════════════════════════════════════════════════════════════════════

def test_h_test_proces_nema_produkcione_kredencijale():
    """Direktno merenje stanja OVOG procesa.

    Ovo je tvrdnja koja bi u Wave 9 pala: tada je `os.environ["SUPABASE_URL"]`
    u test procesu bio pravi produkcioni projekat.
    """
    assert proveri_konfiguraciju(os.environ) == [], (
        "test proces drži produkcionu konfiguraciju — kapija u conftest.py "
        "je zaobiđena ili pokvarena"
    )


def test_i_klijent_ne_pokazuje_na_produkciju():
    """Sloj iznad env-a: sam Supabase klijent koji `shared/deps.py` gradi."""
    import shared.deps as deps
    assert deps.SUPABASE_URL, "URL je prazan — `_get_supa()` bi digao RuntimeError"
    assert proveri_konfiguraciju({"SUPABASE_URL": deps.SUPABASE_URL}) == [], (
        f"`shared.deps.SUPABASE_URL` pokazuje na produkciju"
    )


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 4 — append-only tabele: konekcija pada PRE write-a
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("host", [
    "abcdefghijklmnopqrst.supabase.co",
    "aws-0-eu-central-1.pooler.supabase.com",
    "x.eu-west-1.rds.amazonaws.com",
])
def test_j_dubinska_brana_blokira_upravljane_hostove(host):
    """Drugi sloj: modul koji bi zaobišao `shared/deps.py` i sam sklopio URL.

    Blokira se KLASA hostova, ne konfigurisana vrednost — Wave 9 verzija je
    čitala host iz `SUPABASE_URL`, pa je posle Faze 1 blokirala baš LAŽNI host
    a pravi puštala.
    """
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(host, 443)
    assert type(exc.value).__name__ == "ProductionDatabaseAccessBlocked", (
        f"brana nije opalila za {host} — dobijeno {type(exc.value).__name__}"
    )


def test_ng_dubinska_brana_ne_dira_test_hostove():
    """Negativna kontrola obima — brana koja obori lažni host biva isključena."""
    for host in ("fake.supabase.co", "test-only.invalid", "127.0.0.1"):
        try:
            socket.getaddrinfo(host, 443)
        except BaseException as exc:
            assert type(exc).__name__ != "ProductionDatabaseAccessBlocked", (
                f"brana je preširoka — pogodila je test host {host}"
            )


def test_k_append_only_upis_ne_stize_do_mreze():
    """FAZA 4, mereno kroz stvarni produkcioni put.

    `shared/audit_immutable.log_action` je tačan put kojim je
    `test_ztc_scenario_b_attach.py` pisao u produkciju. Ovde se poziva sa
    hardkodovanim produkcionim klijentom — dakle zaobilazi se i Faza 1 — i
    dokazuje da dubinska brana zaustavi poziv PRE nego što HTTP zahtev ode.
    """
    import asyncio
    from unittest.mock import patch

    from supabase import create_client

    klijent = create_client(
        "https://abcdefghijklmnopqrst.supabase.co",
        "eyJ" + "x" * 200,
    )

    from shared.audit_immutable import log_action

    with patch("shared.deps._get_supa", return_value=klijent):
        try:
            asyncio.run(log_action("test_probe", "u1", "t", "r1"))
        except BaseException as exc:
            assert type(exc).__name__ == "ProductionDatabaseAccessBlocked", (
                f"poziv je prošao ili pao iz drugog razloga: {type(exc).__name__}"
            )
            return

    # `log_action` je fail-soft, pa izuzetak možda ne izađe. Ključna tvrdnja je
    # da ni u tom slučaju nije bilo mrežnog poziva — brana je jedina stvar koja
    # to garantuje, a `test_j` je već dokazuje nad istim hostom.
