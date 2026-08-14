# -*- coding: utf-8 -*-
"""
BETA-P1-DEADLINE-TRUTH §UI — NEUPISAN ROK NE SME IZGLEDATI KAO UPISAN.

Backend popravka bez ove nije popravka. Dve UI putanje pišu isti rok:

  · `lanac_sacuvaj` — na 200 sa `sacuvano_u_predmet: false` nije radila
    **ništa**: bez poruke, bez povratka dugmeta. Dugme je zauvek ostajalo na
    „Čuvam...". Advokat ne razlikuje „čuvam" od „nisam sačuvao".

  · `pred_rokokiGeneriši(true)` — ista situacija je crtala pun spisak rokova
    bez ijedne reči o tome da upis nije prošao. Spisak izgleda isto kao uspeh.

Meri se **ono što advokat vidi**, ne oblik odgovora — po invarijanti ovog
projekta dokaz interakcije je izvršenje, ne čitanje koda.
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

_LANAC = {
    "ok": True,
    "tip_naziv": "Dostava rešenja",
    "datum_pocetka_display": "01.06.2026.",
    "lanac": [
        {"naziv": "Žalba na rešenje", "zakonski_osnov": "čl. 401 ZPP",
         "datum_display": "09.06.2026.", "datum_iso": "2026-06-09",
         "vaznost": "kritican"},
    ],
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


def _stranica(browser, server, *, status, telo):
    st = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    st.on("pageerror", lambda e: greske.append(str(e)))

    st.route(re.compile(r".*/api/rokovi/lanac"), lambda r: r.fulfill(
        status=status, content_type="application/json", body=json.dumps(telo)))
    st.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    st.goto(f"{server}/index.html", wait_until="domcontentloaded")
    st.wait_for_timeout(900)
    st.evaluate("""() => {
        window.currentSession   = { access_token: 't', user: { id: 'u1' } };
        window.activePredmetId  = 'pred-1';
        window.timeline_load    = () => {};
        window.__toasts = [];
        window.showToast = (poruka, tip) => window.__toasts.push(tip + ':' + poruka);
    }""")
    return st, greske


# ═══════════════════════════════════════════════════════════════════════════
# 1. PUTANJA „SAČUVAJ U HRONOLOGIJU" (`lanac_sacuvaj`)
# ═══════════════════════════════════════════════════════════════════════════

def _sacuvaj(browser, server, *, status, telo):
    st, greske = _stranica(browser, server, status=status, telo=telo)
    st.evaluate("""() => {
        const b = document.createElement('button');
        b.id = 'proba-dugme';
        b.textContent = '⛓ Sačuvaj u hronologiju predmeta →';
        document.body.appendChild(b);
    }""")
    st.evaluate("""async () => {
        await lanac_sacuvaj('dostava_resenja', '2026-06-01',
                            document.getElementById('proba-dugme'));
    }""")
    st.wait_for_timeout(300)
    stanje = st.evaluate("""() => {
        const b = document.getElementById('proba-dugme');
        return { toasts: window.__toasts, tekst: b.textContent, onemogucen: b.disabled };
    }""")
    st.close()
    return stanje, greske


def test_ui_uspesan_upis_potvrdjuje_cuvanje(browser, server):
    """Pozitivan slučaj mora i dalje da radi."""
    stanje, greske = _sacuvaj(browser, server, status=200,
                              telo=dict(_LANAC, sacuvano_u_predmet=True))
    assert not greske, greske[:2]
    assert any("success:" in t for t in stanje["toasts"]), stanje["toasts"]
    assert "Sačuvano" in stanje["tekst"]


def test_ui_neupisan_rok_NIKAD_ne_cuti(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    200 uz `sacuvano_u_predmet: false` je ranije završavalo u tišini — dugme
    zaglavljeno na „Čuvam...", nijedna poruka. Advokat je odlazio verujući da
    je rok evidentiran.
    """
    stanje, _ = _sacuvaj(browser, server, status=200,
                         telo=dict(_LANAC, sacuvano_u_predmet=False))
    assert stanje["toasts"], "nijedna poruka — tišina se čita kao uspeh"
    assert any("error:" in t for t in stanje["toasts"]), stanje["toasts"]
    assert any("NISU sačuvani" in t for t in stanje["toasts"]), stanje["toasts"]
    assert "Čuvam" not in stanje["tekst"], "dugme je ostalo zaglavljeno"
    assert stanje["onemogucen"] is False, "advokat ne može ni da pokuša ponovo"
    assert "Sačuvano" not in stanje["tekst"]


def test_ui_http_503_prijavljuje_neuspeh(browser, server):
    """Ovo je odgovor koji backend sada STVARNO vraća kad upis padne."""
    stanje, _ = _sacuvaj(browser, server, status=503, telo={
        "detail": "Rokovi NISU sačuvani uz predmet."})
    assert any("error:" in t for t in stanje["toasts"]), stanje["toasts"]
    assert "Sačuvano" not in stanje["tekst"]
    assert stanje["onemogucen"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. PUTANJA „GENERIŠI I SAČUVAJ" (`pred_rokokiGeneriši`)
# ═══════════════════════════════════════════════════════════════════════════

def _generisi(browser, server, *, status, telo, sacuvaj=True):
    st, greske = _stranica(browser, server, status=status, telo=telo)
    st.evaluate("""() => {
        document.getElementById('pred-rokovi-tip').value   = 'dostava_resenja';
        document.getElementById('pred-rokovi-datum').value = '2026-06-01';
    }""")
    st.evaluate(f"async () => {{ await window['pred_rokokiGeneriši']({str(sacuvaj).lower()}); }}")
    st.wait_for_timeout(300)
    stanje = st.evaluate("""() => {
        const r = document.getElementById('pred-rokovi-rezultat');
        const e = document.getElementById('pred-rokovi-err');
        return { rezultat: r.innerText, vidljiv: r.style.display !== 'none',
                 greska: e.innerText, greska_vidljiva: e.style.display !== 'none' };
    }""")
    st.close()
    return stanje, greske


def test_ui_generisi_uspeh_kaze_sacuvano(browser, server):
    stanje, greske = _generisi(browser, server, status=200,
                               telo=dict(_LANAC, sacuvano_u_predmet=True))
    assert not greske, greske[:2]
    assert "Sačuvano u hronologiji" in stanje["rezultat"]
    assert "Žalba na rešenje" in stanje["rezultat"]


def test_ui_generisi_neupisano_MORA_biti_imenovano(browser, server):
    """Advokat je tražio čuvanje. Spisak rokova bez ijedne reči o upisu
    izgleda potpuno isto kao uspeh — zato se neupisano stanje imenuje."""
    stanje, _ = _generisi(browser, server, status=200,
                          telo=dict(_LANAC, sacuvano_u_predmet=False))
    assert "NIJE sačuvano" in stanje["rezultat"], stanje["rezultat"][:200]
    assert "Sačuvano u hronologiji" not in stanje["rezultat"]


def test_ui_generisi_bez_cuvanja_ne_laze_ni_u_jednom_smeru(browser, server):
    """Kad čuvanje NIJE traženo, odsustvo upisa nije greška — i ne sme se
    prijaviti kao greška. Popravka ne sme da uvede lažnu uzbunu."""
    stanje, _ = _generisi(browser, server, status=200,
                          telo=dict(_LANAC, sacuvano_u_predmet=False),
                          sacuvaj=False)
    assert "NIJE sačuvano" not in stanje["rezultat"]
    assert "Sačuvano u hronologiji" not in stanje["rezultat"]
    assert "Žalba na rešenje" in stanje["rezultat"]


def test_ui_generisi_503_prikazuje_gresku(browser, server):
    stanje, _ = _generisi(browser, server, status=503, telo={
        "detail": "Rokovi NISU sačuvani uz predmet."})
    assert stanje["greska_vidljiva"]
    assert "NISU sačuvani" in stanje["greska"]
    assert "Sačuvano u hronologiji" not in stanje["rezultat"]
