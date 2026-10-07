"""NS002 Task 3 — /v2/preview/ (Vindex V2 NG) je PODRAZUMEVANO ISKLJUČEN.

Promenljiva VINDEX_V2_NG_PREVIEW_ENABLED se čita pri uvozu api.py, kao u
produkciji pri startu procesa. Zato se SVAKA vrednost proverava u ZASEBNOM
Python procesu (stvaran `import api`, stvaran TestClient), sa istim lažnim
okruženjem koje postavlja tests/conftest.py — bez zavisnosti od redosleda
testova i bez mrežnih poziva.

Dokazuje:
  • bez promenljive (i za svaku vrednost osim 1/true/yes) rute ne postoje (404);
  • uključen: /v2/preview i /v2/preview/ bez `rezim` → /v2/preview/?rezim=live
    (NS003: produkcioni preview nikad podrazumevano ne prikazuje DEMO), postojeći
    upit se čuva; index.html (no-store, nosniff, X-Robots-Tag noindex), src/, fonts/;
  • izlaže se SAMO index.html, src/, fonts/ — ne tests/, serve.mjs, package.json;
  • traversal ne vraća nijedan fajl van tih direktorijuma;
  • /app, /app-v2, /sw.js, /offline, /static/*, /api/predmeti su identični
    sa i bez preview-a (preview ne zaklanja /api).
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parent.parent
NG = KOREN / "frontend-v2-ng"

POMOCNIK = r"""
import hashlib, json, re, sys
from fastapi.testclient import TestClient
import api
k = TestClient(api.app, follow_redirects=False)
out = {}
for put in sys.argv[1:]:
    r = k.get(put)
    # /app nosi token za razbijanje keša po procesu (`?v=nover-<vreme>` kad
    # identitet commit-a nije dostupan); razlikuje se i između dva ISTA procesa.
    norm = re.sub(rb"\?v=[A-Za-z0-9._-]+", b"?v=X", r.content)
    out[put] = {"status": r.status_code, "ct": r.headers.get("content-type", ""),
                "cc": r.headers.get("cache-control", ""), "loc": r.headers.get("location", ""),
                "xrt": r.headers.get("x-robots-tag", ""), "xcto": r.headers.get("x-content-type-options", ""),
                "sha": hashlib.sha256(r.content).hexdigest(), "sha_norm": hashlib.sha256(norm).hexdigest()}
print("@@" + json.dumps(out))
"""

PUTANJE_PREVIEW = [
    "/v2/preview", "/v2/preview/", "/v2/preview/?rezim=live", "/v2/preview/?rezim=demo",
    "/v2/preview/src/app.js", "/v2/preview/src/api.js",
    "/v2/preview/fonts/ibm-plex-sans/400.css",
    "/v2/preview/fonts/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2",
]
NEIZLOZENO = [
    "/v2/preview/tests/fixtures/original.html", "/v2/preview/package.json", "/v2/preview/serve.mjs",
    "/v2/preview/README.md", "/v2/preview/index.html", "/v2/preview/src/../serve.mjs",
    "/v2/preview/src/%2e%2e/serve.mjs", "/v2/preview/src/..%2fserve.mjs", "/v2/preview/src/..%2f..%2fapi.py",
    "/v2/preview/fonts/%2e%2e/%2e%2e/api.py", "/v2/preview/src/%2e%2e/tests/live-api.mjs",
]
NEPROMENJENO = ["/app", "/app-v2", "/sw.js", "/offline", "/static/vindex.js", "/static/sw.js", "/api/predmeti"]


# Okruženje pomoćnog procesa se gradi OD NULE: samo sistemske promenljive i
# LAŽNE vrednosti (iste kao u CI-ju). Ništa iz .env ili okruženja programera —
# ni stvarni ključevi, ni SUPABASE_DB_URL/DATABASE_URL — ne može da uđe.
_SISTEMSKE = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
              "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL")
_LAZNO = {
    "SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_ANON_KEY": "fake-anon-key",
    "SUPABASE_SERVICE_KEY": "fake-service-key", "SUPABASE_JWT_SECRET": "fake-jwt-secret-longer-than-32-chars-ok",
    "OPENAI_API_KEY": "sk-fake", "PINECONE_API_KEY": "fake-pinecone", "PINECONE_HOST": "https://fake.pinecone.io",
    "FIELD_ENCRYPTION_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "FOUNDER_EMAILS": "ci@example.com", "PYTHONUTF8": "1",
}


def _pokreni(vrednost, putanje):
    env = {k: os.environ[k] for k in _SISTEMSKE if k in os.environ}
    env.update(_LAZNO)
    if vrednost is not None:
        env["VINDEX_V2_NG_PREVIEW_ENABLED"] = vrednost
    r = subprocess.run([sys.executable, "-c", POMOCNIK, *putanje], cwd=str(KOREN), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    linija = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    assert linija, f"pomoćni proces nije vratio rezultat (rc={r.returncode}):\n{r.stderr[-2000:]}"
    return json.loads(linija[-1][2:])


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def iskljucen():
    return _pokreni(None, PUTANJE_PREVIEW + NEPROMENJENO)


@pytest.fixture(scope="module")
def ukljucen():
    return _pokreni("1", PUTANJE_PREVIEW + NEIZLOZENO + NEPROMENJENO)


def test_podrazumevano_iskljucen_bez_promenljive(iskljucen):
    for put in PUTANJE_PREVIEW:
        assert iskljucen[put]["status"] == 404, (put, iskljucen[put]["status"])


@pytest.mark.parametrize("vrednost", ["", "0", "false", "no", "off", "on", "enabled", "TRUE1", "y", "2"])
def test_svaka_druga_vrednost_je_iskljucen(vrednost):
    r = _pokreni(vrednost, ["/v2/preview", "/v2/preview/", "/v2/preview/src/app.js"])
    assert all(v["status"] == 404 for v in r.values()), (vrednost, r)


@pytest.mark.parametrize("vrednost", ["1", "true", "yes", " TRUE ", "Yes"])
def test_dozvoljene_vrednosti_ukljucuju(vrednost):
    r = _pokreni(vrednost, ["/v2/preview/?rezim=live"])
    assert r["/v2/preview/?rezim=live"]["status"] == 200, (vrednost, r)


# NS003 Task 2: adresa bez `rezim` → LIVE; postojeći upit se čuva; eksplicitni
# `rezim` (i neispravan — runtime ga odbija glasno) se ne dira.
PREUSMERENJA = {
    "/v2/preview": "/v2/preview/?rezim=live",
    "/v2/preview/": "/v2/preview/?rezim=live",
    "/v2/preview?rezim=live": "/v2/preview/?rezim=live",
    "/v2/preview?rezim=demo": "/v2/preview/?rezim=demo",
    "/v2/preview?x=1": "/v2/preview/?x=1&rezim=live",
    "/v2/preview/?x=1": "/v2/preview/?x=1&rezim=live",
    "/v2/preview?rezim=demo&x=1": "/v2/preview/?rezim=demo&x=1",
    "/v2/preview?x=1&rezim=live": "/v2/preview/?x=1&rezim=live",
    "/v2/preview?rezim=nesto": "/v2/preview/?rezim=nesto",
    "/v2/preview?next=//evil.example": "/v2/preview/?next=//evil.example&rezim=live",
    "/v2/preview/?next=https://evil.example/": "/v2/preview/?next=https://evil.example/&rezim=live",
}
SERVIRA = ["/v2/preview/?rezim=live", "/v2/preview/?rezim=demo", "/v2/preview/?rezim=live&x=1",
           "/v2/preview/?x=1&rezim=demo", "/v2/preview/?rezim=nesto", "/v2/preview/?rezim="]


@pytest.fixture(scope="module")
def kanonski():
    return _pokreni("1", list(PREUSMERENJA) + SERVIRA)


@pytest.mark.parametrize("put", list(PREUSMERENJA))
def test_bez_rezima_preusmerava_u_live_i_cuva_upit(kanonski, put):
    r = kanonski[put]
    assert r["status"] == 307, (put, r["status"])
    assert r["loc"] == PREUSMERENJA[put], (put, r["loc"])


@pytest.mark.parametrize("put", list(PREUSMERENJA))
def test_preusmerenje_je_uvek_relativno_na_isti_izvor(kanonski, put):
    loc = kanonski[put]["loc"]
    assert loc.startswith("/v2/preview/?") and not loc.startswith("//") and "://" not in loc.split("?")[0], loc
    assert kanonski[put]["xrt"] == "noindex, nofollow, noarchive"


@pytest.mark.parametrize("put", SERVIRA)
def test_eksplicitan_rezim_servira_index(kanonski, put):
    r = kanonski[put]
    assert r["status"] == 200 and r["sha"] == _sha(NG / "index.html"), (put, r["status"])


def test_ukljucen_servira_v2_index_bez_kesa(ukljucen):
    for put in ("/v2/preview/?rezim=live", "/v2/preview/?rezim=demo"):
        r = ukljucen[put]
        assert r["status"] == 200 and r["ct"].startswith("text/html")
        assert r["sha"] == _sha(NG / "index.html"), "nije V2 NG index.html"
        assert "no-store" in r["cc"]
        assert r["xcto"] == "nosniff"
        assert r["xrt"] == "noindex, nofollow, noarchive", (put, r["xrt"])


@pytest.mark.parametrize("put,fajl", [
    ("/v2/preview/src/app.js", "src/app.js"), ("/v2/preview/src/api.js", "src/api.js"),
    ("/v2/preview/fonts/ibm-plex-sans/400.css", "fonts/ibm-plex-sans/400.css"),
    ("/v2/preview/fonts/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2", "fonts/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2"),
])
def test_ukljucen_asseti_ispod_iste_rute(ukljucen, put, fajl):
    assert ukljucen[put]["status"] == 200
    assert ukljucen[put]["sha"] == _sha(NG / fajl)


def test_ukljucen_izlaze_samo_index_src_fonts(ukljucen):
    zabranjeni = {_sha(p) for p in [KOREN / "api.py", NG / "serve.mjs", NG / "package.json", NG / "README.md",
                                     NG / "tests/fixtures/original.html", NG / "tests/live-api.mjs"]}
    for put in NEIZLOZENO:
        r = ukljucen[put]
        assert r["sha"] not in zabranjeni, f"{put} je vratio fajl van src/fonts"
        assert r["status"] in (404, 405), (put, r["status"])


def test_postojece_rute_nepromenjene(iskljucen, ukljucen):
    for put in NEPROMENJENO:
        a, b = iskljucen[put], ukljucen[put]
        assert (a["status"], a["sha_norm"], a["ct"]) == (b["status"], b["sha_norm"], b["ct"]), put


def test_preview_ne_zaklanja_api(ukljucen):
    # Bez tokena postojeća ruta i dalje odgovara 401 — preview je ne prekriva.
    assert ukljucen["/api/predmeti"]["status"] == 401
