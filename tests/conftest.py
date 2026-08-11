# -*- coding: utf-8 -*-
"""
Shared pytest configuration.

Sets FIELD_ENCRYPTION_KEY before any module is imported so that
validate_field_encryption_key() (called at api.py import time) does not
call sys.exit(1) and kill the pytest collection process.

setdefault: does NOT overwrite the key if it is already present in the
environment (e.g. on Render or when a developer has it in .env).
"""
import base64
import os
import secrets

# Load .env so that FOUNDER_EMAILS and other vars are available when
# shared/deps.py is imported directly (e.g. by routers.web3 tests).
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
except ImportError:
    pass

os.environ.setdefault(
    "FIELD_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)

# CI-RED-001 (2026-08-08): the .env load above is best-effort — in CI there IS
# no .env file, and .github/workflows/tests.yml never supplied FOUNDER_EMAILS.
# shared/deps.py raises RuntimeError at IMPORT time when it is missing, so
# every test that imports it errored during collection and the "Test Suite"
# workflow had been failing on EVERY commit for the entire visible history
# (25+ runs). A permanently-red pipeline is a pipeline nobody reads — which is
# how the PROD-SYNTAX-001 outage shipped past it.
#
# setdefault, so a real value from .env or from the CI environment always wins;
# this only guarantees the suite is self-sufficient wherever it runs.
#
# The VALUE matters, not just its presence: 13 tests across
# test_business_groups / test_tier_config / test_feature_type /
# test_product_intelligence / test_ztc_conflict_check_autowiring assert
# founder-only behaviour using hard-coded addresses, and until now they were
# silently passing on whatever happened to be in the developer's own .env.
# Pinning the value here makes the suite deterministic and identical in CI,
# in a fresh clone, and on a laptop.
#
# (Follow-up worth doing separately: have those tests patch FOUNDER_EMAILS or
# _is_founder themselves instead of depending on ambient configuration. That
# is a 13-file change and is deliberately not bundled into a CI fix.)
os.environ.setdefault("FOUNDER_EMAILS", "benny13.n@gmail.com,founder@test.rs")


# ── Outbound network guard ──────────────────────────────────────────────────
# CI-RED-003 was a test that mocked the database but not the LLM client, so it
# issued a real, BILLED gpt-4o request on every run. It was green locally only
# because the developer's .env holds a live key, and it 401'd in CI. A sweep
# then found ten more tests with the identical shape, all in the RAG pipeline:
# Pinecone/embeddings/Cohere mocked, the OpenAI chat client not. They were
# invisible because those call sites fail soft -- the test passes, after a real
# network round-trip.
#
# Reviewing for this defect one test at a time does not hold. Deny it instead:
# the suite may talk to localhost (the real-PostgreSQL credit proofs need it)
# and nothing else. A test that reaches for the internet now fails loudly and
# names itself, instead of quietly spending money.
#
# Escape hatch: VINDEX_TEST_ALLOW_NETWORK=1 for a deliberate live-integration run.
import socket as _socket

#
# SCOPE: paid-inference hosts only, deliberately. A guard on ALL outbound
# traffic fails 123 tests -- almost all of them fail-soft DNS lookups against
# the fake Supabase host, which cost nothing, resolve instantly and are a
# tidiness problem, not a defect. Rewriting those tonight would be churn, and a
# guard that forces 123 rewrites gets switched off instead of obeyed. This one
# blocks exactly what costs money and makes results nondeterministic.
#
# HOOK POINT: getaddrinfo, not socket.connect. connect() is handed an already-
# resolved (ip, port) tuple, so a hostname test there matches nothing and the
# guard silently does nothing at all -- which is precisely how the first version
# of this block reported a fully green suite while the tests it was written to
# catch kept calling out. getaddrinfo still sees the hostname.
# The canary in tests/test_network_guard.py exists so that failure mode cannot
# happen quietly again.
if os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1":
    _BILLED_HOSTS = (
        "openai.com", "anthropic.com", "pinecone.io", "cohere.ai", "cohere.com",
        "voyageai.com", "googleapis.com", "azure.com",
    )
    _real_getaddrinfo = _socket.getaddrinfo

    class NetworkAccessBlocked(BaseException):
        """Deliberately a BaseException, not an Exception.

        Every offender found so far sits behind a fail-soft `except Exception`
        (and behind @llm_retry, which treats connection errors as retryable and
        backs off between attempts). An Exception here is swallowed: the test
        still passes, having burned three retry cycles reaching for the network
        -- which is exactly how these stayed invisible. As a BaseException it
        propagates through the fail-soft handlers and fails the test by name.
        """

    # Known offenders, recorded once so the guard can block everything else.
    # See tests/network_offenders_baseline.txt for why this exists and what it
    # costs. The list may shrink; anything not on it fails immediately.
    _BASELINE_PATH = os.path.join(os.path.dirname(__file__), "network_offenders_baseline.txt")
    try:
        with open(_BASELINE_PATH, encoding="utf-8") as _f:
            _ALLOWED_NODEIDS = {
                ln.strip() for ln in _f
                if ln.strip() and not ln.lstrip().startswith("#")
            }
    except OSError:
        _ALLOWED_NODEIDS = set()

    _CURRENT_NODEID = {"id": None}

    def pytest_runtest_setup(item):
        _CURRENT_NODEID["id"] = item.nodeid.replace("\\", "/")

    def _guarded_getaddrinfo(host, *a, **k):
        if isinstance(host, (bytes, bytearray)):
            host = host.decode("ascii", "ignore")
        if (
            isinstance(host, str)
            and any(host.endswith(h) for h in _BILLED_HOSTS)
            and _CURRENT_NODEID["id"] not in _ALLOWED_NODEIDS
        ):
            raise NetworkAccessBlocked(
                f"Test attempted a real call to the paid API at {host!r}. "
                "Mock the client instead — this is billed to the account whose key "
                "is in the environment, and makes the test nondeterministic. Set "
                "VINDEX_TEST_ALLOW_NETWORK=1 only for a deliberate live-integration run."
            )
        return _real_getaddrinfo(host, *a, **k)

    _socket.getaddrinfo = _guarded_getaddrinfo


# ── Wave 9: brana ka PRODUKCIONOJ bazi ──────────────────────────────────────
#
# NALAZ, IZMEREN A NE PRETPOSTAVLJEN.
#
# `.env` na razvojnoj mašini nosi žive `SUPABASE_URL` i `SUPABASE_SERVICE_KEY`,
# a `conftest.py` ih učitava (`_load_dotenv` iznad) da bi `FOUNDER_EMAILS` i
# `FIELD_ENCRYPTION_KEY` bili dostupni. Posledica koju je sonda potvrdila:
# `_get_supa()` u test procesu vraća PRAV klijent uperen u produkcioni projekat,
# i jedan poziv `security/ai_forensics.py::log_provenance_from_wrapper` bez moka
# upiše STVARAN red u produkcionu `ai_provenance` tabelu.
#
# Zašto je ovo teže od potrošenog novca: `audit_immutable` je append-only iza
# BEFORE UPDATE/DELETE trigera i hash-lančan. Red koji test upiše NE MOŽE da se
# obriše — svaki forenzički dokaz koji ovaj program koristi tako dobija smeće
# nepoznatog porekla. Isti razred štete je već jednom pogodio ovaj repo, kad su
# testovi brisali vektore iz produkcionog Pinecone-a.
#
# Postojeća brana iznad namerno pokriva samo NAPLATIVE hostove — njen komentar
# to izričito kaže („blocks exactly what costs money"). Cena, međutim, nikad
# nije bila jedina šteta.
#
# OBIM: blokira se TAČNO host iz `SUPABASE_URL`, ne ceo `supabase.co`. Testovi
# koji fail-soft gađaju izmišljeni Supabase host nastavljaju da rade
# nepromenjeno — nisu ni bili problem, ništa ne dodiruju.
#
# ESCAPE: `VINDEX_TEST_ALLOW_PROD_DB=1` za namerno pokretanje protiv prave baze.
#
# Ista `NetworkAccessBlocked` klasa i isti `getaddrinfo` hook kao gore, iz istog
# razloga: `connect()` dobija već razrešen IP, pa provera imena tamo ne hvata
# ništa — što je tačno greška zbog koje je prva verzija gornje brane prijavljivala
# potpuno zelen suite dok su pozivi i dalje odlazili.
if (
    os.environ.get("VINDEX_TEST_ALLOW_PROD_DB") != "1"
    and os.environ.get("VINDEX_TEST_ALLOW_NETWORK") != "1"
):
    import socket as _socket_db
    from urllib.parse import urlparse as _urlparse

    _PROD_DB_HOST = ""
    try:
        _u = (os.environ.get("SUPABASE_URL") or "").strip()
        if _u:
            _PROD_DB_HOST = (_urlparse(_u).hostname or "").lower()
    except Exception:
        _PROD_DB_HOST = ""

    # ZABELEŽENI PRESTUPNICI — isti mehanizam koji gornja brana već koristi.
    #
    # Merenje: 115 testova u ~40 fajlova danas dodiruje produkcionu bazu. Brana
    # koja ih sve obori biva ISKLJUČENA umesto poštovana — to obrazloženje je
    # autor prethodne brane već zapisao i ono i dalje važi. Zato se zatečeno
    # stanje ZAMRZAVA, a svaki NOV prestupnik pada odmah i imenuje se.
    #
    # Stanje je SADRŽANO, ne zatvoreno. `tests/prod_db_offenders_baseline.txt`
    # nosi tačan spisak i cenu, a `tests/test_prod_db_offenders_baseline.py`
    # fiksira maksimum tako da lista može samo da se smanjuje.
    _DB_BASELINE_PATH = os.path.join(os.path.dirname(__file__),
                                     "prod_db_offenders_baseline.txt")
    try:
        with open(_DB_BASELINE_PATH, encoding="utf-8") as _fdb:
            _DB_ALLOWED_NODEIDS = {
                ln.strip() for ln in _fdb
                if ln.strip() and not ln.lstrip().startswith("#")
            }
    except OSError:
        _DB_ALLOWED_NODEIDS = set()

    if _PROD_DB_HOST:
        _real_gai_db = _socket_db.getaddrinfo

        class ProductionDatabaseAccessBlocked(BaseException):
            """BaseException, ne Exception — namerno.

            Svaki upisni put u ovom kodu je fail-soft („a provenance-logging bug
            must never break a real AI call"). Obična `Exception` bi bila
            progutana, test bi ostao zelen, a red bi već bio upisan u produkciju.
            Kao `BaseException` probija fail-soft handlere i imenuje krivca.
            """

        def _guarded_gai_db(host, *a, **k):
            if isinstance(host, (bytes, bytearray)):
                host = host.decode("ascii", "ignore")
            if (
                isinstance(host, str)
                and host.lower() == _PROD_DB_HOST
                and _CURRENT_NODEID["id"] not in _DB_ALLOWED_NODEIDS
            ):
                raise ProductionDatabaseAccessBlocked(
                    "Test je pokušao poziv ka PRODUKCIONOJ bazi. Upis odavde je "
                    "nepovratan (audit tabele su append-only iza trigera), a "
                    "čitanje čini test nedeterminističnim. Mokuj Supabase klijent. "
                    "VINDEX_TEST_ALLOW_PROD_DB=1 samo za namerno pokretanje protiv "
                    "prave baze."
                )
            return _real_gai_db(host, *a, **k)

        _socket_db.getaddrinfo = _guarded_gai_db
