# -*- coding: utf-8 -*-
"""
BETA-P0-COI §UI — ADVOKAT NIKAD NE SME VIDETI ZELENO ZA PROVERU KOJA NIJE PROŠLA.

Backend popravka bez ove nije popravka: `static/vindex.js:5028` je radio
`if (!d.conflict_detected)` → `✅ Nije pronađen sukob interesa.` Negacija
**odsutnog** polja je `true`, pa je i HTTP 500 sa JSON telom davao zeleno.

Meri se **ono što advokat vidi**, ne oblik odgovora. Zato Playwright: po
invarijanti ovog projekta, dokaz interakcije je izvršenje, ne čitanje koda.
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


def _prikazi(browser, server, *, status=200, telo=None):
    """Učitava PRAVU stranicu i poziva PRAVU `crmPokreniKonflikt`."""
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))

    stranica.route(re.compile(r".*/api/conflict-check"), lambda r: r.fulfill(
        status=status, content_type="application/json",
        body=json.dumps(telo if telo is not None else {})))
    stranica.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(1000)
    stranica.evaluate(
        "() => { window.currentSession = { access_token: 't', user: { id: 'u1' } }; }")
    stranica.evaluate("() => { document.getElementById('cf-ime').value = 'Petar'; }")
    stranica.evaluate("async () => { await crmPokreniKonflikt(); }")
    stranica.wait_for_timeout(400)
    tekst = stranica.evaluate(
        "() => document.getElementById('cf-rezultat').innerText")
    html = stranica.evaluate(
        "() => document.getElementById('cf-rezultat').innerHTML")
    stranica.close()
    return tekst, html, greske


def test_coi_ui_nema_konflikta_kad_je_provera_POTPUNA(browser, server):
    """Pozitivan slučaj mora i dalje da radi."""
    tekst, html, greske = _prikazi(browser, server, status=200, telo={
        "status": "clear", "provera_potpuna": True, "slojevi_greska": [],
        "konflikti": [], "poruka": "Nije pronađen konflikt interesa.",
    })
    assert not greske, greske[:2]
    assert "Nema konflikta" in tekst
    assert "cc-clear" in html


def test_coi_ui_prikazuje_konflikt(browser, server):
    tekst, html, _ = _prikazi(browser, server, status=200, telo={
        "status": "conflict", "provera_potpuna": True, "slojevi_greska": [],
        "konflikti": [{"predmet_naziv": "P1", "opis": "protivna strana",
                       "predmet_status": "aktivan", "tip_konflikta": "tuzeni"}],
        "poruka": "KONFLIKT INTERESA",
    })
    assert "KONFLIKT" in tekst.upper()
    assert "cc-clear" not in html


def test_coi_ui_NEPOTPUNA_provera_NIKAD_nije_zeleno(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    Backend degradira na `review` kad sloj padne (SOA2-006). UI to mora
    imenovati, ne prikazati kao odsustvo konflikta.
    """
    tekst, html, _ = _prikazi(browser, server, status=200, telo={
        "status": "review", "provera_potpuna": False,
        "slojevi_greska": ["predmeti", "klijenti"], "konflikti": [],
        "poruka": "PROVERA NIJE POTPUNA — pretraga nije uspela.",
    })
    assert "cc-clear" not in html, "nepotpuna provera prikazana kao 'nema konflikta'"
    assert "Nema konflikta" not in tekst
    assert "NIJE POTPUNA" in tekst.upper()


def test_coi_ui_HTTP_500_NIKAD_NE_DAJE_ZELENO(browser, server):
    """HTTP greška ranije nije proveravana (`r.ok`)."""
    tekst, html, _ = _prikazi(browser, server, status=503, telo={
        "detail": {"poruka": "Provera nije izvršena."}})
    assert "cc-clear" not in html
    assert "Nema konflikta" not in tekst
    assert "NIJE IZVRŠENA" in tekst.upper()


def test_coi_ui_prazno_telo_ne_daje_zeleno(browser, server):
    tekst, html, _ = _prikazi(browser, server, status=200, telo={})
    assert "cc-clear" not in html
    assert "Nema konflikta" not in tekst
