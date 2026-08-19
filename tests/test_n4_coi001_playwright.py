# -*- coding: utf-8 -*-
"""
N4-COI-001 §UI — Intake čarobnjak NE SME otvoriti predmet ako provera
sukoba interesa nije potvrđeno izvršena.

Backend popravka bez ovoga ne bi bila dokazana. Pre N4 je frontend radio:

    if (_cfRes.ok) { if (_cfData.conflict_detected) { ...upozorenje... } }
    } catch(_cfe) { /* Conflict check failure is non-blocking */ }

— dakle HTTP greška se preskakala nemo, a pad mreže je bio izričito
„non-blocking". Advokat bi u oba slučaja otvorio predmet bez ijedne provere.

Meri se POSLEDICA, ne argument: da li je POST /api/intake/kreiraj uopšte
poslat. Po invarijanti projekta dokaz interakcije je izvršenje, ne čitanje.
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


def _pokreni_carobnjaka(browser, server, coi_odgovor):
    """Učitava PRAVU stranicu i zove PRAVI `_intakeKreiraj()`.

    `coi_odgovor` opisuje šta ruta /api/intake/conflict-check vraća:
      {"abort": True}                         -> pad mreže (catch grana)
      {"status": 503, "json": {...}}          -> HTTP greška
      {"status": 200, "json": {...}}          -> uspešan HTTP sa telom
    """
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto("%s/index.html" % server, wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)

    brojac = {"kreiraj": 0}

    # REDOSLED JE BITAN: Playwright bira POSLEDNJU registrovanu rutu koja
    # odgovara. Catch-all mora ići PRVI, inače presreće i merenu rutu.
    stranica.route("**/api/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))

    def _kreiraj(r):
        brojac["kreiraj"] += 1
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"success": False, "error": "stop u testu"}))

    stranica.route("**/api/intake/kreiraj", _kreiraj)

    if coi_odgovor.get("abort"):
        stranica.route("**/api/intake/conflict-check", lambda r: r.abort("failed"))
    else:
        stranica.route("**/api/intake/conflict-check", lambda r: r.fulfill(
            status=coi_odgovor["status"], content_type="application/json",
            body=json.dumps(coi_odgovor["json"])))

    stranica.evaluate("""() => {
        window._iKlijentId   = 'k-1';
        window._iKlijentName = 'Marko Marković';
        window._iKlijentFirma = '';
        window._iFiles = [];
        window.currentSession = { access_token: 'test-token' };
        document.getElementById('intake-f-naziv').value = 'Spor 1/2026';
        document.getElementById('intake-f-protivna').value = 'Petar Petrović';
    }""")

    stranica.evaluate("async () => { await _intakeKreiraj(); }")
    stranica.wait_for_timeout(200)

    stanje = stranica.evaluate("""() => {
        const w = document.getElementById('intake-conflict-warning');
        const b = document.getElementById('intake-btn-next');
        return {
            upozorenje_vidljivo: !!w && w.style.display === 'block',
            upozorenje_tekst: w ? w.innerText : '',
            dugme_tekst: b ? b.textContent : '',
            dugme_onemoguceno: b ? b.disabled : null,
        };
    }""")
    stranica.close()
    return brojac["kreiraj"], stanje, greske


# ---------------------------------------------------------------------------
# Prihvatna matrica iz mandata, merena u pregledaču
# ---------------------------------------------------------------------------

def test_ui_nema_konflikta__predmet_se_otvara(browser, server):
    """KONTROLA. Bez nje bi svi testovi ispod prolazili vakuumski —
    blokada koja blokira uvek nije zaštita."""
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
        "status": 200,
        "json": {"conflict_detected": False, "has_blocker": False, "conflicts": [],
                 "status_provere": "NO_CONFLICT", "izvori_neuspeh": [],
                 "preporuka": "Nije detektovan sukob interesa."},
    })
    assert not greske, greske[:2]
    assert kreiraj == 1, "čist nalaz mora dozvoliti otvaranje predmeta"
    assert not stanje["upozorenje_vidljivo"]


def test_ui_blokirajuci_konflikt__predmet_se_NE_otvara(browser, server):
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
        "status": 200,
        "json": {"conflict_detected": True, "has_blocker": True,
                 "conflicts": [{"opis": "Petar Petrović je vaš klijent."}],
                 "status_provere": "CONFLICT_FOUND", "izvori_neuspeh": [],
                 "preporuka": "Postoji BLOKIRAJUCI sukob interesa."},
    })
    assert not greske, greske[:2]
    assert kreiraj == 0, "predmet otvoren uprkos blokirajućem sukobu"
    assert stanje["upozorenje_vidljivo"]
    assert "Petar Petrović" in stanje["upozorenje_tekst"]


def test_ui_CHECK_FAILED_503__predmet_se_NE_otvara(browser, server):
    """NAJVAŽNIJI TEST U FAJLU: provera nije izvršena."""
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
        "status": 503,
        "json": {"detail": {"status_provere": "CHECK_FAILED",
                            "izvori_neuspeh": ["klijenti", "predmeti"],
                            "poruka": "Provera sukoba interesa nije izvršena."}},
    })
    assert not greske, greske[:2]
    assert kreiraj == 0, "predmet otvoren iako provera NIJE izvršena"
    assert stanje["upozorenje_vidljivo"]
    assert "NIJE izvršena" in stanje["upozorenje_tekst"]
    assert "klijenti" in stanje["upozorenje_tekst"], "advokat ne vidi šta nije pročitano"
    assert stanje["dugme_onemoguceno"] is False, "korisnik mora moći da pokuša ponovo"


def test_ui_CHECK_FAILED_sa_HTTP_200__predmet_se_NE_otvara(browser, server):
    """Semantički status mora blokirati i kad je HTTP uspešan —
    `r.ok` sam po sebi nije dovoljan."""
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
        "status": 200,
        "json": {"conflict_detected": False, "has_blocker": False, "conflicts": [],
                 "status_provere": "CHECK_FAILED", "izvori_neuspeh": ["predmet_klijenti"],
                 "preporuka": "Provera sukoba interesa NIJE izvršena."},
    })
    assert not greske, greske[:2]
    assert kreiraj == 0
    assert stanje["upozorenje_vidljivo"]
    assert "predmet_klijenti" in stanje["upozorenje_tekst"]


def test_ui_stari_oblik_bez_statusa__predmet_se_NE_otvara(browser, server):
    """Odgovor pre N4 (bez `status_provere`) mora se tretirati kao neproveren —
    `!undefined` je `true`, tačno ta greška je i bila u pitanju."""
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
        "status": 200,
        "json": {"conflict_detected": False, "has_blocker": False, "conflicts": [],
                 "preporuka": "Nije detektovan sukob interesa. Možete otvoriti predmet."},
    })
    assert not greske, greske[:2]
    assert kreiraj == 0, "stari oblik odgovora je propustio otvaranje predmeta"
    assert stanje["upozorenje_vidljivo"]


def test_ui_nepoznat_status__predmet_se_NE_otvara(browser, server):
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
        "status": 200,
        "json": {"conflict_detected": False, "status_provere": "SVE_JE_OK",
                 "conflicts": [], "has_blocker": False},
    })
    assert not greske, greske[:2]
    assert kreiraj == 0
    assert stanje["upozorenje_vidljivo"]


def test_ui_HTTP_greska_sa_telom_NO_CONFLICT__predmet_se_NE_otvara(browser, server):
    """Mandat traži KONJUNKCIJU: HTTP uspeh I važeći COI status.

    Ovde je jedina odbrana `r.ok` — telo tvrdi NO_CONFLICT, a odgovor je
    non-2xx. Posrednik (proxy, rate-limiter, keš) može vratiti greškovni
    status uz zatečeno telo; telu se tada ne sme verovati.
    """
    for kod in (429, 502, 503):
        kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {
            "status": kod,
            "json": {"conflict_detected": False, "has_blocker": False, "conflicts": [],
                     "status_provere": "NO_CONFLICT", "izvori_neuspeh": [],
                     "preporuka": "Nije detektovan sukob interesa."},
        })
        assert not greske, greske[:2]
        assert kreiraj == 0, "HTTP %d sa telom NO_CONFLICT je propustio predmet" % kod
        assert stanje["upozorenje_vidljivo"], kod


def test_ui_pad_mreze__predmet_se_NE_otvara(browser, server):
    """Ranije izričito označeno kao `non-blocking` — čarobnjak je nastavljao."""
    kreiraj, stanje, greske = _pokreni_carobnjaka(browser, server, {"abort": True})
    assert not greske, greske[:2]
    assert kreiraj == 0, "pad mreže je propustio otvaranje predmeta"
    assert stanje["upozorenje_vidljivo"]
    assert "NIJE izvršena" in stanje["upozorenje_tekst"]
    assert stanje["dugme_tekst"] == "Pokušaj ponovo"
