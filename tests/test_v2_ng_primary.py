"""NS004 Task 5 — reverzibilan prekidač: V2 NG kao primarni /app (podrazumevano ISKLJUČEN).

VINDEX_V2_NG_PRIMARY_ENABLED se čita pri uvozu api.py (kao u produkciji pri
startu procesa), pa se svaka kombinacija proverava u ZASEBNOM procesu sa
okruženjem izgrađenim od nule (samo lažne vrednosti).

Dokazuje:
  • ISKLJUČEN (odsutan i svaka vrednost osim 1/true/yes): /app je bajt-identičan
    legacy odgovoru, /app-legacy je isti legacy, /v2/app/* ne postoji (404),
    `?posle=app`/`?odjava=1` ne menjaju ništa;
  • UKLJUČEN: /app je V2 NG sa apsolutnim assetima na /v2/app/ (nijedan relativan
    src/fonts/brand), no-store; asseti su bajt-identični fajlovima; tests/,
    package.json i ostalo nisu izloženi; /app-legacy je i dalje legacy, a
    `?posle=app`/`?odjava=1` dobijaju skript povratka; preview ostaje nezavisan;
  • ponovo ISKLJUČEN (novi proces): sve kao na početku — bez izmene koda;
  • ostale rute (/, /app-v2, /sw.js, /offline, /static/*, /api/predmeti) su
    identične u oba stanja.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parent.parent
NG = KOREN / "frontend-v2-ng"
LOGO = {"brand/Vindex_Transparent_EXACT_LOOK.svg": "a69b32383295eb8c3850bb01581bb370433bb1761a935f88f878a1fc4afffc3f",
        "brand/Vindex_Protected_Light_Surface.png": "7485ddff765080615bcd90f04f383762770c41d8cf9e24fb21171088024eeae9"}

POMOCNIK = r"""
import hashlib, json, re, sys
from fastapi.testclient import TestClient
import api
k = TestClient(api.app, follow_redirects=False)
out = {}
for put in sys.argv[1:]:
    r = k.get(put)
    norm = re.sub(rb"\?v=[A-Za-z0-9._-]+", b"?v=X", r.content)
    norm = re.sub(rb"/v2/@[A-Za-z0-9._-]+/", b"/v2/@X/", norm)
    out[put] = {"status": r.status_code, "ct": r.headers.get("content-type", ""), "cc": r.headers.get("cache-control", ""),
                "xcto": r.headers.get("x-content-type-options", ""), "sha": hashlib.sha256(r.content).hexdigest(),
                "norm": hashlib.sha256(norm).hexdigest(), "telo": r.content.decode("utf-8", "replace") if put.startswith("/app") else ""}
print("@@" + json.dumps(out))
"""

_SISTEMSKE = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
              "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL")
_LAZNO = {
    "SUPABASE_URL": "https://fake.supabase.co", "SUPABASE_ANON_KEY": "fake-anon-key",
    "SUPABASE_SERVICE_KEY": "fake-service-key", "SUPABASE_JWT_SECRET": "fake-jwt-secret-longer-than-32-chars-ok",
    "OPENAI_API_KEY": "sk-fake", "PINECONE_API_KEY": "fake-pinecone", "PINECONE_HOST": "https://fake.pinecone.io",
    "FIELD_ENCRYPTION_KEY": "a" * 64, "FOUNDER_EMAILS": "ci@example.com", "PYTHONUTF8": "1",
}
APP = ["/app", "/app-legacy", "/app-legacy?posle=app", "/app-legacy?odjava=1", "/app?rezim=demo"]
ASSETI = ["/v2/app/src/app.js", "/v2/app/src/runtime.js", "/v2/app/fonts/ibm-plex-sans/400.css", *("/v2/app/" + f for f in LOGO)]
SKRIVENO = ["/v2/app/tests/live-api.mjs", "/v2/app/package.json", "/v2/app/serve.mjs", "/v2/app/README.md", "/v2/app/index.html",
            "/v2/app/src/%2e%2e/serve.mjs", "/v2/app/brand/%2e%2e/package.json"]
OSTALO = ["/", "/app-v2", "/sw.js", "/offline", "/static/vindex.js", "/static/sw.js", "/api/predmeti", "/v2/preview/"]


def _pokreni(okruzenje, putanje):
    env = {k: os.environ[k] for k in _SISTEMSKE if k in os.environ}
    env.update(_LAZNO)
    env.update(okruzenje)
    r = subprocess.run([sys.executable, "-c", POMOCNIK, *putanje], cwd=str(KOREN), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    linija = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    assert linija, f"pomoćni proces nije vratio rezultat (rc={r.returncode}):\n{r.stderr[-2000:]}"
    return json.loads(linija[-1][2:])


SVE = APP + ASSETI + SKRIVENO + OSTALO


@pytest.fixture(scope="module")
def iskljucen():
    return _pokreni({}, SVE)


@pytest.fixture(scope="module")
def ukljucen():
    return _pokreni({"VINDEX_V2_NG_PRIMARY_ENABLED": "true"}, SVE)


@pytest.fixture(scope="module")
def ponovo_iskljucen():
    return _pokreni({"VINDEX_V2_NG_PRIMARY_ENABLED": "0"}, SVE)


def _je_legacy(r):
    return r["status"] == 200 and "/static/vindex.js" in r["telo"] and "frontend-v2-ng" not in r["telo"] and "v2/app/src" not in r["telo"]


def test_iskljucen_app_je_legacy_bez_ikakve_promene(iskljucen):
    assert _je_legacy(iskljucen["/app"])
    for put in ("/app-legacy", "/app-legacy?posle=app", "/app-legacy?odjava=1", "/app?rezim=demo"):
        assert iskljucen[put]["norm"] == iskljucen["/app"]["norm"], put
    assert "location.replace('/app')" not in iskljucen["/app-legacy?posle=app"]["telo"]


def test_iskljucen_nema_v2_app_asseta(iskljucen):
    for put in ASSETI + SKRIVENO:
        assert iskljucen[put]["status"] == 404, (put, iskljucen[put]["status"])


@pytest.mark.parametrize("vrednost", ["", "0", "false", "no", "off", "on", "enabled", "2", "TRUE1"])
def test_svaka_druga_vrednost_je_iskljucen(vrednost):
    r = _pokreni({"VINDEX_V2_NG_PRIMARY_ENABLED": vrednost}, ["/app", "/v2/app/src/app.js"])
    assert _je_legacy(r["/app"]) and r["/v2/app/src/app.js"]["status"] == 404, vrednost


@pytest.mark.parametrize("vrednost", ["1", "true", "yes", " TRUE ", "Yes"])
def test_dozvoljene_vrednosti_ukljucuju(vrednost):
    r = _pokreni({"VINDEX_V2_NG_PRIMARY_ENABLED": vrednost}, ["/app"])
    assert '<canvas id="pozadina"' in r["/app"]["telo"], vrednost


def test_ukljucen_app_je_v2_sa_stabilnim_assetima(ukljucen):
    r = ukljucen["/app"]
    assert r["status"] == 200 and r["ct"].startswith("text/html") and "no-store" in r["cc"] and r["xcto"] == "nosniff"
    telo = r["telo"]
    assert '<canvas id="pozadina"' in telo and 'src="/v2/app/src/runtime.js"' in telo
    assert not re.search(r'\b(?:href|src)="(?:src|fonts|brand)/', telo), "ostala je relativna putanja asseta"
    assert "/v2/preview/" not in telo, "primarni /app ne sme zavisiti od preview putanje"
    ocekivano = re.sub(r'\b((?:href|src)=")(src|fonts|brand)/', r"\1/v2/app/\2/", (NG / "index.html").read_text(encoding="utf-8"))
    assert telo == ocekivano
    # ?rezim=demo ne menja ništa na serveru; DEMO isključuje runtime.js po putanji.
    assert ukljucen["/app?rezim=demo"]["sha"] == r["sha"]


@pytest.mark.parametrize("put", ASSETI)
def test_ukljucen_asseti_bajt_identicni(ukljucen, put):
    assert ukljucen[put]["status"] == 200, put
    fajl = put[len("/v2/app/"):]
    ocekivano = LOGO.get(fajl) or hashlib.sha256((NG / fajl).read_bytes()).hexdigest()
    assert ukljucen[put]["sha"] == ocekivano, put


@pytest.mark.parametrize("put", SKRIVENO)
def test_ukljucen_nista_drugo_nije_izlozeno(ukljucen, put):
    assert ukljucen[put]["status"] in (404, 405), (put, ukljucen[put]["status"])


def test_ukljucen_app_legacy_ostaje_klasican_i_vraca_na_v2(ukljucen, iskljucen):
    assert _je_legacy(ukljucen["/app-legacy"]) and ukljucen["/app-legacy"]["norm"] == iskljucen["/app"]["norm"]
    for put in ("/app-legacy?posle=app", "/app-legacy?odjava=1"):
        t = ukljucen[put]["telo"]
        assert _je_legacy(ukljucen[put]) and t.count("location.replace('/app')") >= 1, put
        assert t.index("location.replace('/app')") > t.index("/static/vindex.js"), "skript mora biti posle legacy koda"
        assert '"sb-czsxymueizfqrbbgqqob-auth-token"' in t and "doLogout" in t
        assert "setItem" not in t.split("<script>(function(){'use strict';")[-1], "skript povratka ne sme pisati sesiju"


def test_preview_ostaje_nezavisan(ukljucen, iskljucen):
    assert ukljucen["/v2/preview/"]["status"] == 404 and iskljucen["/v2/preview/"]["status"] == 404
    oba = _pokreni({"VINDEX_V2_NG_PRIMARY_ENABLED": "1", "VINDEX_V2_NG_PREVIEW_ENABLED": "1"},
                   ["/app", "/v2/preview/?rezim=live", "/v2/app/src/app.js"])
    assert '<canvas id="pozadina"' in oba["/app"]["telo"]
    assert oba["/v2/preview/?rezim=live"]["status"] == 200 and oba["/v2/app/src/app.js"]["status"] == 200
    samo_preview = _pokreni({"VINDEX_V2_NG_PREVIEW_ENABLED": "1"}, ["/app", "/v2/preview/?rezim=live", "/v2/app/src/app.js"])
    assert _je_legacy(samo_preview["/app"]) and samo_preview["/v2/preview/?rezim=live"]["status"] == 200
    assert samo_preview["/v2/app/src/app.js"]["status"] == 404


def test_ostale_rute_identicne_u_oba_stanja(ukljucen, iskljucen):
    for put in OSTALO:
        assert (iskljucen[put]["status"], iskljucen[put]["norm"]) == (ukljucen[put]["status"], ukljucen[put]["norm"]), put
    assert ukljucen["/api/predmeti"]["status"] == 401


def test_ponovo_iskljucen_vraca_legacy_bez_izmene_koda(ponovo_iskljucen, iskljucen):
    for put in SVE:
        a, b = iskljucen[put], ponovo_iskljucen[put]
        assert (a["status"], a["norm"]) == (b["status"], b["norm"]), put
