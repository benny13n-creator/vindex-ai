# -*- coding: utf-8 -*-
"""B4-M2 FAZA 5 — UI DOKAZ NAD STVARNIM PRODUKCIONIM ODGOVORIMA.

„Backend ima podatak" NIJE dokaz. Ovde se iscrtava stvarni `index.html` u
pravom pretraživaču i meri se ono što advokat VIDI.

Ulaz NISU sintetički objekti nego DOSLOVNI odgovori snimljeni sa produkcije
(`POST /api/pitanje`, commit `6458587`) tokom živog A/J merenja:

    tests/fixtures/ns003/live_response_A.json   confidence MEDIUM, normalan put
    tests/fixtures/ns003/live_response_J.json   confidence LOW — pravni deo NIJE
                                                proizveo normalan odgovor

Ključno pitanje ovog paketa: kada pravni deo padne, da li advokat i dalje vidi
činjenicu iz sopstvenog dokumenta.
"""
import http.server
import io
import json
import os
import socket
import socketserver
import threading

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_KOREN, "tests", "fixtures", "ns003")

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright nije instaliran")

CINJENICA = "847.250,00"
DOKUMENT = "dokument_a.docx"


def _ucitaj(oz):
    p = os.path.join(_FIX, "live_response_%s.json" % oz)
    return json.load(io.open(p, encoding="utf-8"))


@pytest.fixture(scope="module")
def server():
    class Tih(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=_KOREN, **kw)

        def log_message(self, *a):
            pass

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Tih)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield "http://127.0.0.1:%d" % port
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def _prikazi(browser, server, odgovor):
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto("%s/index.html" % server, wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    r = stranica.evaluate("""(d) => {
        _vxRenderIzvori(d);
        const e = document.getElementById('rag-source-info');
        return e ? {t: e.innerText, h: e.innerHTML, vidljiv: e.style.display !== 'none'} : null;
    }""", odgovor)
    stranica.close()
    assert r is not None, "kontejner `rag-source-info` nije u DOM-u"
    return r, greske


# ═══════════════════════════════════════════════════════════════════════════
# 1 — SCENARIO J: PRAVNI DEO JE PAO, ČINJENICA MORA BITI VIDLJIVA
# ═══════════════════════════════════════════════════════════════════════════

def test_J_advokat_vidi_cinjenicu_kada_pravni_deo_padne(browser, server):
    """Jezgro B4: pravni retrieval LOW, a činjenica iz dokumenta na ekranu."""
    zapis = _ucitaj("J")
    assert zapis["_meta"]["legal_status"] == "A_pravni_LOW", (
        "fixture nije snimak pravnog neuspeha — dokaz ne bi merio B4")
    r, greske = _prikazi(browser, server, zapis["response"])
    assert not greske, greske[:2]
    assert "Činjenica iz vašeg dokumenta" in r["t"], (
        "advokat NE vidi blok sa činjenicom kada pravni deo padne")
    assert CINJENICA in r["t"], "iznos iz dokumenta nije na ekranu"
    assert DOKUMENT in r["t"], "izvor činjenice nije imenovan"
    assert r["vidljiv"] is True, "blok postoji u DOM-u ali je sakriven"


def test_J_cinjenica_nije_prikazana_kao_pravni_izvor(browser, server):
    """Dokument NAVODI, propis PROPISUJE — dva različita autoriteta."""
    r, _g = _prikazi(browser, server, _ucitaj("J")["response"])
    assert "nije pravno potvrđen" in r["t"], (
        "nedostaje ograda da dokumentarni navod NIJE pravno potvrđen")
    i_dok = r["h"].index("vx-dok-nas")
    i_navod = r["h"].index(CINJENICA.replace(",", ","))
    assert i_dok < i_navod, "navod je iscrtan izvan dokumentarnog bloka"


# ═══════════════════════════════════════════════════════════════════════════
# 2 — SCENARIO A: KONTROLA
# ═══════════════════════════════════════════════════════════════════════════

def test_A_cinjenica_vidljiva_na_normalnom_putu(browser, server):
    r, greske = _prikazi(browser, server, _ucitaj("A")["response"])
    assert not greske, greske[:2]
    assert "Činjenica iz vašeg dokumenta" in r["t"]
    assert CINJENICA in r["t"]


# ═══════════════════════════════════════════════════════════════════════════
# 3 — NEGATIVNA: BEZ IZVORA NEMA BLOKA
# ═══════════════════════════════════════════════════════════════════════════

def test_bez_dokumentarnog_izvora_UI_ne_prikazuje_blok(browser, server):
    """Isti oblik odgovora, ali prazan kanal — UI ne sme ništa da izmisli.
    Odgovara stanju izmerenom na tenantu bez ijednog dokumenta (NEG 5/5)."""
    zapis = _ucitaj("J")["response"]
    prazan = dict(zapis)
    prazan["cinjenice_iz_dokumenta"] = []
    r, greske = _prikazi(browser, server, prazan)
    assert not greske, greske[:2]
    assert "Činjenica iz vašeg dokumenta" not in r["t"], (
        "UI iscrtava dokumentarni blok bez ijedne činjenice")
    assert CINJENICA not in r["t"]


def test_fixture_su_stvarni_produkcioni_odgovori(browser, server):
    """Zaključava poreklo dokaza: ako neko zameni fixture sintetičkim objektom,
    ovaj test pada i UI dokaz prestaje da bude živ."""
    for oz in ("A", "J"):
        m = _ucitaj(oz)["_meta"]
        assert m["commit"] == "6458587"
        assert m["izvor"].startswith("STVARAN produkcioni odgovor")
        assert "847.250,00" in json.dumps(_ucitaj(oz)["response"], ensure_ascii=False)
