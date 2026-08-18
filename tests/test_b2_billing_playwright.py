# -*- coding: utf-8 -*-
"""
B2 §UI — ADVOKAT NE SME VIDETI IZNOS IZ PRETRAGE KOJA NIJE USPELA.

Backend popravka bez ove nije potpuna: `billing_renderReport` je iscrtavao
`Math.round(d.ukupno_naplaceno_rsd || 0)` kao podebljan iznos, bez ijednog
polja koje bi razlikovalo „nula jer nema faktura" od „nula jer upit nije
uspeo".

Meri se ono što advokat VIDI. Po invarijanti ovog projekta dokaz interakcije je
izvršenje, ne čitanje izvora.
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


def _otvori_izvestaj(browser, server, tip, *, status=200, telo=None):
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))

    # Redosled: prvo opšte, pa specifično — Playwright bira POSLEDNJU rutu koja
    # se poklapa, pa bi catch-all inače presreo i sam merени poziv.
    stranica.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))
    stranica.route(re.compile(r".*/api/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    stranica.route(re.compile(r".*/billing/report/.*"), lambda r: r.fulfill(
        status=status, content_type="application/json",
        body=json.dumps(telo if telo is not None else {})))

    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(1000)
    stranica.evaluate(
        "() => { window.currentSession = { access_token: 't', user: { id: 'u1' } }; }")
    tekst = stranica.evaluate("""async (tip) => {
        await billing_openReport(tip);
        const e = document.getElementById('billing-report-result');
        return e ? e.innerText : null;
    }""", tip)
    stranica.close()
    assert tekst is not None, "kontejner izveštaja nije u DOM-u"
    return tekst, greske


_POTPUN_GODISNJI = {
    "godina": 2026, "ukupno_uneseno_rsd": 19500.0, "ukupno_fakturisano": 23400.0,
    "ukupno_naplaceno_rsd": 9000.0, "stopa_naplate_pct": 38.5,
    "po_mesecima": [], "top_klijenti": [], "top_tipovi_predmeta": [],
    "nepotpuno": [],
}


def test_b2_ui_potpun_izvestaj_nema_upozorenje(browser, server):
    tekst, greske = _otvori_izvestaj(browser, server, "godisnji", telo=_POTPUN_GODISNJI)
    assert not greske, greske[:2]
    assert "9.000" in tekst or "9000" in tekst
    assert "⚠" not in tekst


def test_b2_ui_nepotpun_izvestaj_MORA_biti_oznacen(browser, server):
    """NAJVAŽNIJI TEST U FAJLU: grupa izvedena iz pale pretrage mora biti imenovana."""
    telo = dict(_POTPUN_GODISNJI, nepotpuno=["tipovi predmeta"])
    tekst, greske = _otvori_izvestaj(browser, server, "godisnji", telo=telo)
    assert not greske, greske[:2]
    assert "⚠" in tekst, "nepotpun izveštaj prikazan kao potpun"
    assert "tipovi predmeta" in tekst


def test_b2_ui_503_ne_prikazuje_nulu(browser, server):
    """Pao izvor broja -> 503. Ekran sme reći grešku, ali NIKAD `0 RSD`."""
    tekst, greske = _otvori_izvestaj(
        browser, server, "godisnji", status=503,
        telo={"detail": "Izveštaj nije izračunat — izvor „fakture” trenutno nije dostupan."})
    assert not greske, greske[:2]
    assert "0 RSD" not in tekst
    assert "nije izračunat" in tekst


def test_b2_ui_po_tipu_nepotpun_oznacen(browser, server):
    telo = {"od": "2026-01-01", "do": "2026-08-18", "ukupno_rsd": 19500.0,
            "po_tipu": [], "nepotpuno": ["tipovi predmeta"]}
    tekst, greske = _otvori_izvestaj(browser, server, "po-tipu", telo=telo)
    assert not greske, greske[:2]
    assert "⚠" in tekst


def test_b2_ui_po_klijentu_503_ne_kaze_nema_faktura(browser, server):
    """`po_klijentu: []` je frontend ispisivao kao „Nema faktura za ovaj period."."""
    tekst, greske = _otvori_izvestaj(
        browser, server, "po-klijentu", status=503,
        telo={"detail": "Izveštaj nije izračunat — izvor „fakture” trenutno nije dostupan."})
    assert not greske, greske[:2]
    assert "Nema faktura" not in tekst
    assert "nije izračunat" in tekst
