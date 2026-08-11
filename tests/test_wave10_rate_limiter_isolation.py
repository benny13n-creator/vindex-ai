# -*- coding: utf-8 -*-
"""
Wave 10 — Rate limiter ima JEDAN jasan lifecycle.

Problem koji ovaj fajl zaključava (izmeren, ne hipoteza):
u repou su postojale DVE žive `Limiter` instance — jedna u `shared/rate.py`
(na koju su svi `@limiter.limit(...)` dekoratori u `routers/*` trajno vezani
pri uvozu) i druga koju je `api.py` gradio za sebe i stavljao u
`app.state.limiter` (odakle je `SlowAPIMiddleware` sprovodio podrazumevani
`60/hour`). `importlib.reload(shared.rate)` je pravio i TREĆU. Posledica:
test koji ugasi ili resetuje limiter preko `shared.rate.limiter` gasi
instancu koju rute ne koriste — brojači i dalje rastu i sledeći testovi
dobijaju HTTP 429 iz razloga koji nema veze sa njihovim predmetom
(izmereno: 84 pada u punom suite-u, zeleno izolovano).

INVARIJANTA KOJU OVAJ FAJL DOKAZUJE: test A ne sme uticati na limiter state
testa B, a svi potrošači (ruteri, `app.state.limiter`, `shared.rate`) moraju
gledati u ISTU instancu — po identitetu objekta, ne po jednakosti.

Sve se meri RUNTIME ponašanjem (TestClient, stvarni HTTP zahtevi i stvarni
brojači u storage-u), ne čitanjem izvornog koda.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("SECRET_KEY", "test-secret-key-za-testove-128bit")

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from shared.rate import limiter, reset_limiter_state

# VAŽNO — ovi uvozi MORAJU biti na nivou modula, ne unutar test funkcija.
#
# `routers/*` i `api.py` vezuju svoju referencu na limiter jednom, pri uvozu, i
# nikad je više ne osvežavaju. Ako bi ih ovaj fajl uvozio tek unutar testa, uvoz
# bi se desio POSLE što je autouse fixture već pozvala reset — pa bi ruterska
# referenca pokupila tek-postavljenu vrednost i test bi bio slep za tačnu klasu
# greške koju treba da hvata (reset koji prevezuje modulski atribut umesto da
# resetuje objekat koji rute stvarno drže). Izmereno: sa lazy uvozom, mutacija
# M4 je prošla nezapaženo.
from dotenv import load_dotenv

load_dotenv()
import api  # noqa: E402
import shared.rate as rs  # noqa: E402
import routers.strategija as strategija  # noqa: E402
import routers.drafting as drafting  # noqa: E402
import routers.dokument as dokument  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# Test app — koristi KANONSKU instancu limitera (ne kopiju, ne novu instancu).
#
# Namerno se ne registruje ruta na `api.app`: to bi trajno izmenilo pravu app
# za ostatak suite-a. Brojači ipak žive u istom, deljenom storage-u kanonskog
# limitera — a to je tačno stanje čija se izolacija ovde testira.
#
# `SlowAPIMiddleware` se namerno NE dodaje: bez njega u storage-u postoji samo
# brojač eksplicitnog `@limiter.limit`, pa test A može da tvrdi tačnu vrednost
# brojača (1), a ne "bar 1".
# ═══════════════════════════════════════════════════════════════════════════
LIMIT = 3
PUTANJA = "/wave10-test-limit"
IP = "203.0.113.77"

_app = FastAPI()
_app.state.limiter = limiter
_app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(status_code=429, content={"greska": "429"}),
)


@_app.get(PUTANJA)
@limiter.limit(f"{LIMIT}/minute")
async def _wave10_ruta(request: Request):
    return {"ok": True}


client = TestClient(_app)


def _zahtev():
    """Jedan stvarni HTTP zahtev sa fiksnim klijentskim IP-om (X-Forwarded-For
    je ono što `shared.rate._get_real_ip` čita, pa je ovo isti key svaki put)."""
    return client.get(PUTANJA, headers={"X-Forwarded-For": IP})


def _brojaci() -> dict:
    """Stvarni sadržaj brojača kanonskog limitera (MemoryStorage.storage)."""
    return dict(getattr(limiter._storage, "storage", {}))


def _ukupno() -> int:
    return sum(int(v) for v in _brojaci().values())


# ═══════════════════════════════════════════════════════════════════════════
# Korak 3 — fixture koja garantuje izolaciju.
#
# Lokalna je (autouse na nivou ovog modula). Da bi važila za CEO suite mora u
# `tests/conftest.py` — tačan predlog je u izveštaju; conftest ovde nije diran
# jer je u tuđem opsegu.
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def _izolovan_limiter():
    """Pre svakog testa vraća kanonski limiter na determinističko stanje.

    Reset ide kroz PRODUKCIONU funkciju `shared.rate.reset_limiter_state()` —
    ne kroz test-only petljanje po privatnim atributima — pa test i sam
    dokazuje da je ta funkcija dovoljna.
    """
    reset_limiter_state()
    yield
    reset_limiter_state()


# ═══════════════════════════════════════════════════════════════════════════
# A — jedan zahtev prolazi, brojač je tačno 1
# ═══════════════════════════════════════════════════════════════════════════
def test_a_jedan_zahtev_prolazi_i_brojac_je_jedan():
    assert _ukupno() == 0, "fixture nije očistila brojače pre testa"

    r = _zahtev()

    assert r.status_code == 200, f"prvi zahtev je odbijen: {r.status_code} {r.text}"
    assert _ukupno() == 1, (
        f"posle tačno jednog zahteva brojač mora biti 1, a jeste {_ukupno()} "
        f"(sadržaj: {_brojaci()})"
    )


# ═══════════════════════════════════════════════════════════════════════════
# B — limit dostignut → sledeći zahtev BLOKIRAN (HTTP 429)
# ═══════════════════════════════════════════════════════════════════════════
def test_b_prekoracen_limit_vraca_429():
    for i in range(LIMIT):
        r = _zahtev()
        assert r.status_code == 200, f"zahtev {i + 1}/{LIMIT} je odbijen pre limita: {r.status_code}"

    r = _zahtev()
    assert r.status_code == 429, (
        f"{LIMIT + 1}. zahtev je prošao sa {r.status_code} — limit se ne sprovodi, "
        f"pa bi svaki test koji 'dokazuje' izolaciju bio prazan"
    )


# ═══════════════════════════════════════════════════════════════════════════
# C — nov test kontekst: stanje prethodnog testa NE POSTOJI
#
# Meri se ISTI endpoint i ISTI IP kao u testu B, koji je bafer napunio do 429.
# Prva tvrdnja je ordering-nezavisna i to je ona jaka: šta god prethodni test
# radio, OVAJ test počinje sa praznim brojačima.
# ═══════════════════════════════════════════════════════════════════════════
def test_c_novi_kontekst_ne_nasledjuje_pun_bafer():
    assert _ukupno() == 0, (
        f"brojači su procureli iz prethodnog testa: {_brojaci()} — "
        f"tačno curenje globalnog stanja koje je Wave 9 morao da krpi"
    )

    r = _zahtev()
    assert r.status_code == 200, (
        f"isti endpoint i isti IP koji je prethodni test doveo do 429 i dalje "
        f"vraćaju {r.status_code} — stanje je preživelo granicu testa"
    )


# ═══════════════════════════════════════════════════════════════════════════
# D — jedna instanca za sve: ruteri, app.state.limiter, shared.rate
#     Dokaz po IDENTITETU objekta (`is`), ne po jednakosti.
# ═══════════════════════════════════════════════════════════════════════════
def test_d_svi_potrosaci_gledaju_u_istu_instancu():
    kandidati = {
        "shared.rate.limiter": rs.limiter,
        "api.app.state.limiter": api.app.state.limiter,
        "routers.strategija.limiter": strategija.limiter,
        "routers.drafting.limiter": drafting.limiter,
        "routers.dokument.limiter": dokument.limiter,
    }

    razlicite = {}
    for ime, obj in kandidati.items():
        razlicite.setdefault(id(obj), []).append(ime)

    assert len(razlicite) == 1, (
        "postoji više od jedne žive Limiter instance — dekoratori u ruterima i "
        "SlowAPIMiddleware bi brojali u odvojene storage-e, pa gašenje/reset "
        f"jedne tiho promašuje drugu. Grupe: {list(razlicite.values())}"
    )

    # I storage mora biti isti objekat — dve instance mogu deliti konfiguraciju
    # a i dalje imati odvojene brojače, pa identitet limitera sam nije dovoljan.
    storages = {id(obj._storage) for obj in kandidati.values()}
    assert len(storages) == 1, "isti limiter, a različit storage — nemoguće stanje, proveri fix"


def test_d2_reset_je_vidljiv_kroz_svaku_referencu():
    """Reset preko `shared.rate` mora biti odmah vidljiv i ruterskoj referenci
    i `app.state.limiter` — to je ono što je pre fixa tiho promašivalo.

    Reference se čitaju iz uvoza na nivou modula (vidi napomenu uz uvoze):
    ruterska referenca je vezana PRE bilo kog reseta, tačno kao u produkciji.
    """
    _zahtev()
    assert _ukupno() >= 1, "priprema nije napunila brojač"

    reset_limiter_state()

    assert sum(int(v) for v in strategija.limiter._storage.storage.values()) == 0, (
        "ruterska referenca i dalje vidi stare brojače — reset je pogodio drugu instancu"
    )
    assert sum(int(v) for v in api.app.state.limiter._storage.storage.values()) == 0, (
        "app.state.limiter i dalje vidi stare brojače — reset je pogodio drugu instancu"
    )
    assert api.app.state.limiter.enabled is True, "reset mora vratiti enabled na podrazumevano"


# ═══════════════════════════════════════════════════════════════════════════
# E — nema cross-test kontaminacije: prvi test iscrpi limit, drugi mora proći.
#     Par se čita u redosledu definisanja (verifikacija se pokreće sa
#     `-p no:randomly`); E2 je i sam po sebi tačan ako se izvrši prvi.
# ═══════════════════════════════════════════════════════════════════════════
def test_e1_prvi_test_iscrpljuje_limit_do_429():
    poslednji = None
    for _ in range(LIMIT + 2):
        poslednji = _zahtev()
    assert poslednji.status_code == 429, (
        f"priprema kontaminacije nije uspela — očekivan 429, dobijeno {poslednji.status_code}"
    )


def test_e2_drugi_test_mora_proci_iako_je_prvi_iscrpeo_limit():
    assert _ukupno() == 0, (
        f"stanje iz test_e1 je preživelo granicu testa: {_brojaci()}"
    )
    r = _zahtev()
    assert r.status_code == 200, (
        f"drugi test dobija {r.status_code} zbog brojača koje je napunio prvi — "
        f"cross-test kontaminacija limitera"
    )
