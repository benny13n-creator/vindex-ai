# -*- coding: utf-8 -*-
"""
Wave 10, Faza 2 — detekcija produkcione baze u test okruženju.

ZAŠTO JE OVO ZASEBAN MODUL, A NE PAR REDOVA U `conftest.py`
Zaštita mora da se može TESTIRATI. Provera zakopana u `conftest.py` izvršava se
jednom, pri pokretanju, i nijedan test ne može da je pozove sa izmišljenom
konfiguracijom da bi dokazao da radi. Wave 9 je već pokazao šta se dešava sa
zaštitom koju niko ne može posmatrati kako pada: prva verzija mrežne brane je
mesecima prijavljivala zelen suite ne radeći ništa.

ŠTA JE CILJ, A ŠTA NIJE
Cilj NIJE savršena detekcija svih mogućih budućih URL oblika — to je nedostižno.
Cilj je: **poznata produkciona konfiguracija ne sme nikada biti validan test
target.** Zato se ne gleda samo hostname, nego host, port, ime baze, oblik
ključa i environment marker; dovoljan je JEDAN pogodak.

FAIL-CLOSED U OBA SMERA
Ako se konfiguracija ne može razumeti (neparsabilan URL, nepoznat oblik), tretira
se kao PRODUKCIONA. Nepoznato nije isto što i bezbedno.
"""
from urllib.parse import urlparse

# ── Sankcionisani test targeti ──────────────────────────────────────────────
#
# `.invalid` je rezervisan TLD (RFC 2606) — po standardu se nikad ne razrešava.
# `localhost`/`127.0.0.1` pokrivaju throwaway PostgreSQL klastere na kojima rade
# dokazi o naplati. `fake.*` je postojeća konvencija ovog repoa (24 test fajla).
_TEST_HOST_SUFIKSI = (".invalid", ".test", ".example", ".localhost")
_TEST_HOST_TOKENI = ("fake", "test-only", "example", "dummy", "localhost")
_LOKALNI_HOSTOVI = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}

# Hostovi upravljanih baza. Nijedan od njih ne sme biti test target — čak i kad
# bi neko napravio „staging" projekat, njegovo mešanje sa suite-om koji svaki dan
# upisuje hiljade redova nije nešto što se dešava slučajno.
_UPRAVLJANI_SUFIKSI = (
    ".supabase.co", ".supabase.com", ".supabase.in",
    ".pooler.supabase.com",
    ".rds.amazonaws.com", ".render.com", ".neon.tech", ".railway.app",
    ".azure.com", ".googleapis.com", ".planetscale.com", ".cockroachlabs.cloud",
)

_PRODUKCIONI_MARKERI = {"production", "prod", "live"}
_ENV_MARKER_KLJUCEVI = ("ENV", "ENVIRONMENT", "APP_ENV", "VINDEX_ENV", "NODE_ENV")

# Portovi throwaway klastera. 5432 je NAMERNO izostavljen: to je podrazumevani
# port TRAJNOG PostgreSQL servisa, koji na razvojnim mašinama nosi stvarne
# podatke i sluša van loopback-a. „Lokalno" nije isto što i „potrošno" —
# `scripts/test_db.py::verify` primenjuje isti kriterijum (K2).
_DOZVOLJENI_PORTOVI = {55432, 55433, 55434, None}


def _host_je_testni(host: str) -> bool:
    """Poklapanje po LABELAMA, ne po podnizu.

    Prva verzija je koristila `t in h`, pa je `neki-host.example-corp.net`
    prolazio kao test target zbog podniza „example" u sredini imena firme. To je
    lažno negativan u smeru koji košta: nepoznat produkcioni host bi bio
    proglašen bezbednim. Uhvaćeno sopstvenim testom `test_b`.

    Labela je ceo deo između tačaka. `fake.supabase.co` ima labelu „fake";
    `example-corp.net` nema labelu „example".
    """
    h = (host or "").lower()
    if not h:
        return False
    if h in _LOKALNI_HOSTOVI:
        return True
    if h.endswith(_TEST_HOST_SUFIKSI):
        return True
    return any(t in h.split(".") for t in _TEST_HOST_TOKENI)


def _proveri_supabase_url(url: str):
    """`https://<ref>.supabase.co` je produkcioni projekat osim ako je očigledno lažan."""
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return f"SUPABASE_URL se ne može parsirati ({url[:24]}…) — nepoznato se tretira kao produkcija"
    if not host:
        return f"SUPABASE_URL nema host ({url[:24]}…)"
    if _host_je_testni(host):
        return None
    if host.endswith(_UPRAVLJANI_SUFIKSI):
        return f"SUPABASE_URL pokazuje na upravljanu bazu ({host})"
    return f"SUPABASE_URL nije prepoznat kao test target ({host})"


def _proveri_dsn(ime: str, dsn: str):
    """PostgreSQL connection string — host, port i ime baze."""
    if not dsn:
        return None
    try:
        p = urlparse(dsn)
        host = (p.hostname or "").lower()
        port = p.port
        baza = (p.path or "").lstrip("/")
    except Exception:
        return f"{ime} se ne može parsirati — nepoznato se tretira kao produkcija"
    if not host:
        return f"{ime} nema host"
    if host.endswith(_UPRAVLJANI_SUFIKSI):
        return f"{ime} pokazuje na upravljanu bazu ({host})"
    if host not in _LOKALNI_HOSTOVI and not _host_je_testni(host):
        return f"{ime} pokazuje na udaljeni host ({host}) — test suite sme samo lokalno"
    if port is not None and port not in _DOZVOLJENI_PORTOVI:
        return f"{ime} koristi port {port}, van dozvoljenih test portova"
    if baza and baza.lower() in _PRODUKCIONI_MARKERI:
        return f"{ime} cilja bazu imena {baza!r}"
    return None


def _proveri_kljuc(env) -> str | None:
    """Pravi Supabase service key je JWT (`eyJ…`). Test ključ to nikad nije.

    Ovo hvata slučaj koji URL provera propušta: neko ostavi lažan URL a pravi
    ključ, ili obrnuto. Sam ključ se NIKAD ne ispisuje — samo činjenica o obliku.
    """
    for k in ("SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY"):
        v = (env.get(k) or "").strip()
        if v.startswith("eyJ") and len(v) > 100:
            return f"{k} ima oblik pravog JWT ključa (ne test vrednosti)"
    return None


def _proveri_marker(env) -> str | None:
    for k in _ENV_MARKER_KLJUCEVI:
        v = (env.get(k) or "").strip().lower()
        if v in _PRODUKCIONI_MARKERI:
            return f"{k}={v!r}"
    return None


def proveri_konfiguraciju(env) -> list:
    """Vraća listu razloga zbog kojih je konfiguracija produkciona.

    Prazna lista znači: nijedan poznati produkcioni oblik nije prepoznat.
    Namerno vraća SVE razloge, ne prvi — poruka o grešci koja imenuje samo jedan
    problem vodi u krug „popravi pa pokreni pa popravi".
    """
    razlozi = []
    for r in (
        _proveri_supabase_url((env.get("SUPABASE_URL") or "").strip()),
        _proveri_dsn("SUPABASE_DB_URL", (env.get("SUPABASE_DB_URL") or "").strip()),
        _proveri_dsn("DATABASE_URL", (env.get("DATABASE_URL") or "").strip()),
        _proveri_kljuc(env),
        _proveri_marker(env),
    ):
        if r:
            razlozi.append(r)
    return razlozi


def je_produkcija(env) -> bool:
    return bool(proveri_konfiguraciju(env))


PORUKA = (
    "\n"
    "====================================================================\n"
    "  TEST SUITE ZAUSTAVLJEN — konfiguracija pokazuje na PRODUKCIONU bazu\n"
    "====================================================================\n"
    "\n"
    "Razlozi:\n"
    "{razlozi}\n"
    "\n"
    "Suite ne sme da se pokrene nad produkcijom. `audit_immutable` i\n"
    "`ai_provenance` su append-only iza trigera — red koji test upiše NE MOŽE\n"
    "da se obriše, a forenzički hash lanac time dobija zapise nepoznatog porekla.\n"
    "\n"
    "Šta uraditi:\n"
    "  1. Ukloni produkcione DB promenljive iz okruženja (`.env` se ne uvozi —\n"
    "     ove vrednosti su izričito izvezene u shell-u).\n"
    "  2. Za testove kojima treba prava baza koristi lokalni klaster:\n"
    "         python scripts/test_db.py up\n"
    "         python scripts/test_db.py verify\n"
    "\n"
    "Namerno pokretanje protiv prave baze (na sopstvenu odgovornost):\n"
    "     VINDEX_TEST_ALLOW_PROD_DB=1\n"
    "====================================================================\n"
)
