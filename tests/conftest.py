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

# ── Wave 10, Faza 1-2: PRODUKCIONA BAZA NE ULAZI U TEST PROCES ─────────────
#
# DOKAZAN RIZIK (Wave 9, izmeren sondom — ne hipoteza)
# `.env` nosi žive `SUPABASE_URL` i `SUPABASE_SERVICE_KEY`. Učitavaju se ovde
# jer su `FOUNDER_EMAILS` i `FIELD_ENCRYPTION_KEY` iz istog fajla. Posledica:
# `shared/deps.py::_get_supa()` u test procesu vraća PRAV klijent uperen u
# produkcioni projekat. Jedan nemokovan poziv upiše STVARAN red u produkcionu
# bazu — a `audit_immutable` i `ai_provenance` su append-only iza BEFORE
# UPDATE/DELETE trigera i hash-lančane, pa se taj red NE MOŽE obrisati.
#
# Najčistiji dokaz da nije teorijski: `tests/test_ztc_scenario_b_attach.py`
# je kroz `routers/smart_intake.py:1525` → `audit_immutable.log_action` →
# `_get_last_hash(supa)` čitao i pisao u produkcioni lanac na SVAKOM pokretanju
# suite-a.
#
# ZAŠTO SE `.env` KREDENCIJALI ODBACUJU, A NE „PREBACUJU"
# `.env` je konfiguracija APLIKACIJE, ne testova. Odbijanje da se uveze nije
# „pametno prebacivanje na drugu bazu" — posle njega baze prosto NEMA. Vrednosti
# koje se postavljaju umesto njih (`fake.supabase.co`) nisu druga baza nego
# domen koji ne postoji; to je i postojeća konvencija ovog repoa, koju 24 test
# fajla već koriste preko `os.environ.setdefault(...)`. Ta konvencija je do sada
# bila NEDELOTVORNA baš zato što je `.env` učitan prvi, pa `setdefault` nije
# imao šta da postavi.
#
# ŠTA SE DEŠAVA AKO NEKO IZRIČITO IZVEZE PRODUKCIONE KREDENCIJALE
# To je namerna radnja i tretira se kao takva: suite se GASI pre prvog testa
# (v. `pytest_configure` na dnu ovog fajla). Ne upozorenje, ne log, ne fallback.
_DB_ENV_KLJUCEVI = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_KEY",
    "SUPABASE_DB_URL",
    "DATABASE_URL",
)

# Šta je bilo u okruženju PRE `.env` — samo to je izričita namera korisnika.
_DB_IZ_OKRUZENJA = {k: os.environ.get(k) for k in _DB_ENV_KLJUCEVI}

# Load .env so that FOUNDER_EMAILS and other vars are available when
# shared/deps.py is imported directly (e.g. by routers.web3 tests).
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
except ImportError:
    pass

# Sve što je `.env` doneo za bazu se poništava — vraća se tačno ono što je u
# okruženju stvarno stajalo pre učitavanja (najčešće: ništa).
for _k, _stara in _DB_IZ_OKRUZENJA.items():
    if _stara is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _stara

# Sankcionisane test vrednosti. `.invalid` je rezervisan TLD (RFC 2606) i po
# standardu se NIKAD ne razrešava — dakle nije „druga baza" nego garantovan
# ćorsokak. `fake.supabase.co` se zadržava jer 24 test fajla već grade svoje
# fixture-e oko tog imena.
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-only-service-key-not-a-real-jwt")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-only-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-only-jwt-secret-longer-than-32-chars")

# KAPIJA. Izvršava se PRE ijednog uvoza produkcionog modula i pre prvog testa,
# dakle pre bilo kakvog write-a. Ako je konfiguracija i posle poništavanja `.env`
# produkciona, neko ju je izričito izvezao u shell-u — to je namerna radnja i
# odbija se glasno.
#
# `RuntimeError` na nivou modula, ne `pytest.exit()`: `conftest.py` se uvozi pre
# nego što su pytest hook-ovi dostupni, a i inače — izuzetak ovde obara
# kolekciju, što je tačno ono što se traži. Nijedan test se ne izvršava.
if os.environ.get("VINDEX_TEST_ALLOW_PROD_DB") != "1":
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from prod_db_guard import PORUKA as _PORUKA_PROD
    from prod_db_guard import proveri_konfiguraciju as _proveri_prod

    _razlozi = _proveri_prod(os.environ)
    if _razlozi:
        raise RuntimeError(
            _PORUKA_PROD.format(razlozi="\n".join(f"  - {r}" for r in _razlozi))
        )

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
# WAVE 10 — OVA BRANA VIŠE NIJE PRVA ODBRANA, NEGO DUBINSKA.
# Primarna zaštita je sada kapija na vrhu ovog fajla: produkcioni kredencijali
# uopšte ne ulaze u test proces, pa `_get_supa()` ne može ni da napravi klijent
# ka produkciji. Brana ostaje kao drugi sloj — hvata slučaj u kome bi neki modul
# zaobišao `shared/deps.py` i sam sklopio produkcioni URL.
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

    # WAVE 10 — ISPRAVLJEN IZVOR ISTINE.
    #
    # Do sada je brana blokirala TAČNO host iz `SUPABASE_URL`. Otkako kapija na
    # vrhu ovog fajla postavlja sankcionisanu test vrednost, taj host je
    # `fake.supabase.co` — pa bi brana blokirala baš lažni host, a pravi
    # produkcioni pustila. Merenje je to i pokazalo: 115 testova je odjednom
    # palo na hostu koji ne postoji.
    #
    # Sada se blokira KLASA: svaki host upravljane baze koji nije sankcionisani
    # test target. Time brana dobija stvarnu preostalu ulogu — hvata modul koji
    # bi zaobišao `shared/deps.py` i sam sklopio produkcioni URL.
    from prod_db_guard import _UPRAVLJANI_SUFIKSI as _UPR_SUF
    from prod_db_guard import _host_je_testni as _host_testni

    # ZABELEŽENI PRESTUPNICI — LISTA JE PRAZNA, I TO JE CILJNO STANJE.
    #
    # Wave 9 je ovde imenovao 115 testova iz ~40 fajlova kao „sadržano, ne
    # zatvoreno". Wave 10 je to IZMERIO: kad produkcioni kredencijali ne uđu u
    # test proces, od 455 testova u tih 42 fajla pada TAČNO JEDAN
    # (`test_ztc_scenario_b_attach.py`, koji je kroz `smart_intake.py:1525`
    # stvarno pisao u produkcioni hash-lančani ledger). Ostalih 114 je produkciju
    # dodirivalo isključivo kroz fail-soft putanje koje se identično ponašaju i
    # kad hosta nema.
    #
    # Drugim rečima: allowlist nikad nije bio potreban — bio je posledica toga
    # što se problem rešavao na nivou DNS-a umesto na nivou konfiguracije.
    # Zadržava se prazan, po uzoru na `network_offenders_baseline.txt`, da bi
    # budući prestupnik imao gde da bude zabeležen NAMERNO umesto da neko ugasi
    # branu.
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

    if True:
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
            _h = host.lower() if isinstance(host, str) else ""
            if (
                _h.endswith(_UPR_SUF)
                and not _host_testni(_h)
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


# ── Wave 10, Faza 6: izolacija rate-limiter stanja između testova ──────────
#
# DOKAZAN PROBLEM (Wave 9, izmeren): jedan test koji napuni bafer obarao je
# sledeći sa HTTP 429 iz razloga koji nema veze sa njegovim predmetom — 84 pada
# u punom suite-u, dok je izolovano sve bilo zeleno. Klasičan „radi kod mene".
#
# Wave 10 je uzrok uklonio na dva nivoa:
#   1. `api.py` više ne gradi sopstvenu `Limiter` instancu nego uvozi kanonsku
#      iz `shared/rate.py`. Ranije su postojale DVE (a posle
#      `importlib.reload` i TRI), pa je gašenje limitera preko `shared.rate`
#      gasilo instancu koju rute uopšte ne koriste.
#   2. `shared/rate.py::reset_limiter_state()` — produkciona funkcija koja
#      prazni brojače, `_fallback_storage`, i vraća instancu iz „storage je
#      mrtav" režima.
#
# Ova fixture je treći nivo: garantuje da svaki test počinje sa praznim
# brojačima, bez obzira šta je prethodni radio.
#
# NAPOMENA O `enabled`: reset vraća `enabled = True`. Test koji se OSLANJA na to
# da je limiter ostao ugašen iz prethodnog testa (a sam ga ne gasi) posle ovoga
# pada — i to je ispravan nalaz, ne regresija.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _izolovan_rate_limiter():
    from shared.rate import reset_limiter_state
    reset_limiter_state()
    yield
    reset_limiter_state()


@_pytest.fixture(autouse=True)
def _izolovan_ai_kontekst():
    """Čisti korelacioni kontekst između testova.

    `shared/ai_provenance.py` drži `_request_ctx` i `_case_ctx` kao
    `ContextVar`-ove koje `set_request_context()` postavlja BEZ vraćanja na
    staro — to je namerno u produkciji (v. komentar u modulu i u
    `test_mission_atlas_ai_provenance.py:54`), jer svaki HTTP zahtev dobija svoj
    kontekst. U testovima, međutim, svi dele isti kontekst procesa, pa je
    vrednost iz jednog testa curela u sve naredne.

    Posledica je bila pad koji se vidi SAMO pod određenim redosledom:
    `test_case_dna_events.py::test_emit_genome_event_inserts_row_with_correct_payload`
    je dobijao tuđi `correlation_id` umesto sveže generisanog UUID-a
    (`assert 6 == 36`, vrednost `'corr-9'`), jer `routers/case_dna.py:591` uzima
    `current_correlation_id() or new_correlation_id()`.

    Isti obrazac i isti razlog kao `_izolovan_rate_limiter` iznad: globalno
    stanje se resetuje s obe strane testa, ne samo pre.
    """
    from shared import ai_provenance as _ap
    _ap._request_ctx.set({})
    _ap._case_ctx.set({})
    yield
    _ap._request_ctx.set({})
    _ap._case_ctx.set({})
