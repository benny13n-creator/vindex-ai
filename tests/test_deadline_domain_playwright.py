# -*- coding: utf-8 -*-
"""
BETA-DEADLINE-DOMAIN-001 §E — ONO ŠTO ADVOKAT VIDI KAD ROKOVI NISU PROČITANI.

Tri stanja koja su do sada na ekranu izgledala identično:

    STVARAN ROK      →  rok se vidi
    PRAZAN DAN       →  sekcija rokova ćuti (legitimno)
    UPIT PAO         →  ranije: sekcija rokova ćuti — ISTO kao prazan dan

Treće stanje je razlog zbog kog ovaj domen postoji: advokat koji vidi prazno
zaključuje da rokova nema. Meri se izvršenje u pregledaču, ne izvor.
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

_OSNOVA = {
    "ukupno_predmeta": 3, "ukupno_aktivnih": 2, "predmeti_truncated": False,
    "rokovi_7_dana": [], "hitni_rokovi": [], "neaktivni_30_dana": [],
    "danasnja_rocista": [], "predmeti_visok_rizik": [], "pad_procene": [],
    "novi_dokumenti": [], "summary": "Sve je pod kontrolom — nema hitnih upozorenja.",
    "statistike": {},
}


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
    # BETA-NIGHT-STABILIZATION / TASK 9: jednonitni `TCPServer` serijalizuje
    # SVE zahteve. Pregledac za `index.html` otvara vise paralelnih konekcija
    # (HTML + 9.5k linija JS + CSS + fontovi), pa jedna spora blokira ostale i
    # `domcontentloaded` ume da probije 30s -- izmereno kao flake u punoj suiti.
    # Threading varijanta nije „veci timeout" nego uklanjanje uskog grla.
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


def _prikazi(browser, server, telo):
    st = browser.new_page(viewport={"width": 1280, "height": 1000})
    greske = []
    st.on("pageerror", lambda e: greske.append(str(e)))
    st.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    st.goto(f"{server}/index.html", wait_until="domcontentloaded")
    st.wait_for_timeout(900)
    st.evaluate("""(d) => {
        window.currentSession = { access_token: 't', user: { id: 'u1' } };
        // `portfolio_render` je PRAVA funkcija koju `portfolio_load()` zove
        // posle odgovora sa `/portfolio/dashboard`. Elementi vec postoje u
        // `index.html`; `portfolio-strip` je uslov za rani izlaz.
        for (const id of ['portfolio-strip', 'portfolio-rokovi',
                          'portfolio-rokovi-list', 'portfolio-hitni',
                          'portfolio-hitni-list']) {
            if (!document.getElementById(id)) {
                const e = document.createElement('div');
                e.id = id; e.style.display = 'none';
                document.body.appendChild(e);
            }
        }
        portfolio_render(d);
    }""", telo)
    st.wait_for_timeout(300)
    stanje = st.evaluate("""() => {
        const el = document.getElementById('portfolio-rokovi-list');
        const sek = document.getElementById('portfolio-rokovi');
        return { tekst: el ? el.innerText : '',
                 vidljiva: sek ? sek.style.display !== 'none' : false };
    }""")
    st.close()
    return stanje, greske


def test_ui_stvaran_rok_se_vidi(browser, server):
    telo = dict(_OSNOVA, rokovi_dostupni=True, rokovi_7_dana=[{
        "predmet_id": "p1", "predmet_naziv": "Marković", "dogadjaj": "Rok: žalba",
        "datum_iso": "2026-09-01", "vaznost": "kritičan", "izvor": "predmet_hronologija"}])
    stanje, greske = _prikazi(browser, server, telo)
    assert not greske, greske[:2]
    assert stanje["vidljiva"]
    assert "Rok: žalba" in stanje["tekst"]
    assert "nisu dostupni" not in stanje["tekst"]


def test_ui_prazan_dan_ne_uzbunjuje(browser, server):
    """Legitimno prazno NE sme da izgleda kao greška — inače bi popravka
    proizvela lažnu uzbunu svakog mirnog dana."""
    stanje, _ = _prikazi(browser, server, dict(_OSNOVA, rokovi_dostupni=True))
    assert "nisu dostupni" not in stanje["tekst"]


def test_ui_neuspeh_NIKAD_ne_izgleda_kao_prazan_dan(browser, server):
    """NAJVAŽNIJI TEST U FAJLU."""
    stanje, _ = _prikazi(browser, server, dict(_OSNOVA, rokovi_dostupni=False))
    assert stanje["vidljiva"], "sekcija rokova ćuti iako upit nije uspeo"
    assert "nisu dostupni" in stanje["tekst"]
    assert "NE znači da ih nema" in stanje["tekst"]


def test_ui_neuspeh_i_prazno_daju_RAZLICIT_ekran(browser, server):
    """Doslovno pravilo iz mandata: EMPTY ≠ FAILURE."""
    prazno, _ = _prikazi(browser, server, dict(_OSNOVA, rokovi_dostupni=True))
    pao, _ = _prikazi(browser, server, dict(_OSNOVA, rokovi_dostupni=False))
    assert prazno["tekst"] != pao["tekst"]


def test_ui_stari_odgovor_bez_polja_se_ne_tretira_kao_neuspeh(browser, server):
    """Kompatibilnost: odgovor bez `rokovi_dostupni` (npr. keširan stariji
    payload) ne sme da pali lažnu uzbunu."""
    stanje, _ = _prikazi(browser, server, dict(_OSNOVA))
    assert "nisu dostupni" not in stanje["tekst"]
