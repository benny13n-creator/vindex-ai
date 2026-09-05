# -*- coding: utf-8 -*-
"""
Z015 W1.0 — RUTE I DOKUMENT VINDEX V2.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. `/app-v2` i `/app` MORAJU servirati razlicite dokumente. Ako bi neko ikad
     spojio te dve rute "da se ne duplira kod", V2 URL bi vratio legacy
     aplikaciju — a to je tacno kvar zbog koga je Z015 §11 uopste napisan.
     `test_v2_i_legacy_nisu_isti_dokument` obara bas to.

  2. V2 dokument NE SME referencirati nijedan legacy asset. Legacy `index.html`
     ucitava `/static/vindex.js` (1,2 MB) i `/static/vindex.css`; jedan
     zaboravljen `<script>` bi vratio globalnu promenljivu `window.supabase` i
     ceo legacy runtime u V2. `test_dokument_nema_nijedan_legacy_asset` obara to.

  3. Asseti nose verziju U PUTANJI i zato smeju `immutable` kes od godinu dana.
     Da neko vrati legacy `?v=` model, ista putanja bi se kesirala godinu dana
     sa promenljivim sadrzajem. `test_asset_nosi_immutable_kes` obara to.

  4. Ruta asseta ne sme sluziti kao citac fajlova van `v2/`.
     `test_asset_ne_izlazi_iz_v2_direktorijuma` obara to.
"""
import os
import re
import sys

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, KOREN)

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

klijent = TestClient(api.app)

LEGACY_ASSETI = [
    "/static/vindex.js",
    "/static/vindex.css",
    "/static/supabase.min.js",
    "font-awesome",
    "fontawesome",
    "vindex-system.css",
]


@pytest.fixture(scope="module")
def dokument():
    r = klijent.get("/app-v2")
    assert r.status_code == 200
    return r.text


# ─── Rute ─────────────────────────────────────────────────────────────────────

def test_app_v2_postoji():
    r = klijent.get("/app-v2")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_child_ruta_servira_isti_dokument():
    """Ruter je na klijentu, pa deep link i osvezavanje moraju raditi."""
    a = klijent.get("/app-v2")
    b = klijent.get("/app-v2/predmeti")
    c = klijent.get("/app-v2/nepoznata-putanja")
    assert b.status_code == c.status_code == 200
    assert a.text == b.text == c.text


def test_v2_i_legacy_nisu_isti_dokument():
    v2 = klijent.get("/app-v2").text
    legacy = klijent.get("/app").text
    assert v2 != legacy
    # Legacy je red velicine 400 kB; V2 dokument je minimalan po projektu.
    assert len(v2) < 8000, "V2 dokument je narastao — proveri da nije uvucen legacy sadrzaj"
    assert len(legacy) > 100_000


def test_dokument_se_ne_kesira():
    r = klijent.get("/app-v2")
    assert "no-store" in r.headers.get("cache-control", "")


# ─── Kontaminacija legacy-jem ────────────────────────────────────────────────

def test_dokument_nema_nijedan_legacy_asset(dokument):
    nadjeni = [a for a in LEGACY_ASSETI if a.lower() in dokument.lower()]
    assert nadjeni == [], f"V2 dokument referencira legacy assete: {nadjeni}"


def test_dokument_nema_inline_rukovaoce(dokument):
    assert not re.search(r"\son(click|change|submit|load|input)\s*=", dokument, re.I)


def test_skripta_je_es_modul_iz_v2_prostora(dokument):
    skripte = re.findall(r'<script[^>]*src="([^"]+)"[^>]*>', dokument)
    assert len(skripte) == 1, f"ocekivan tacno jedan modul, nadjeno: {skripte}"
    assert skripte[0].startswith("/v2/@")
    assert 'type="module"' in dokument


def test_stilovi_dolaze_iz_v2_prostora_ili_google_fonts(dokument):
    stilovi = re.findall(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"', dokument)
    stilovi += re.findall(r'<link[^>]+href="([^"]+)"[^>]*rel="stylesheet"', dokument)
    assert stilovi, "dokument nema nijedan stylesheet"
    for s in stilovi:
        assert s.startswith("/v2/@") or s.startswith("https://fonts.googleapis.com"), s


def test_legacy_pisma_nisu_u_v2(dokument):
    """Owner canon: Source Serif 4 / Source Sans 3 / JetBrains Mono.
    Cormorant Garamond i Plus Jakarta Sans su legacy i zabranjeni u V2."""
    assert "Cormorant" not in dokument
    assert "Jakarta" not in dokument
    assert "Source+Serif+4" in dokument
    assert "Source+Sans+3" in dokument
    assert "JetBrains+Mono" in dokument


# ─── Verzionisani asseti ─────────────────────────────────────────────────────

def test_dokument_nosi_verziju_u_putanji(dokument):
    baze = set(re.findall(r"/v2/@([A-Za-z0-9._-]+)/", dokument))
    assert len(baze) == 1, f"vise razlicitih verzija u istom dokumentu: {baze}"
    assert "__V2_BASE__" not in dokument, "zamena tokena nije izvrsena"


def _baza(dokument):
    return "/v2/@" + re.findall(r"/v2/@([A-Za-z0-9._-]+)/", dokument)[0]


def test_svi_referencirani_asseti_se_serviraju(dokument):
    putanje = set(re.findall(r'(/v2/@[A-Za-z0-9._-]+/[^"\']+)', dokument))
    assert putanje, "dokument ne referencira nijedan V2 asset"
    for p in sorted(putanje):
        r = klijent.get(p)
        assert r.status_code == 200, f"{p} -> {r.status_code}"


def test_asset_nosi_immutable_kes(dokument):
    r = klijent.get(_baza(dokument) + "/boot.js")
    cc = r.headers.get("cache-control", "")
    assert "immutable" in cc and "max-age=31536000" in cc
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "javascript" in r.headers.get("content-type", "")


def test_css_asset_ima_ispravan_tip(dokument):
    r = klijent.get(_baza(dokument) + "/styles/tokens.css")
    assert r.status_code == 200
    assert "text/css" in r.headers.get("content-type", "")


def test_asset_ne_izlazi_iz_v2_direktorijuma(dokument):
    for zlo in ["../api.py", "..%2fapi.py", "../../.env", "/etc/passwd"]:
        r = klijent.get(f"{_baza(dokument)}/{zlo}")
        assert r.status_code == 404, f"{zlo} -> {r.status_code}"


def test_nepostojeci_asset_je_404(dokument):
    assert klijent.get(_baza(dokument) + "/nema-me.js").status_code == 404


def test_stara_verzija_i_dalje_servira():
    """Immutable model znaci da otvoren dokument sme da dovuce svoju verziju
    i posle novog builda. Token se namerno NE proverava."""
    assert klijent.get("/v2/@bilo-koja-stara-verzija/boot.js").status_code == 200


# ─── Legacy ostaje netaknut ──────────────────────────────────────────────────

def test_legacy_app_i_dalje_radi():
    r = klijent.get("/app")
    assert r.status_code == 200
    assert "vindex.js" in r.text


def test_v2_ne_dira_legacy_staticke_rute():
    for p in ["/static/vindex.js", "/static/vindex.css", "/sw.js"]:
        assert klijent.get(p).status_code == 200, p
