# -*- coding: utf-8 -*-
"""
TASK 2 — OPTIMISTIC UI: „SAČUVANO" SME DA SE KAŽE TEK POSLE SERVERSKE POTVRDE.

Pet nalaza iz `FALSE_SUCCESS_INVENTORY.md`, jedan obrazac:

    IDLE → (klik) → prikaži uspeh → server možda uspe

Ispravan model:

    IDLE → SUBMITTING → CONFIRMED
                     ↘ FAILED   (stanje se VRAĆA, unos se NE gubi)

| nalaz | površina | šta se gubilo |
|---|---|---|
| FS-P1-27 | dokazna stavka | tekst iz `prompt()` — nepovratan |
| FS-P1-28 | komentar na predmet | otkucan tekst |
| FS-P1-29 | tajmer naplativih sati | izmereno vreme (novac) |
| FS-P1-30 | prihvatanje Uslova korišćenja | pravno obavezujući čin |
| FS-P1-31 | GDPR saglasnost (benchmarking) | saglasnost za obradu podataka |

Za svaki se meri PONAŠANJE u pregledaču pri: uspehu, HTTP 500 i padu mreže.
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


def _stranica(browser, server, ruta, ishod):
    """`ishod`: 'ok' | '500' | 'mreza'."""
    st = browser.new_page(viewport={"width": 1280, "height": 900})
    st.on("pageerror", lambda e: st.__dict__.setdefault("greske", []).append(str(e)))

    def _rukuj(r):
        if ishod == "mreza":
            r.abort()
        elif ishod == "500":
            r.fulfill(status=500, content_type="application/json",
                      body=json.dumps({"detail": "Serverska greška."}))
        else:
            r.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True}))

    st.route(re.compile(ruta), _rukuj)
    st.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    st.goto(f"{server}/index.html", wait_until="domcontentloaded")
    st.wait_for_timeout(900)
    st.evaluate("""() => {
        window.currentSession = { access_token: 't', user: { id: 'u1' } };
        window.currentUser    = { id: 'u1', email: 't@t.rs' };
        window.activePredmetId = 'p1';
        window._aktPredmetId   = 'p1';
        window.__toasts = [];
        window.showToast = (p, t) => window.__toasts.push((t || '') + ':' + p);
        window.evidence_load   = () => {};
        window.ucitajKomentare = () => {};
    }""")
    return st


# ═══════════════════════════════════════════════════════════════════════════
# FS-P1-30 — PRIHVATANJE USLOVA KORIŠĆENJA
# ═══════════════════════════════════════════════════════════════════════════

def _tos(browser, server, ishod):
    st = _stranica(browser, server, r".*/api/tos/accept", ishod)
    st.evaluate("""() => {
        document.getElementById('tos-overlay').style.display = 'flex';
        document.getElementById('tos-confirm-chk').checked = true;
    }""")
    st.evaluate("async () => { await tosAccept(); }")
    st.wait_for_timeout(400)
    stanje = st.evaluate("""() => ({
        overlay: document.getElementById('tos-overlay').style.display,
        greska:  (document.getElementById('tos-greska')||{}).innerText || '',
        dugme:   document.getElementById('tos-accept-btn').dataset.stanje || '',
        onemogucen: document.getElementById('tos-accept-btn').disabled,
        toasts: window.__toasts,
    })""")
    st.close()
    return stanje


def test_tos_uspeh_zatvara_overlay(browser, server):
    s = _tos(browser, server, "ok")
    assert s["overlay"] == "none"
    assert s["dugme"] == "CONFIRMED"


def test_tos_500_NE_zatvara_overlay(browser, server):
    """NAJVAŽNIJI TEST ZA FS-P1-30. Prihvatanje Uslova je pravno obavezujući
    čin — ne sme se smatrati datim ako server nema zapis."""
    s = _tos(browser, server, "500")
    assert s["overlay"] != "none", "overlay zatvoren iako server nije potvrdio"
    assert s["dugme"] == "FAILED"
    assert s["onemogucen"] is False, "korisnik ne može ni da pokuša ponovo"
    assert "NIJE zabeleženo" in s["greska"]


def test_tos_pad_mreze_NE_zatvara_overlay(browser, server):
    s = _tos(browser, server, "mreza")
    assert s["overlay"] != "none"
    assert s["dugme"] == "FAILED"


# ═══════════════════════════════════════════════════════════════════════════
# FS-P1-28 — KOMENTAR NA PREDMET
# ═══════════════════════════════════════════════════════════════════════════

def _komentar(browser, server, ishod, tekst="Klijent je doneo ugovor 12.08."):
    st = _stranica(browser, server, r".*/predmeti/.*/komentari", ishod)
    st.evaluate("""(t) => {
        if (!document.getElementById('pred-kom-input')) {
            const i = document.createElement('input');
            i.id = 'pred-kom-input';
            document.body.appendChild(i);
        }
        document.getElementById('pred-kom-input').value = t;
    }""", tekst)
    st.evaluate("async () => { await dodajKomentar(); }")
    st.wait_for_timeout(400)
    stanje = st.evaluate("""() => {
        const i = document.getElementById('pred-kom-input');
        return { vrednost: i.value, stanje: i.dataset.stanje || '',
                 onemogucen: i.disabled, toasts: window.__toasts };
    }""")
    st.close()
    return stanje


def test_komentar_uspeh_cisti_polje(browser, server):
    s = _komentar(browser, server, "ok")
    assert s["vrednost"] == ""
    assert s["stanje"] == "CONFIRMED"


def test_komentar_500_CUVA_otkucan_tekst(browser, server):
    """NAJVAŽNIJI TEST ZA FS-P1-28."""
    tekst = "Klijent je doneo ugovor 12.08."
    s = _komentar(browser, server, "500", tekst)
    assert s["vrednost"] == tekst, "otkucan komentar je izgubljen"
    assert s["stanje"] == "FAILED"
    assert s["onemogucen"] is False
    assert any("NIJE sačuvan" in t for t in s["toasts"]), s["toasts"]


def test_komentar_pad_mreze_CUVA_tekst(browser, server):
    tekst = "Rok za žalbu ističe u petak."
    s = _komentar(browser, server, "mreza", tekst)
    assert s["vrednost"] == tekst
    assert s["stanje"] == "FAILED"


# ═══════════════════════════════════════════════════════════════════════════
# FS-P1-31 — GDPR SAGLASNOST ZA BENCHMARKING
# ═══════════════════════════════════════════════════════════════════════════

def _optin(browser, server, ishod, trazeno=True):
    st = _stranica(browser, server, r".*/api/benchmarking/opt-in", ishod)
    st.evaluate("""(trazeno) => {
        const c = document.createElement('input');
        c.type = 'checkbox'; c.id = 'proba-optin';
        c.checked = trazeno;          // pregledac je vec prebacio stanje
        document.body.appendChild(c);
    }""", trazeno)
    st.evaluate("async () => { await profitabilnost_toggleOptIn("
                "document.getElementById('proba-optin')); }")
    st.wait_for_timeout(400)
    stanje = st.evaluate("""() => {
        const c = document.getElementById('proba-optin');
        return { cekiran: c.checked, onemogucen: c.disabled,
                 toasts: window.__toasts };
    }""")
    st.close()
    return stanje


def test_optin_uspeh_zadrzava_novo_stanje(browser, server):
    s = _optin(browser, server, "ok", trazeno=True)
    assert s["cekiran"] is True
    assert s["onemogucen"] is False


def test_optin_500_VRACA_checkbox_na_stanje_servera(browser, server):
    """NAJVAŽNIJI TEST ZA FS-P1-31. Ovo je GDPR saglasnost — UI ne sme
    pokazivati jedno dok server drži drugo."""
    s = _optin(browser, server, "500", trazeno=True)
    assert s["cekiran"] is False, "UI tvrdi saglasnost koju server nema"
    assert s["onemogucen"] is False
    assert any("NIJE promenjena" in t for t in s["toasts"]), s["toasts"]


def test_optin_pad_mreze_takodje_vraca(browser, server):
    s = _optin(browser, server, "mreza", trazeno=False)
    assert s["cekiran"] is True, "povlačenje saglasnosti prikazano bez servera"


# ═══════════════════════════════════════════════════════════════════════════
# FS-P1-27 — DOKAZNA STAVKA (tekst iz `prompt()` je nepovratan)
# ═══════════════════════════════════════════════════════════════════════════

def _dokaz(browser, server, ishod, tvrdnja="Svedok je video potpisivanje."):
    st = _stranica(browser, server, r".*/api/evidence/predmeti/.*/dokaz", ishod)
    st.evaluate("(t) => { window.prompt = () => t; }", tvrdnja)
    st.evaluate("() => { evidence_addDokaz(); }")
    st.wait_for_timeout(500)
    toasts = st.evaluate("() => window.__toasts")
    st.close()
    return toasts


def test_dokaz_uspeh_potvrdjuje(browser, server):
    t = _dokaz(browser, server, "ok")
    assert any("Dokaz dodat" in x for x in t), t


def test_dokaz_500_NE_tvrdi_da_je_dodat_i_vraca_tekst(browser, server):
    """NAJVAŽNIJI TEST ZA FS-P1-27. Tekst dolazi iz `prompt()` i nigde nije
    sačuvan — zato se pri neuspehu vraća korisniku da može da ga kopira."""
    tvrdnja = "Svedok je video potpisivanje."
    t = _dokaz(browser, server, "500", tvrdnja)
    assert not any("Dokaz dodat" in x for x in t), t
    assert any("NIJE sačuvan" in x for x in t), t
    assert any(tvrdnja in x for x in t), "izgubljen tekst nije vraćen korisniku"


def test_dokaz_pad_mreze_NE_tvrdi_uspeh(browser, server):
    t = _dokaz(browser, server, "mreza")
    assert not any("Dokaz dodat" in x for x in t), t


# ═══════════════════════════════════════════════════════════════════════════
# FS-P1-29 — TAJMER NAPLATIVIH SATI (novac)
# ═══════════════════════════════════════════════════════════════════════════

def _tajmer(browser, server, ishod):
    st = _stranica(browser, server, r".*/billing/entries", ishod)
    st.evaluate("""() => {
        // Tajmer koji tece 30 minuta.
        localStorage.setItem('vx_timer_p1',
            JSON.stringify({ start: Date.now() - 30 * 60 * 1000 }));
        for (const id of ['pred-timer-start-btn', 'pred-timer-stop-btn',
                          'pred-timer-display']) {
            if (!document.getElementById(id)) {
                const e = document.createElement('div');
                e.id = id;
                document.body.appendChild(e);
            }
        }
    }""")
    st.evaluate("async () => { await timer_stop(); }")
    st.wait_for_timeout(400)
    stanje = st.evaluate("""() => ({
        merenje: localStorage.getItem('vx_timer_p1'),
        toasts: window.__toasts,
    })""")
    st.close()
    return stanje


def test_tajmer_uspeh_brise_merenje(browser, server):
    s = _tajmer(browser, server, "ok")
    assert s["merenje"] is None, "merenje ostalo iako je unos sačuvan"
    assert any("dodata u naplatu" in t for t in s["toasts"]), s["toasts"]


def test_tajmer_500_ZADRZAVA_izmereno_vreme(browser, server):
    """NAJVAŽNIJI TEST ZA FS-P1-29.

    Ranije se `localStorage.removeItem` izvršavao PRE POST-a — kad upis padne,
    izmereni naplativi sati su nepovratno nestajali. Toast jeste bio iskren,
    ali novac više nije postojao ni u pregledaču.
    """
    s = _tajmer(browser, server, "500")
    assert s["merenje"] is not None, "izmereno naplativo vreme je izgubljeno"
    assert any("zadržano" in t for t in s["toasts"]), s["toasts"]


def test_tajmer_pad_mreze_ZADRZAVA_vreme(browser, server):
    s = _tajmer(browser, server, "mreza")
    assert s["merenje"] is not None
    assert any("zadržano" in t for t in s["toasts"]), s["toasts"]
