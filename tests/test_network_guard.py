# -*- coding: utf-8 -*-
"""
Canary for the paid-API network guard in tests/conftest.py.

The guard's first version hooked socket.connect and matched on hostname. But
connect() receives an already-resolved (ip, port) tuple, so the hostname test
matched nothing and the guard did precisely nothing -- while reporting a fully
green suite, including the very tests it was written to catch. A guard that
cannot be observed failing is indistinguishable from no guard at all.

These tests observe it.
"""
import os
import socket

import pytest

_ENABLED = os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1"


@pytest.mark.skipif(not _ENABLED, reason="network guard deliberately disabled for this run")
def test_guard_blocks_a_paid_api_host():
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo("api.openai.com", 443)
    assert type(exc.value).__name__ == "NetworkAccessBlocked", (
        f"the guard did not fire — got {type(exc.value).__name__}"
    )


@pytest.mark.skipif(not _ENABLED, reason="network guard deliberately disabled for this run")
def test_guard_is_not_an_ordinary_exception():
    """Every offender found sits behind a fail-soft `except Exception` and
    behind @llm_retry. An Exception here is swallowed and the test still
    passes, having merely wasted three retry cycles reaching for the network.
    The guard must be a BaseException or it does not surface anything."""
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo("api.openai.com", 443)
    assert not isinstance(exc.value, Exception), (
        "an Exception is swallowed by the fail-soft handlers this guard exists to defeat"
    )


@pytest.mark.skipif(not _ENABLED, reason="network guard deliberately disabled for this run")
@pytest.mark.parametrize("host", ["api.pinecone.io", "api.anthropic.com", "api.cohere.ai"])
def test_guard_covers_the_other_billed_providers(host):
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(host, 443)
    assert type(exc.value).__name__ == "NetworkAccessBlocked"


def test_guard_leaves_localhost_alone():
    """The real-PostgreSQL credit proofs connect to 127.0.0.1 and must not be
    caught in the blast radius."""
    assert socket.getaddrinfo("127.0.0.1", 5432)


def test_guard_leaves_unrelated_hosts_alone():
    """Scoped to paid inference APIs on purpose — see the conftest comment.
    A guard that fails 123 tests gets switched off instead of obeyed."""
    try:
        socket.getaddrinfo("fake.supabase.co", 443)
    except BaseException as exc:  # DNS failure is fine; being BLOCKED is not
        assert type(exc).__name__ != "NetworkAccessBlocked", (
            "the guard must not extend to non-billed hosts"
        )


# ── Kanarinac za branu ka PRODUKCIONOJ bazi ────────────────────────────────
#
# Ista logika kao gore, drugi razlog. Sonda je u Wave 9 izmerila da test proces
# sa živim `.env`-om upisuje STVARAN red u produkcionu `ai_provenance` tabelu — a
# te tabele su append-only iza trigera, pa se taj red ne može ukloniti.
#
# PREPISANO U WAVE 10 — ŠTA SE PROMENILO I ZAŠTO
#
# Wave 9 verzija je izvodila blokirani host iz `SUPABASE_URL`:
#     _PROD_HOST = urlparse(os.environ["SUPABASE_URL"]).hostname
# i tvrdila da `getaddrinfo(_PROD_HOST)` puca.
#
# Ta tvrdnja je bila tačna samo dok je test proces DRŽAO produkcione
# kredencijale. Wave 10 je upravo to uklonio: `tests/conftest.py` više ne uvozi
# `.env` DB vrednosti, pa je `SUPABASE_URL` sada `fake.supabase.co`. Stari
# kanarinac bi time tvrdio da brana treba da blokira LAŽNI host — tačno suprotno
# od onoga što se želi.
#
# NOVA, TRAJNA INVARIJANTA: brana blokira KLASU hostova upravljanih baza, bez
# obzira šta je u konfiguraciji. Time hvata i modul koji bi zaobišao
# `shared/deps.py` i sam sklopio produkcioni URL.
#
# Tvrdnje nisu oslabljene — ojačane su: stara je pokrivala jedan host, nova
# pokriva klasu, i uz to ima negativnu kontrolu obima.
import os as _os

_DB_GUARD_ENABLED = (
    _os.environ.get("VINDEX_TEST_ALLOW_PROD_DB") != "1"
    and _os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1"
)

# Predstavnici klase: Supabase projekat, Supabase pooler, AWS RDS.
_PROD_KLASA = (
    "abcdefghijklmnopqrst.supabase.co",
    "aws-0-eu-central-1.pooler.supabase.com",
    "moja-baza.eu-west-1.rds.amazonaws.com",
)


@pytest.mark.skipif(not _DB_GUARD_ENABLED, reason="brana je namerno isključena")
@pytest.mark.parametrize("host", _PROD_KLASA)
def test_db_guard_blocks_managed_database_hosts(host):
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(host, 443)
    assert type(exc.value).__name__ == "ProductionDatabaseAccessBlocked", (
        f"brana nije opalila za {host} — dobijeno {type(exc.value).__name__}"
    )


@pytest.mark.skipif(not _DB_GUARD_ENABLED, reason="brana je namerno isključena")
def test_db_guard_is_not_an_ordinary_exception():
    """Svaki upisni put je fail-soft — `Exception` bi bila progutana, test bi
    ostao zelen, a red bi već bio u produkciji."""
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(_PROD_KLASA[0], 443)
    assert not isinstance(exc.value, Exception), (
        "obična Exception se guta u fail-soft handlerima koje ova brana treba da probije"
    )


@pytest.mark.skipif(not _DB_GUARD_ENABLED, reason="brana je namerno isključena")
@pytest.mark.parametrize("host", ["fake.supabase.co", "test-only.invalid", "127.0.0.1"])
def test_db_guard_does_not_block_sanctioned_test_hosts(host):
    """Negativna kontrola obima, i najvažnija u ovom bloku.

    Bez nje bi gornji testovi prolazili i da brana blokira SVE — uključujući
    sankcionisani `fake.supabase.co`, koji ceo suite koristi. Tačno ta greška je
    napravljena u prvoj verziji Wave 10 promene i oborila je 115 testova.
    """
    try:
        socket.getaddrinfo(host, 443)
    except BaseException as exc:
        assert type(exc).__name__ != "ProductionDatabaseAccessBlocked", (
            f"brana je preširoka — pogodila je sankcionisani test host {host}"
        )


@pytest.mark.skipif(not _DB_GUARD_ENABLED, reason="brana je namerno isključena")
def test_db_guard_config_gate_is_the_primary_defence():
    """Brana je DRUGI sloj. Prvi je to što produkcioni kredencijali uopšte ne
    ulaze u test proces — bez njih klijent ka produkciji ne može ni da nastane."""
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from prod_db_guard import proveri_konfiguraciju

    assert proveri_konfiguraciju(_os.environ) == [], (
        "test proces drži produkcionu konfiguraciju — primarna kapija je "
        "zaobiđena, a brana je samo dubinska odbrana"
    )
