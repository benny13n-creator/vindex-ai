# -*- coding: utf-8 -*-
"""
BETA-DATA-ID-01 §10 — STATUS INDEKSIRANJA MORA BITI VIDLJIV ADVOKATU.

ZAŠTO OVAJ FAJL POSTOJI

Sprint 004 je popravio `static/vindex.js` da indikator „vektorizovan" izvodi iz
`dok.status` umesto iz `dok.pinecone_namespace`, koji se upisuje **bezuslovno**
— i time se dokument koji nikad nije stigao u indeks renderovao piksel-identično
indeksiranom.

Ali ta popravka je zatvorena **čitanjem koda i `node --check`**, bez izvršnog
dokaza. Po pravilu ovog projekta to nije dokaz interakcije, pa je sprint 004
završen kao YELLOW baš zbog toga. Mandat ID-01 §10 traži Playwright.

ŠTA SE MERI — I ŠTA NAMERNO NE

Ne proverava se nijedna CSS deklaracija, ni prisustvo neke klase u izvoru, ni
tekst funkcije. Meri se **ishod koji advokat vidi**: dva dokumenta koja se
razlikuju SAMO po `status` polju moraju se u DOM-u razlikovati.

Oba testna dokumenta imaju POPUNJEN `pinecone_namespace`. To je srž: pod starim
ponašanjem bi izgledali identično, jer je stara logika gledala baš to polje.
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

_PREDMET_ID = "11111111-1111-1111-1111-111111111111"

# Dva dokumenta, ista u svemu osim u `status`. OBA imaju pinecone_namespace.
_DOKUMENTI = [
    {
        "id": "doc-indeksiran", "predmet_id": _PREDMET_ID,
        "naziv_fajla": "UGOVOR-INDEKSIRAN.pdf", "velicina_kb": 12,
        "redni_broj": 1, "pinecone_namespace": "kancelarija_test",
        "status": "indeksirano", "tip_dokaza": "neklasifikovan",
    },
    {
        "id": "doc-samo-primljen", "predmet_id": _PREDMET_ID,
        "naziv_fajla": "UGOVOR-NIJE-INDEKSIRAN.pdf", "velicina_kb": 12,
        "redni_broj": 2, "pinecone_namespace": "kancelarija_test",
        "status": "sacuvano", "tip_dokaza": "neklasifikovan",
    },
]

_ODGOVOR = {
    "id": _PREDMET_ID, "naziv": "Test predmet", "status": "aktivan",
    "opis": "", "sud": "", "broj_predmeta": "", "oblast": "",
    "beleske": [], "istorija": [], "hronologija": [], "komentari": [],
    "predmet_klijenti": [], "klijenti": [], "dokumenti": _DOKUMENTI,
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


def _renderuj(browser, server):
    """Učitava PRAVU stranicu i poziva PRAVU funkciju renderovanja.

    Ne rekonstruiše se nijedan deo produkcijske logike — `pred_loadDetail` je
    ista funkcija koju zove aplikacija, samo joj je mrežni odgovor presretnut.
    """
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))

    stranica.route("**/api/predmeti/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps(_ODGOVOR)))
    stranica.route("**/rest/v1/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(1200)

    # Minimalna sesija — `pred_loadDetail` šalje Authorization zaglavlje.
    stranica.evaluate(
        "() => { window.currentSession = { access_token: 't', user: { id: 'u1' } }; }"
    )
    stranica.evaluate(
        "async (pid) => { window.activePredmetId = pid;"
        " if (typeof pred_loadDetail === 'function') { await pred_loadDetail(pid); } }",
        _PREDMET_ID,
    )
    stranica.wait_for_timeout(600)
    return stranica, greske


def _kartica(stranica, dok_id):
    return stranica.query_selector(f'[data-dok-id="{dok_id}"]')


def test_id01_ui_razlikuje_indeksiran_od_samo_primljenog(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    Dva dokumenta, identična osim po `status`. Ako se u DOM-u ne razlikuju,
    advokat nema način da sazna da mu dokument nije pretraživ — a upravo to je
    bilo stanje pre sprinta 004.
    """
    stranica, greske = _renderuj(browser, server)
    try:
        assert not greske, f"stranica je pukla: {greske[:2]}"

        k_ind = _kartica(stranica, "doc-indeksiran")
        k_ne = _kartica(stranica, "doc-samo-primljen")
        assert k_ind and k_ne, "obe kartice moraju biti renderovane"

        # Ne poredi se ceo HTML: dve kartice se ionako razlikuju po nazivu
        # fajla i rednom broju, pa bi takvo poredjenje prolazilo i sa vracenom
        # starom logikom -- sto je mutacija i pokazala. Meri se SAM INDIKATOR.
        def _stanje(kartica):
            red = kartica.evaluate("el => el.closest('.vx-tl-item')")
            tacka = kartica.evaluate(
                "el => { const it = el.closest('.vx-tl-item');"
                " const d = it && it.querySelector('.vx-tl-dot');"
                " return d ? d.className : null; }"
            )
            ikona = kartica.evaluate(
                "el => { const i = el.querySelector('[data-lucide]');"
                " return i ? getComputedStyle(i).color : null; }"
            )
            return (tacka, ikona)

        assert _stanje(k_ind) != _stanje(k_ne), (
            "indikator indeksiranosti je IDENTICAN za dokument koji jeste i onaj "
            "koji NIJE u indeksu — status je nevidljiv advokatu"
        )
    finally:
        stranica.close()


def test_id01_neindeksiran_dokument_nosi_vidljivo_upozorenje(browser, server):
    """Razlika nije dovoljna ako je nečitljiva — mora postojati tekst koji
    advokat razume."""
    stranica, _ = _renderuj(browser, server)
    try:
        tekst_ne = _kartica(stranica, "doc-samo-primljen").inner_text().lower()
        tekst_ind = _kartica(stranica, "doc-indeksiran").inner_text().lower()
        assert "nije vektorizovan" in tekst_ne, (
            f"nema upozorenja na neindeksiranom dokumentu: {tekst_ne!r}"
        )
        assert "nije vektorizovan" not in tekst_ind
    finally:
        stranica.close()


def test_id01_prisustvo_namespace_a_NE_znaci_indeksirano(browser, server):
    """Brava nad uzrokom.

    OBA dokumenta imaju popunjen `pinecone_namespace`. Ako bi neko vratio staru
    logiku (`!!dok.pinecone_namespace`), oba bi izgledala indeksirano i ovaj
    test bi pao — što je i dokazano mutacijom.
    """
    stranica, _ = _renderuj(browser, server)
    try:
        assert _DOKUMENTI[1]["pinecone_namespace"], "test je besmislen bez ovoga"
        tekst = _kartica(stranica, "doc-samo-primljen").inner_text().lower()
        assert "klikni za analizu" not in tekst, (
            "dokument bez indeksa poziva korisnika na analizu koju ne može da dobije"
        )
    finally:
        stranica.close()
