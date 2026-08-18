# -*- coding: utf-8 -*-
"""
B4-M2 §UI — ČINJENICA IZ DOKUMENTA I PRAVNI IZVOR SU DVA RAZLIČITA AUTORITETA.

`_vxRenderIzvori` je do sada iscrtavao samo `d.izvori` pod naslovom „Pravni
izvori". Činjenica iz advokatovog dokumenta nije imala gde da se prikaže, pa
UI nije mogao da razlikuje „dokument NAVODI" od „propis PROPISUJE".

Meri se ono što advokat VIDI. Po invarijanti projekta dokaz interakcije je
izvršenje, ne čitanje izvora.
"""
import http.server
import os
import socket
import socketserver
import threading

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright nije instaliran"
)


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
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
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
    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    r = stranica.evaluate("""(d) => {
        _vxRenderIzvori(d);
        const e = document.getElementById('rag-source-info');
        return e ? {t: e.innerText, h: e.innerHTML, vidljiv: e.style.display !== 'none'} : null;
    }""", odgovor)
    stranica.close()
    assert r is not None, "kontejner `rag-source-info` nije u DOM-u"
    return r, greske


IZVORI = [{"zakon": "ZOO", "clan": "262"}]
CINJ = [{"navod": "Ugovorena kazna iznosi 17.350 EUR.", "dokument": "ugovor.pdf",
         "chunk": 0, "source_type": "USER_DOCUMENT", "verification_state": "READ_OK"}]


def test_ui_oba_autoriteta_su_odvojena(browser, server):
    r, greske = _prikazi(browser, server, {
        "izvori": IZVORI, "cinjenice_iz_dokumenta": CINJ, "izvori_neuspeh": []})
    assert not greske, greske[:2]
    assert "Činjenica iz vašeg dokumenta" in r["t"]
    assert "Pravni izvori" in r["t"]
    assert "17.350" in r["t"] and "ugovor.pdf" in r["t"]
    assert "ZOO" in r["t"]
    # Dokumentarni navod NE SME biti unutar bloka pravnih izvora.
    i_dok = r["h"].index("vx-dok-nas")
    i_zak = r["h"].index("vx-izvori-nas")
    i_navod = r["h"].index("17.350")
    assert i_dok < i_navod < i_zak, "dokumentarni navod je unutar pravnih izvora"


def test_ui_dokument_je_oznacen_kao_nepotvrdjen(browser, server):
    """INVARIANT 3/4: pročitano ≠ pravno potvrđeno."""
    r, greske = _prikazi(browser, server, {
        "izvori": [], "cinjenice_iz_dokumenta": CINJ, "izvori_neuspeh": []})
    assert not greske, greske[:2]
    assert "nije pravno potvrđen" in r["t"]
    assert "Pravni izvori" not in r["t"], "prikazan pravni blok bez pravnih izvora"


def test_ui_dokument_OK_korpus_FAILED(browser, server):
    """CASE B na ekranu: činjenica DA, uz izričito „nije provereno"."""
    r, greske = _prikazi(browser, server, {
        "izvori": [], "cinjenice_iz_dokumenta": CINJ,
        "izvori_neuspeh": ["zakonski korpus"]})
    assert not greske, greske[:2]
    assert r["vidljiv"]
    assert "17.350" in r["t"]
    assert "zakonski korpus" in r["t"] and "⚠" in r["t"]
    assert "NIJE potvrđeno" in r["t"]


def test_ui_dokument_FAILED_ne_prikazuje_cinjenicu(browser, server):
    """INVARIANT 5/6: backend šalje praznu listu — UI ne sme ništa izmisliti."""
    r, greske = _prikazi(browser, server, {
        "izvori": IZVORI, "cinjenice_iz_dokumenta": [],
        "izvori_neuspeh": ["dokumenti predmeta"]})
    assert not greske, greske[:2]
    assert "Činjenica iz vašeg dokumenta" not in r["t"]
    assert "dokumenti predmeta" in r["t"]


def test_ui_ne_prikazuje_stavku_koja_tvrdi_pravni_autoritet(browser, server):
    """Defense-in-depth: čak i ako backend pošalje LEGAL_CORPUS, UI ga odbija."""
    lazno = [dict(CINJ[0], source_type="LEGAL_CORPUS")]
    r, greske = _prikazi(browser, server, {
        "izvori": IZVORI, "cinjenice_iz_dokumenta": lazno, "izvori_neuspeh": []})
    assert not greske, greske[:2]
    assert "Činjenica iz vašeg dokumenta" not in r["t"]
    assert "17.350" not in r["t"]


def test_ui_reset_izmedju_odgovora(browser, server):
    """Provenance prethodnog odgovora ne sme preživeti sledeći."""
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    t = stranica.evaluate("""() => {
        _vxRenderIzvori({izvori: [], cinjenice_iz_dokumenta: [{
            navod:'17.350 EUR', dokument:'ugovor.pdf', chunk:0,
            source_type:'USER_DOCUMENT', verification_state:'READ_OK'}],
            izvori_neuspeh:['zakonski korpus']});
        _vxRenderIzvori({izvori: [{zakon:'ZOO', clan:'262'}],
                         cinjenice_iz_dokumenta: [], izvori_neuspeh: []});
        return document.getElementById('rag-source-info').innerText;
    }""")
    stranica.close()
    assert "17.350" not in t, "dokumentarna činjenica je preživela sledeći odgovor"
    assert "⚠" not in t
    assert "ZOO" in t
