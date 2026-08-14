# -*- coding: utf-8 -*-
"""
BETA-P1-FEEDBACK-TRUTH §UI — TRI ISHODA PRIJAVE, TRI RAZLIČITE PORUKE.

`sendFeedback` piše u dva nezavisna skladišta:

    reported_errors   tekst pitanja + tekst odgovora   (primarni)
    /api/feedback     samo heš pitanja + tip           (rezervni)

Pad primarnog kanala je ranije radio `return` **pre** rezervnog poziva — dakle
jedini preostali trag se nije ni pokušavao tačno onda kad je bio jedini koji
može da uspe. Uz to je advokatu prikazivan sirov engleski PostgREST tekst
(*„Could not find the table 'public.reported_errors' in the schema cache"*).

Ovi testovi zaključavaju tri stanja i drže ih razdvojenima:

    primarni uspeo              →  ✓ Prijavljeno — hvala
    primarni pao, rezervni ok   →  ⚠ Prijavljeno bez sadržaja   (ne ✓)
    oba pala                    →  ⚠ Nije poslato, dugme se vraća
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


def _prijavi(browser, server, *, primarni_ok, rezervni_status):
    st = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    st.on("pageerror", lambda e: greske.append(str(e)))

    pozivi = []
    st.route(re.compile(r".*/api/feedback"), lambda r: (
        pozivi.append(r.request.post_data),
        r.fulfill(status=rezervni_status, content_type="application/json",
                  body=json.dumps({"status": "ok"} if rezervni_status < 400
                                  else {"greska": "Prijava NIJE zabeležena."}))))
    st.route(re.compile(r".*/rest/v1/.*"), lambda r: r.fulfill(
        status=200, content_type="application/json", body="[]"))

    st.goto(f"{server}/index.html", wait_until="domcontentloaded")
    st.wait_for_timeout(900)
    st.evaluate(
        """(primarniOk) => {
             window.currentSession = { access_token: 't' };
             window.currentUser    = { id: 'u1', email: 't@t.rs' };
             window.__toasts = [];
             window.showToast = (p, t) => window.__toasts.push((t||'') + ':' + p);
             window.__upisi = [];
             // Dvojnik Supabase klijenta: `insert` vraca gresku u OBJEKTU,
             // tacno kao pravi SDK (ne baca izuzetak).
             window._waitSupa = () => Promise.resolve({
               from: (t) => ({ insert: (row) => {
                 window.__upisi.push({ t: t, row: row });
                 return Promise.resolve(primarniOk ? {} : {
                   error: { message: "Could not find the table "
                                   + "'public.reported_errors' in the schema cache" }
                 });
               }})
             });
             const d = document.createElement('div');
             d.innerHTML = _feedbackBar('Uslovi za naknadu?', 'Član 154 ZOO.');
             document.body.appendChild(d);
           }""", primarni_ok)
    st.evaluate("() => document.querySelector('#fb-btn').click()")
    st.wait_for_timeout(700)
    stanje = st.evaluate(
        """() => { const b = document.querySelector('#fb-btn');
                   return { tekst: b.textContent, onemogucen: b.disabled,
                            toasts: window.__toasts, upisa: window.__upisi.length }; }""")
    st.close()
    stanje["rezervnih_poziva"] = len(pozivi)
    return stanje, greske


# ═══════════════════════════════════════════════════════════════════════════
# 1. PRIMARNI KANAL RADI
# ═══════════════════════════════════════════════════════════════════════════

def test_ui_primarni_uspeh_daje_potvrdu(browser, server):
    stanje, greske = _prijavi(browser, server, primarni_ok=True,
                              rezervni_status=200)
    assert not greske, greske[:2]
    assert "Prijavljeno" in stanje["tekst"]
    assert "bez sadržaja" not in stanje["tekst"]
    assert stanje["onemogucen"]
    assert stanje["upisa"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. PRIMARNI PAO — SRŽ POPRAVKE
# ═══════════════════════════════════════════════════════════════════════════

def test_ui_pad_primarnog_IPAK_salje_rezervni(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    Ranije je `return` na grešci primarnog kanala preskakao rezervni poziv —
    dakle prijava se gubila na oba kanala umesto na jednom. Meri se da je
    rezervni poziv STVARNO otišao na mrežu, ne da je funkcija pozvana.
    """
    stanje, _ = _prijavi(browser, server, primarni_ok=False,
                         rezervni_status=200)
    assert stanje["rezervnih_poziva"] == 1, (
        "rezervni kanal nije pozvan iako je primarni pao"
    )


def test_ui_samo_rezervni_NIJE_puna_potvrda(browser, server):
    """Rezervni kanal ne čuva tekst odgovora. Advokat mora znati da je prijava
    stigla BEZ sadržaja — inače misli da smo videli šta je bilo pogrešno."""
    stanje, _ = _prijavi(browser, server, primarni_ok=False,
                         rezervni_status=200)
    assert "Bez sadržaja" in stanje["tekst"], stanje["tekst"]
    assert "✓" not in stanje["tekst"], "delimičan ishod prikazan kao pun uspeh"
    assert "Prijavljeno" not in stanje["tekst"], (
        "delimičan ishod nosi istu reč kao pun uspeh — to je razlika koju "
        "advokat ne može da vidi"
    )
    assert stanje["onemogucen"] is False, (
        "sadržaj nije sačuvan, a advokat ne može da pokuša ponovo"
    )
    assert any("bitan" in t or "BEZ teksta" in t for t in stanje["toasts"]), \
        stanje["toasts"]


def test_ui_oba_kanala_pala_je_jasan_neuspeh(browser, server):
    stanje, _ = _prijavi(browser, server, primarni_ok=False,
                         rezervni_status=503)
    assert "Nije poslato" in stanje["tekst"], stanje["tekst"]
    assert "Prijavljeno" not in stanje["tekst"]
    assert stanje["onemogucen"] is False, "advokat ne može ni da pokuša ponovo"
    assert any("NIJE zabeležena" in t for t in stanje["toasts"]), stanje["toasts"]


def test_ui_sirov_engleski_iz_baze_se_NE_prikazuje_advokatu(browser, server):
    """Poruka PostgREST-a je engleska i govori o šemi baze. Ona pripada
    konzoli, ne advokatu koji je hteo da prijavi netačan član zakona."""
    stanje, _ = _prijavi(browser, server, primarni_ok=False,
                         rezervni_status=503)
    spojeno = " ".join(stanje["toasts"]) + " " + stanje["tekst"]
    for engleski in ("schema cache", "Could not find", "relation", "PGRST"):
        assert engleski not in spojeno, f"advokatu je prikazano: {spojeno!r}"
