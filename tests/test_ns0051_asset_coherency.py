"""NS005.1 — koherentnost asseta primarnog V2 /app (build-adresirane putanje).

Kvar u produkciji (8a125977): nov index.html je tražio NOVE module (novi URL-ovi →
stigli do servera), ali `app.js` na STABILNOJ putanji /v2/app/src/app.js (bez
Cache-Control) i dalje je davao keš iz NS004 — mešanje buildova.

Ugovor koji se ovde dokazuje (svaki proces = jedan „deploy“, token iz
shared/build_info.py kroz GIT_SHA, kao RENDER_GIT_COMMIT u produkciji):
  A. svaka lokalna src/href referenca u /app nosi /v2/app/@<token>/; token B ≠ A;
  B. HTML builda B traži samo URL-ove builda B — keš popunjen buildom A nema
     nijedan od njih; server B odbija token A i server A odbija token B (smena
     instanci) sa 404 + no-store;
  C. inventar: svi JS, CSS, fontovi (uključujući url() iz CSS-a fontova) i brand
     su build-adresirani i bajt-identični fajlovima; nijedna stabilna putanja;
  D. /app-legacy, /app-v2 i /v2/preview su isti sa i bez primarnog prekidača.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

import pytest

KOREN = Path(__file__).resolve().parent.parent
NG = KOREN / "frontend-v2-ng"
SHA_A = "aaaaaaa1111111111111111111111111111111aa"
SHA_B = "bbbbbbb2222222222222222222222222222222bb"
TOK_A, TOK_B = SHA_A[:7], SHA_B[:7]

POMOCNIK = r"""
import hashlib, json, re, sys
from fastapi.testclient import TestClient
import api
k = TestClient(api.app, follow_redirects=False)
out = {"_token": getattr(api, "_V2_NG_TOKEN", None)}
for put in sys.argv[1:]:
    r = k.get(put)
    norm = re.sub(rb"\?v=[A-Za-z0-9._-]+", b"?v=X", r.content)
    out[put] = {"status": r.status_code, "ct": r.headers.get("content-type", ""), "cc": r.headers.get("cache-control", ""),
                "xcto": r.headers.get("x-content-type-options", ""), "sha": hashlib.sha256(r.content).hexdigest(),
                "norm": hashlib.sha256(norm).hexdigest(),
                "telo": r.content.decode("utf-8", "replace") if (put.startswith("/app") or put.endswith(".css") or "rezim=" in put) else ""}
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
UKLJUCEN = {"VINDEX_V2_NG_PRIMARY_ENABLED": "1"}


def _pokreni(okruzenje, putanje):
    env = {k: os.environ[k] for k in _SISTEMSKE if k in os.environ}
    env.update(_LAZNO)
    env.update(okruzenje)
    r = subprocess.run([sys.executable, "-c", POMOCNIK, *putanje], cwd=str(KOREN), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    linija = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    assert linija, f"pomoćni proces nije vratio rezultat (rc={r.returncode}):\n{r.stderr[-2000:]}"
    return json.loads(linija[-1][2:])


def _reference(html):
    """Sve src/href vrednosti osim sidara, /app* navigacije i spoljnih adresa."""
    return [v for v in re.findall(r'\b(?:href|src)="([^"]*)"', html)
            if not v.startswith(("#", "/app", "http:", "https:", "mailto:"))]


def _izvorne_reference():
    return re.findall(r'\b(?:href|src)="((?:src|fonts|brand)/[^"]*)"', (NG / "index.html").read_text(encoding="utf-8"))


def _fontovi(token):
    """URL-ovi woff2 fajlova iz CSS-a fontova (relativni url() se razrešava kao u pregledaču)."""
    urls = []
    for css in sorted((NG / "fonts").rglob("*.css")):
        osnova = f"/v2/app/@{token}/" + css.relative_to(NG).as_posix()
        for u in re.findall(r"url\(([^)]+)\)", css.read_text(encoding="utf-8")):
            urls.append(urljoin(osnova, u.strip("'\"")))
    return sorted(set(urls))


@pytest.fixture(scope="module")
def html_a():
    return _pokreni({**UKLJUCEN, "GIT_SHA": SHA_A}, ["/app"])


@pytest.fixture(scope="module")
def html_b():
    return _pokreni({**UKLJUCEN, "GIT_SHA": SHA_B}, ["/app"])


@pytest.fixture(scope="module")
def deploy_b(html_a, html_b):
    """Server B dobija SVE URL-ove iz HTML-a A i B + fontove iz CSS-a + pokušaje van ugovora."""
    ref_a, ref_b = _reference(html_a["/app"]["telo"]), _reference(html_b["/app"]["telo"])
    van = [f"/v2/app/@{TOK_B}/" + p for p in ("tests/live-api.mjs", "package.json", "serve.mjs", "index.html", "README.md",
                                              "src/%2e%2e/serve.mjs", "brand/%2e%2e/package.json", "src/..%5cserve.mjs", "src",
                                              # .js sa dozvoljenom ekstenzijom VAN src/fonts/brand: samo spisak direktorijuma ga zaustavlja
                                              "tests/fixtures/zoom-ext/sw.js", "src/%2e%2e/tests/fixtures/zoom-ext/sw.js")]
    putanje = sorted(set(ref_a + ref_b + _fontovi(TOK_A) + _fontovi(TOK_B) + van))
    return _pokreni({**UKLJUCEN, "GIT_SHA": SHA_B}, putanje), ref_a, ref_b, van


# ── A. BUILD-ADRESIRANJE ──────────────────────────────────────────────────────

def test_token_je_kanonski_build_identitet(html_a, html_b):
    assert html_a["_token"] == TOK_A and html_b["_token"] == TOK_B


def test_a_svaka_lokalna_referenca_nosi_token_a(html_a):
    r = html_a["/app"]
    assert r["status"] == 200 and r["cc"] == "no-store"
    ref = _reference(r["telo"])
    assert ref and all(v.startswith(f"/v2/app/@{TOK_A}/") for v in ref), [v for v in ref if not v.startswith(f"/v2/app/@{TOK_A}/")]


def test_a_b_se_razlikuju_samo_po_tokenu(html_a, html_b):
    ref_a, ref_b = _reference(html_a["/app"]["telo"]), _reference(html_b["/app"]["telo"])
    assert not set(ref_a) & set(ref_b), "isti URL u dva builda = keš može da ih spoji"
    assert [v.replace(f"@{TOK_A}/", f"@{TOK_B}/") for v in ref_a] == ref_b
    assert html_a["/app"]["telo"].replace(f"/v2/app/@{TOK_A}/", f"/v2/app/@{TOK_B}/") == html_b["/app"]["telo"]


# ── B. NEMA MEŠANJA BUILDOVA ─────────────────────────────────────────────────

def test_b_kes_iz_builda_a_ne_moze_da_odgovori_na_html_b(html_a, html_b):
    kes_a = set(_reference(html_a["/app"]["telo"])) | set(_fontovi(TOK_A))
    trazi_b = set(_reference(html_b["/app"]["telo"])) | set(_fontovi(TOK_B))
    assert not kes_a & trazi_b
    assert f"/v2/app/@{TOK_B}/src/app.js" in trazi_b and f"/v2/app/@{TOK_A}/src/app.js" in kes_a


def test_b_server_b_odbija_token_a_bez_kesiranja(deploy_b):
    odg, ref_a, _, _ = deploy_b
    for put in ref_a + _fontovi(TOK_A):
        assert (odg[put]["status"], odg[put]["cc"]) == (404, "no-store"), put


def test_b_server_a_odbija_token_b_smena_instanci(html_b):
    """Stara instanca A koja tokom deploya primi zahtev iz HTML-a B ne sme da vrati
    bajtove A pod URL-om B (immutable bi ih zapamtio)."""
    put = f"/v2/app/@{TOK_B}/src/app.js"
    r = _pokreni({**UKLJUCEN, "GIT_SHA": SHA_A}, [put])[put]
    assert (r["status"], r["cc"]) == (404, "no-store")


def test_b_server_b_servira_sve_svoje_immutable_i_bajt_identicno(deploy_b):
    odg, _, ref_b, _ = deploy_b
    for put in ref_b + _fontovi(TOK_B):
        r = odg[put]
        assert r["status"] == 200, put
        assert r["cc"] == "public, max-age=31536000, immutable" and r["xcto"] == "nosniff", put
        fajl = NG / put[len(f"/v2/app/@{TOK_B}/"):]
        assert r["sha"] == hashlib.sha256(fajl.read_bytes()).hexdigest(), put


# ── C. POTPUN INVENTAR ───────────────────────────────────────────────────────

def test_c_inventar_js_css_fontovi_brand(html_b):
    ref = _reference(html_b["/app"]["telo"])
    izvor = _izvorne_reference()
    assert [v[len(f"/v2/app/@{TOK_B}/"):] for v in ref] == izvor, "svaka izvorna referenca mora biti prepisana, nijedna dodata"
    vrste = {"js": [v for v in izvor if v.startswith("src/") and v.endswith(".js")],
             "css": [v for v in izvor if v.startswith("src/") and v.endswith(".css")],
             "fontovi": [v for v in izvor if v.startswith("fonts/")],
             "brand": [v for v in izvor if v.startswith("brand/")]}
    assert len(vrste["js"]) == len(list((NG / "src").glob("*.js"))), "svaki src/*.js se učitava kroz index.html"
    assert "src/app.js" in vrste["js"] and set(vrste["css"]) == {"src/tokens.css", "src/app.css"}
    assert len(vrste["fontovi"]) >= 6 and len(vrste["brand"]) == 2
    assert sum(map(len, vrste.values())) == len(izvor)
    assert _fontovi(TOK_B), "CSS fontova mora referencirati woff2 fajlove"


def test_c_nijedna_stabilna_putanja_u_novom_html(html_b):
    telo = html_b["/app"]["telo"]
    assert not re.search(r'\b(?:href|src)="(?:src|fonts|brand)/', telo), "relativna putanja asseta"
    assert not re.search(r"/v2/app/(?:src|fonts|brand)/", telo), "stabilna /v2/app/ putanja"
    assert "/v2/preview/" not in telo


def test_c_asseti_ne_referenciraju_apsolutne_v2_putanje():
    """Ako bi neki JS/CSS sam tražio /v2/app/src/… ili /v2/preview/…, zaobišao bi token."""
    for f in [*(NG / "src").glob("*.js"), *(NG / "src").glob("*.css"), *(NG / "fonts").rglob("*.css")]:
        t = re.sub(r"(?m)^\s*//.*$", "", re.sub(r"/\*[\s\S]*?\*/", "", f.read_text(encoding="utf-8")))  # bez komentara
        assert not re.search(r"""["'(]\s*/v2/(?:app|preview)/""", t), f.name


def test_c_van_ugovora_nije_izlozeno(deploy_b):
    odg, _, _, van = deploy_b
    for put in van:
        assert odg[put]["status"] == 404 and odg[put]["cc"] == "no-store", (put, odg[put]["status"])


# ── D. POSTOJEĆE RUTE ────────────────────────────────────────────────────────

D_RUTE = ["/app-legacy", "/app-legacy?posle=app", "/app-v2", "/v2/preview/?rezim=live", "/v2/preview/src/app.js",
          "/v2/preview/fonts/ibm-plex-sans/400.css", "/sw.js", "/"]


def test_d_postojece_rute_iste_sa_i_bez_primarnog():
    preview = {"VINDEX_V2_NG_PREVIEW_ENABLED": "1", "GIT_SHA": SHA_B}
    bez = _pokreni(preview, D_RUTE + ["/app"])
    sa = _pokreni({**preview, **UKLJUCEN}, D_RUTE + ["/app"])
    assert "/static/vindex.js" in bez["/app"]["telo"] and f"/v2/app/@{TOK_B}/src/app.js" in sa["/app"]["telo"]
    assert (bez["/app-legacy"]["status"], bez["/app-legacy"]["norm"]) == (sa["/app-legacy"]["status"], sa["/app-legacy"]["norm"])
    for put in ["/app-v2", "/v2/preview/?rezim=live", "/v2/preview/src/app.js", "/v2/preview/fonts/ibm-plex-sans/400.css", "/sw.js", "/"]:
        assert (bez[put]["status"], bez[put]["norm"], bez[put]["cc"]) == (sa[put]["status"], sa[put]["norm"], sa[put]["cc"]), put
    # preview i dalje servira izvorni index.html (relativne putanje), ne build-adresiran
    assert sa["/v2/preview/?rezim=live"]["sha"] == hashlib.sha256((NG / "index.html").read_bytes()).hexdigest()
    assert "/v2/@" in sa["/app-v2"]["telo"] and "/v2/app/@" not in sa["/app-v2"]["telo"]


def test_d_iskljucen_primarni_nema_build_adresiranih_ruta():
    put = f"/v2/app/@{TOK_B}/src/app.js"
    r = _pokreni({"GIT_SHA": SHA_B}, ["/app", put])
    assert "/static/vindex.js" in r["/app"]["telo"] and "/v2/app/" not in r["/app"]["telo"]
    assert r[put]["status"] == 404
