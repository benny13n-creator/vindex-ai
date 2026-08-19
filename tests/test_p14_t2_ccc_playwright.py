# -*- coding: utf-8 -*-
"""
NIGHT2-A-001 §UI — Command Center ne sme iscrtati tvrdnju o odsustvu kad
izvor nije pročitan.

Pre popravke: `_ccc_render` je izdavao CRVENI čip „Uploaduj prvi dokument"
kad je `dok_stats.ukupno == 0`, bez obzira da li je nula izmerena ili je
upit pao. Meri se ono što advokat VIDI — prava stranica, prava funkcija.
"""
import http.server
import json
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


def _render(browser, server, podaci):
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto("%s/index.html" % server, wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    tekst = stranica.evaluate(
        """(d) => {
            const el = document.createElement('div');
            _ccc_render(el, d);
            return el.innerText;
        }""",
        podaci,
    )
    stranica.close()
    return tekst, greske


def _podaci(**over):
    d = {
        "predmet": {"id": "p1", "naziv": "Spor 1/2026", "tip": "parnicno", "status": "aktivan"},
        "klijenti": [], "dok_stats": {"ukupno": 0, "jaka": 0, "srednja": 0, "slaba": 0},
        "tip_stat": {}, "rokovi": [], "predstojeći": [], "billing": {},
        "aktivnosti": [], "health_score": 70, "nedostajuci": [], "kritican_rok": None,
        "degradirani_izvori": [], "provera_potpuna": True,
    }
    d.update(over)
    return d


def test_ui_kontrola_stvarna_nula_i_dalje_trazi_upload(browser, server):
    """Izmerena nula SME proizvesti poziv na akciju."""
    t, greske = _render(browser, server, _podaci())
    assert not greske, greske[:2]
    assert "Uploaduj prvi dokument" in t
    assert "Nepotpuno" not in t


def test_ui_pad_izvora_NE_trazi_upload_nego_upozorava(browser, server):
    """NAJVAŽNIJI TEST: nula iz palog upita nije nula."""
    t, greske = _render(browser, server, _podaci(
        degradirani_izvori=["dokazi"], provera_potpuna=False))
    assert not greske, greske[:2]
    assert "Uploaduj prvi dokument" not in t, \
        "pao izvor je proizveo poziv na akciju kao da predmet nema dokaze"
    assert "Nepotpuno" in t
    assert "dokazi" in t


def test_ui_degradacija_bez_imena_izvora_i_dalje_upozorava(browser, server):
    t, greske = _render(browser, server, _podaci(provera_potpuna=False))
    assert not greske, greske[:2]
    assert "Nepotpuno" in t
    assert "Uploaduj prvi dokument" not in t


def test_ui_stari_oblik_bez_polja_ne_pada(browser, server):
    """Unazadna kompatibilnost: odgovor bez novih polja se i dalje iscrtava."""
    d = _podaci()
    d.pop("degradirani_izvori")
    d.pop("provera_potpuna")
    t, greske = _render(browser, server, d)
    assert not greske, greske[:2]
    assert "Uploaduj prvi dokument" in t


def _ucitaj(browser, server, status, telo):
    """Vozi PRAVI `ccc_load()` — jedini put na kome se `r.ok` uopste proverava."""
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto("%s/index.html" % server, wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    stranica.route("**/api/ccc/predmeti/**", lambda r: r.fulfill(
        status=status, content_type="application/json", body=json.dumps(telo)))
    stranica.evaluate("""() => {
        window.activePredmetId = 'p1';
        window.currentSession = { access_token: 'test-token' };
        if (!document.getElementById('ccc-container')) {
            const d = document.createElement('div');
            d.id = 'ccc-container';
            document.body.appendChild(d);
        }
    }""")
    stranica.evaluate("() => ccc_load()")
    stranica.wait_for_timeout(400)
    tekst = stranica.evaluate("() => document.getElementById('ccc-container').innerText")
    stranica.close()
    return tekst, greske


def test_ui_HTTP_greska_sa_telom_ne_sme_biti_iscrtana_kao_podatak(browser, server):
    """`r.ok` je jedina odbrana: telo je validno, ali odgovor je non-2xx.
    Ranije je `.then(r => r.json())` parsirao greskovni odgovor kao podatak."""
    for kod in (429, 500, 503):
        t, greske = _ucitaj(browser, server, kod, _podaci())
        assert not greske, greske[:2]
        assert "Uploaduj prvi dokument" not in t, \
            "HTTP %d je iscrtan kao stvarno stanje predmeta" % kod
        assert "Greška" in t or "Greska" in t, kod


def test_ui_HTTP_200_se_i_dalje_iscrtava(browser, server):
    """Kontrola za prethodni test."""
    t, greske = _ucitaj(browser, server, 200, _podaci())
    assert not greske, greske[:2]
    assert "Uploaduj prvi dokument" in t


def test_ui_kriticni_rok_se_prikazuje_kad_postoji(browser, server):
    """Kontrola za drugi čip — bez nje bi blokada koja sve guta prošla."""
    t, greske = _render(browser, server, _podaci(
        kritican_rok={"naziv": "Žalba na presudu", "dana_ostalo": 2}))
    assert not greske, greske[:2]
    assert "Žalba na presudu" in t
