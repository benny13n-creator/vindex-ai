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


# ── Wave 9: kanarinac za branu ka PRODUKCIONOJ bazi ─────────────────────────
#
# Ista logika kao gore, drugi razlog. Sonda je izmerila da test proces sa živim
# `.env`-om upisuje STVARAN red u produkcionu `ai_provenance` tabelu — a te
# tabele su append-only iza trigera, pa se taj red ne može ukloniti.
#
# Brana bez kanarinca je nedokaziva: prva verzija gornje brane je mesecima
# prijavljivala zelen suite ne radeći ništa.
import os as _os
from urllib.parse import urlparse as _urlparse

_PROD_HOST = ""
try:
    _PROD_HOST = (_urlparse((_os.environ.get("SUPABASE_URL") or "").strip()).hostname or "")
except Exception:
    _PROD_HOST = ""

_DB_GUARD_ENABLED = (
    bool(_PROD_HOST)
    and _os.environ.get("VINDEX_TEST_ALLOW_PROD_DB") != "1"
    and _os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1"
)


@pytest.mark.skipif(not _DB_GUARD_ENABLED,
                    reason="SUPABASE_URL nije postavljen ili je brana namerno isključena")
def test_db_guard_blocks_the_production_project_host():
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(_PROD_HOST, 443)
    assert type(exc.value).__name__ == "ProductionDatabaseAccessBlocked", (
        f"brana ka produkcionoj bazi nije opalila — dobijeno {type(exc.value).__name__}"
    )


@pytest.mark.skipif(not _DB_GUARD_ENABLED,
                    reason="SUPABASE_URL nije postavljen ili je brana namerno isključena")
def test_db_guard_is_not_an_ordinary_exception():
    """Svaki upisni put je fail-soft — `Exception` bi bila progutana, test bi
    ostao zelen, a red bi već bio u produkciji."""
    with pytest.raises(BaseException) as exc:
        socket.getaddrinfo(_PROD_HOST, 443)
    assert not isinstance(exc.value, Exception), (
        "obična Exception se guta u fail-soft handlerima koje ova brana treba da probije"
    )


@pytest.mark.skipif(not _DB_GUARD_ENABLED,
                    reason="SUPABASE_URL nije postavljen ili je brana namerno isključena")
def test_db_guard_does_not_block_other_supabase_hosts():
    """Negativna kontrola obima.

    Blokira se TAČNO produkcioni projekat, ne ceo `supabase.co`. Testovi koji
    fail-soft gađaju izmišljeni host nisu ni bili problem — ništa ne dodiruju —
    i brana koja bi ih oborila bila bi isključena umesto poštovana.
    """
    try:
        socket.getaddrinfo("nepostojeci-projekat-vindex-test.supabase.co", 443)
    except BaseException as exc:
        assert type(exc).__name__ != "ProductionDatabaseAccessBlocked", (
            "brana je preširoka — pogodila je host koji nije produkcioni projekat"
        )
