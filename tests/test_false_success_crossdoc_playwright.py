# -*- coding: utf-8 -*-
"""
BETA-RELIABILITY-FALSE-SUCCESS §11 / FS-P1-01 — CROSS-DOC ANALIZA U PREGLEDAČU.

Tri stanja koja moraju biti razlučiva na ekranu:

    NAĐEN KONFLIKT   →  konflikt se vidi
    NEMA KONFLIKATA  →  „Nisu pronađeni konflikti" (legitimno prazno)
    ANALIZA PALA     →  greška; NIKAD „Nisu pronađeni konflikti"

Treće je pravna tvrdnja o odnosu dokumenata. Do popravke se izgovaralo iz
analize koja nikada nije proizvela nijedan nalaz.
"""
import http.server
import json
import os
import re
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
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", port), Tih)
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


def _analiziraj(browser, server, *, status, telo):
    st = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    st.on("pageerror", lambda e: greske.append(str(e)))
    st.route(re.compile(r".*/api/analiza/cross-doc.*"), lambda r: r.fulfill(
        status=status, content_type="application/json", body=json.dumps(telo)))
    st.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    st.goto(f"{server}/index.html", wait_until="domcontentloaded")
    st.wait_for_timeout(900)
    st.evaluate("""() => {
        window.currentSession = { access_token: 't', user: { id: 'u1' } };
        window.activePredmetId = 'p1';
        window._crossdocSelected = { d1: 'Ugovor A', d2: 'Ugovor B' };
        if (!document.getElementById('crossdoc-result')) {
            const e = document.createElement('div');
            e.id = 'crossdoc-result';
            document.body.appendChild(e);
        }
        const p = document.getElementById('crossdoc-pitanje');
        if (p) p.value = 'Da li postoji konflikt između otkaznih rokova?';
    }""")
    st.evaluate("async () => { await crossdoc_analiziraj(); }")
    st.wait_for_timeout(500)
    tekst = st.evaluate(
        "() => (document.getElementById('crossdoc-result')||{}).innerText || ''")
    st.close()
    return tekst, greske


_NALAZ = {
    "pravno_pitanje": "x", "broj_dokumenata": 2, "nazivi": ["A", "B"],
    "rezime": "", "slicnosti": [], "preporuke": [], "pravni_zakljucak": "",
    "upozorenje_skracenja": None,
}


def test_ui_nadjen_konflikt_se_vidi(browser, server):
    telo = dict(_NALAZ, konflikti=[{
        "dokument_a": "Ugovor A", "dokument_b": "Ugovor B",
        "ozbiljnost": "visoka", "opis": "Otkazni rokovi se razlikuju"}])
    tekst, greske = _analiziraj(browser, server, status=200, telo=telo)
    assert not greske, greske[:2]
    assert "Otkazni rokovi se razlikuju" in tekst
    assert "Nisu pronađeni konflikti" not in tekst


def test_ui_legitimno_prazno_i_dalje_kaze_nema_konflikata(browser, server):
    """SUCCESS_EMPTY mora ostati moguć — inače bi popravka pretvorila svaki
    čist nalaz u grešku."""
    tekst, _ = _analiziraj(browser, server, status=200,
                           telo=dict(_NALAZ, konflikti=[],
                                     rezime="Nema neusaglašenosti."))
    assert "Nisu pronađeni konflikti" in tekst


def test_ui_pad_analize_NIKAD_ne_kaze_da_konflikata_nema(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    Backend sada vraća 500 kad model ne isporuči validan JSON. Ekran to sme
    nazvati greškom — ali nikad odsustvom konflikta.
    """
    tekst, _ = _analiziraj(browser, server, status=500, telo={
        "error": "Greška pri analizi dokumenata. Pokušajte ponovo."})
    assert "Nisu pronađeni konflikti" not in tekst, tekst
    assert "Greška" in tekst or "greška" in tekst


def test_ui_prazno_telo_ne_daje_pravnu_tvrdnju(browser, server):
    tekst, _ = _analiziraj(browser, server, status=500, telo={})
    assert "Nisu pronađeni konflikti" not in tekst
