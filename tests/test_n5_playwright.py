# -*- coding: utf-8 -*-
"""
N5 §UI — pad izvora NIKAD ne sme biti iscrtan kao pozitivno stanje.

Backend popravka bez ovoga ne bi bila dokazana: `degradirani_izvori` postoji
isključivo zato da bi ga korisnički sloj prikazao.

Pre N5 je `_wsRender` (vindex.js) na `ukupno_aktivnih == 0` iscrtavao zeleni
✓ „Sve je pod kontrolom — Nema otvorenih akcija koje zahtevaju pažnju.", a
`_dashRender` nule kao stvarno stanje kancelarije — u oba slučaja i kad su
upiti pali.

Meri se ono što advokat VIDI: prava stranica, prave render funkcije.
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


def _render(browser, server, funkcija, podaci):
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto("%s/index.html" % server, wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    tekst = stranica.evaluate(
        """([fn, d]) => {
            const html = (fn === 'ws') ? _wsRender(d) : _dashRender(d, null, null);
            const el = document.createElement('div');
            el.innerHTML = html;
            return el.innerText;
        }""",
        [funkcija, podaci],
    )
    stranica.close()
    return tekst, greske


PRAZNO_CISTO = {
    "danas": [], "kriticno": [], "predstojece": [], "za_pregled": [],
    "na_cekanju": [], "zavrseno_nedavno": [], "ukupno_aktivnih": 0,
    "predmeta_sa_akcijama": 0, "degradirani_izvori": [], "provera_potpuna": True,
}


def _degradirano(**over):
    d = dict(PRAZNO_CISTO)
    d.update({"degradirani_izvori": ["otvorene akcije"], "provera_potpuna": False})
    d.update(over)
    return d


# ── WORKSPACE ────────────────────────────────────────────────────────────────

def test_ui_ws_cisto_prazno_i_dalje_kaze_sve_je_pod_kontrolom(browser, server):
    """KONTROLA: validno prazno mora ostati validno prazno."""
    t, greske = _render(browser, server, "ws", PRAZNO_CISTO)
    assert not greske, greske[:2]
    assert "Sve je pod kontrolom" in t
    assert "nije potpun" not in t


def test_ui_ws_pad_izvora_NE_kaze_sve_je_pod_kontrolom(browser, server):
    """NAJVAŽNIJI TEST U FAJLU."""
    t, greske = _render(browser, server, "ws", _degradirano())
    assert not greske, greske[:2]
    assert "Sve je pod kontrolom" not in t, "pad izvora iscrtan kao pozitivno stanje"
    assert "Pregled nije potpun" in t
    assert "otvorene akcije" in t, "advokat ne vidi koji izvor nije pročitan"
    assert "NIJE potvrda" in t


def test_ui_ws_pad_uz_postojece_stavke_i_dalje_upozorava(browser, server):
    """Parcijalni pad: nešto se vidi, ali provera nije potpuna."""
    d = _degradirano(ukupno_aktivnih=2, danas=[{
        "vrsta": "case_action", "id": "a1", "predmet_id": "p1",
        "predmet_naziv": "Spor 1/2026", "naslov": "Podnesi žalbu",
        "tip": "ROK", "prioritet": "critical", "rok": "2026-08-20",
        "izvor": {}, "created_at": "2026-08-18T00:00:00Z"}])
    t, greske = _render(browser, server, "ws", d)
    assert not greske, greske[:2]
    assert "Pregled nije potpun" in t
    assert "Sve je pod kontrolom" not in t
    assert "Spor 1/2026" in t, "poznate stavke se ne smeju sakriti"


def test_ui_ws_provera_potpuna_false_bez_imena_izvora(browser, server):
    """Ni bez liste imena se ne sme tvrditi da je sve čisto."""
    d = dict(PRAZNO_CISTO)
    d["provera_potpuna"] = False
    t, greske = _render(browser, server, "ws", d)
    assert not greske, greske[:2]
    assert "Sve je pod kontrolom" not in t
    assert "nije potpun" in t


def test_ui_ws_stari_oblik_bez_polja_ne_pada(browser, server):
    """Unazadna kompatibilnost: odgovor bez novih polja se i dalje iscrtava."""
    d = {k: v for k, v in PRAZNO_CISTO.items()
         if k not in ("degradirani_izvori", "provera_potpuna")}
    t, greske = _render(browser, server, "ws", d)
    assert not greske, greske[:2]
    assert "Sve je pod kontrolom" in t


# ── DASHBOARD ────────────────────────────────────────────────────────────────

DASH_CISTO = {
    "ukupno_predmeta": 0, "ukupno_aktivnih": 0, "hitni_rokovi": [],
    "rokovi_7_dana": 0, "rokovi_dostupni": True, "neaktivni_30_dana": [],
    "predmeti_visok_rizik": [], "novi_dokumenti": [], "statistike": {},
    "degradirani_izvori": [], "provera_potpuna": True,
}


def test_ui_dash_cisto_nema_upozorenja(browser, server):
    t, greske = _render(browser, server, "dash", DASH_CISTO)
    assert not greske, greske[:2]
    assert "nepotpuni" not in t


def test_ui_dash_pad_izvora_upozorava(browser, server):
    d = dict(DASH_CISTO)
    d.update({"degradirani_izvori": ["fakture", "ročišta"], "provera_potpuna": False})
    t, greske = _render(browser, server, "dash", d)
    assert not greske, greske[:2]
    assert "nepotpuni" in t, "Command Center prikazuje nule bez ijednog upozorenja"
    assert "fakture" in t and "ročišta" in t
    assert "NIJE potvrda" in t
