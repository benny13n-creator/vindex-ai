# -*- coding: utf-8 -*-
"""
B4 §UI — PARCIJALAN ODGOVOR NE SME IZGLEDATI KAO POTPUNO PROVEREN.

Backend popravka bez ove nije potpuna: `_vxRenderIzvori` je iscrtavao ISKLJUČIVO
`d.izvori` — dakle samo ono što JESTE pročitano. Kad je pretraga advokatovih
dokumenata pala, lista pravnih izvora je izgledala normalno, a advokat nije imao
nijedan način da sazna da njegovi dokumenti uopšte nisu pretraženi.

Meri se ono što advokat VIDI. Po invarijanti ovog projekta dokaz interakcije je
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
    """Učitava PRAVU stranicu i zove PRAVI `_vxRenderIzvori`."""
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    tekst = stranica.evaluate("""(d) => {
        _vxRenderIzvori(d);
        const e = document.getElementById('rag-source-info');
        return e ? {t: e.innerText, vidljiv: e.style.display !== 'none'} : null;
    }""", odgovor)
    stranica.close()
    assert tekst is not None, "kontejner `rag-source-info` nije u DOM-u"
    return tekst["t"], tekst["vidljiv"], greske


IZVORI = [{"zakon": "ZOO", "clan": "262"}]


def test_b4_ui_potpun_odgovor_nema_upozorenje(browser, server):
    tekst, vidljiv, greske = _prikazi(browser, server, {
        "izvori": IZVORI, "izvori_neuspeh": []})
    assert not greske, greske[:2]
    assert vidljiv and "ZOO" in tekst
    assert "⚠" not in tekst


def test_b4_ui_parcijalan_odgovor_MORA_biti_oznacen(browser, server):
    """NAJVAŽNIJI TEST U FAJLU: zakon pročitan, dokumenti NISU."""
    tekst, vidljiv, greske = _prikazi(browser, server, {
        "izvori": IZVORI, "izvori_neuspeh": ["dokumenti predmeta"]})
    assert not greske, greske[:2]
    assert vidljiv
    assert "⚠" in tekst, "parcijalan odgovor prikazan kao potpuno proveren"
    assert "dokumenti predmeta" in tekst
    assert "ZOO" in tekst, "pravni izvori moraju ostati prikazani"


def test_b4_ui_oznaka_se_vidi_i_bez_ijednog_izvora(browser, server):
    """Ranije: prazna lista `izvori` -> ceo blok se sakrivao -> nula informacije."""
    tekst, vidljiv, greske = _prikazi(browser, server, {
        "izvori": [], "izvori_neuspeh": ["zakonski korpus", "dokumenti predmeta"]})
    assert not greske, greske[:2]
    assert vidljiv, "blok je sakriven iako izvori nisu provereni"
    assert "zakonski korpus" in tekst and "dokumenti predmeta" in tekst
    assert "NIJE potvrđeno" in tekst


def test_b4_ui_stanje_se_resetuje_izmedju_odgovora(browser, server):
    """Upozorenje prethodnog odgovora ne sme ostati uz sledeći."""
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    tekst = stranica.evaluate("""() => {
        _vxRenderIzvori({izvori: [], izvori_neuspeh: ['dokumenti predmeta']});
        _vxRenderIzvori({izvori: [{zakon:'ZOO', clan:'262'}], izvori_neuspeh: []});
        return document.getElementById('rag-source-info').innerText;
    }""")
    stranica.close()
    assert "⚠" not in tekst, "upozorenje je preživelo sledeći, uspešan odgovor"
    assert "ZOO" in tekst
