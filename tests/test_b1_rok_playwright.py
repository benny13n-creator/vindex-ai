# -*- coding: utf-8 -*-
"""
B1 §UI — „✓ Sačuvano." SE NE SME POJAVITI ZA ROK KOJI NIJE UPISAN.

Backend popravka bez ove nije popravka. `static/vindex.js::pred_confirmLinks`
je radio:

    if (d && d.success) { ... '✓ Sačuvano.' }

a backend je za odbijen INSERT vraćao tačno `{"success": true,
"rok_dodat": false}` — pa je zelena grana bila jedina dostižna. Advokat je
video potvrdu za rok koji u bazi ne postoji.

Meri se **ono što advokat vidi**, ne oblik odgovora. Zato Playwright: po
invarijanti ovog projekta dokaz interakcije je izvršenje, ne čitanje koda.

NAJVAŽNIJI TEST U FAJLU je `test_b1_ui_success_true_uz_rok_dodat_false_NIJE_zeleno`
— on drži odbranu u dubinu i mora da prolazi čak i kada backend takav odgovor
više ne proizvodi.
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
    # Isti razlog kao u `test_beta_p0_coi_playwright.py`: jednonitni TCPServer
    # serijalizuje sve zahteve i pravi flake na `domcontentloaded`.
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


# Oblik koji `pred_renderConfirmCard` čita da bi uopšte prikazao stavku roka.
_METADATA = {"datumi_kljucni": [
    {"opis": "Rok za žalbu", "datum_iso": "2026-09-01"}]}
# Predlog klijenta — bez njega kartica bez roka uopšte ne bi bila renderovana.
_PREDLOZI = [{"id": "k1", "naziv": "Klijent A", "pouzdanost": 95}]


def _klikni_potvrdi(browser, server, *, status=200, telo=None, sa_rokom=True,
                    prekini_vezu=False):
    """Učitava PRAVU stranicu, renderuje PRAVU karticu, zove PRAVI handler.

    Snimak se uzima ODMAH po završetku handler-a. Razlog je merljiv, ne
    stilski: uspešna grana zove `pred_loadDetail()` BEZ `await`, a ta funkcija
    posle svog `fetch`-a prepisuje radni prostor i kartica nestane. Čitanje
    posle `wait_for_timeout` merilo bi stanje DOM-a posle te kaskade, ne ono
    što je advokat video.
    """
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))

    # REDOSLED JE DEO ISPRAVNOSTI: Playwright bira POSLEDNJU registrovanu
    # rutu koja se poklapa. Kad je catch-all `/api/` bio registrovan posle
    # `confirm-links`, on je presretao i sam poziv koji se meri i vraćao `{}` --
    # pa su svi negativni testovi prolazili iz pogrešnog razloga (lažno zeleno),
    # a pozitivni padali. Zato prvo opšte, pa specifično.
    stranica.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))
    # Sve ostale API pozive (npr. `pred_loadDetail`) drži bezopasnim.
    stranica.route(re.compile(r".*/api/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="{}"))
    if prekini_vezu:
        stranica.route(re.compile(r".*/confirm-links.*"), lambda r: r.abort())
    else:
        stranica.route(re.compile(r".*/confirm-links.*"), lambda r: r.fulfill(
            status=status, content_type="application/json",
            body=json.dumps(telo if telo is not None else {})))

    stranica.goto(f"{server}/index.html", wait_until="domcontentloaded")
    stranica.wait_for_timeout(1000)
    stranica.evaluate("""() => {
        window.currentSession   = { access_token: 't', user: { id: 'u1' } };
        window.activePredmetId  = 'pred-1';
    }""")
    # Prava kartica, pravi markup, pravi checkbox `conf-rok-0`.
    stranica.evaluate(
        "([predlozi, meta]) => {"
        "  const host = document.createElement('div');"
        "  host.innerHTML = pred_renderConfirmCard(predlozi, meta);"
        "  document.body.appendChild(host);"
        "}", [_PREDLOZI, _METADATA if sa_rokom else {}])
    stranica.evaluate(
        "(sa) => window.__rok = sa ? {naziv:'Rok za žalbu', datum_iso:'2026-09-01', vaznost:'važan'} : null",
        sa_rokom)
    el = stranica.evaluate("""async () => {
        await pred_confirmLinks([], window.__rok);
        const e = document.getElementById('pred-confirm-card');
        return e ? {t: e.innerText, h: e.innerHTML} : null;
    }""")
    stranica.close()
    assert el is not None, "kartica `pred-confirm-card` nije u DOM-u"
    return el["t"], el["h"], greske


def test_b1_ui_kartica_uopste_renderuje_rok(browser, server):
    """Kontrola harness-a: bez ovoga ostali testovi ne bi merili ništa."""
    tekst, html, greske = _klikni_potvrdi(browser, server, telo={
        "success": True, "rok_dodat": True, "linked_klijenti": []})
    assert not greske, greske[:2]


def test_b1_ui_uspesan_upis_i_dalje_kaze_sacuvano(browser, server):
    """Pozitivan slučaj mora da preživi popravku."""
    tekst, html, greske = _klikni_potvrdi(browser, server, telo={
        "success": True, "rok_dodat": True, "linked_klijenti": []})
    assert not greske, greske[:2]
    assert "Sačuvano" in tekst
    assert "⚠" not in tekst


def test_b1_ui_success_true_uz_rok_dodat_false_NIJE_zeleno(browser, server):
    """NAJVAŽNIJI TEST U FAJLU — odbrana u dubinu.

    Ovo je DOSLOVNO telo koje je backend vraćao pre popravke. Frontend ga ne
    sme prihvatiti kao uspeh čak i ako se serverski ugovor jednog dana vrati.
    """
    tekst, html, greske = _klikni_potvrdi(browser, server, telo={
        "success": True, "rok_dodat": False, "linked_klijenti": []})
    assert not greske, greske[:2]
    assert "Sačuvano" not in tekst, "rok koji nije upisan prikazan kao sačuvan"
    assert "⚠" in tekst


def test_b1_ui_success_false_nije_zeleno(browser, server):
    """Ugovor posle popravke: neuspeo upis → success=false + poruka."""
    tekst, html, greske = _klikni_potvrdi(browser, server, telo={
        "success": False, "rok_dodat": False, "linked_klijenti": [],
        "rok_greska": "Rok nije sačuvan. Pokušajte ponovo ili ga unesite ručno u kartici Rokovi."})
    assert not greske, greske[:2]
    assert "Sačuvano" not in tekst
    assert "nije sačuvan" in tekst.lower()


def test_b1_ui_http_greska_nije_zeleno(browser, server):
    """`r.ok` se ranije nije proveravao — 500 sa JSON telom je davao zeleno."""
    tekst, html, greske = _klikni_potvrdi(
        browser, server, status=503,
        telo={"success": True, "rok_dodat": True, "detail": "nedostupno"})
    assert not greske, greske[:2]
    assert "Sačuvano" not in tekst
    assert "⚠" in tekst


def test_b1_ui_prazno_telo_nije_zeleno(browser, server):
    tekst, html, greske = _klikni_potvrdi(browser, server, telo={})
    assert not greske, greske[:2]
    assert "Sačuvano" not in tekst


def test_b1_ui_prekinuta_veza_nije_zeleno_i_ne_cuti(browser, server):
    """Ranije je `catch(e) {}` ostavljao karticu nepromenjenom — bez ijedne reči."""
    tekst, html, greske = _klikni_potvrdi(browser, server, prekini_vezu=True)
    assert "Sačuvano" not in tekst
    assert "⚠" in tekst


def test_b1_ui_bez_roka_success_true_i_dalje_kaze_sacuvano(browser, server):
    """Regresiona brava: povezivanje klijenata bez roka ostaje uspeh."""
    tekst, html, greske = _klikni_potvrdi(browser, server, sa_rokom=False, telo={
        "success": True, "rok_dodat": False, "linked_klijenti": ["k1"]})
    assert not greske, greske[:2]
    assert "Sačuvano" in tekst
