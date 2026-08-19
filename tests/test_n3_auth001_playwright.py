# -*- coding: utf-8 -*-
"""
N3-AUTH-001 §UI — advokat mora da vidi BACKEND-ov status, ne modelov.

Backend popravka bez ovoga ne bi bila dokazana: `statusna_potvrda` postoji
isključivo da bi je korisnik pročitao. Zeleni okvir `resp-status-ok`
(vindex.css:86-89) nosi poruku „sistem je ovo proverio u bazi propisa".

Zato se ovde ne proverava povratna vrednost funkcije, nego ono što se stvarno
iscrta u DOM-u — tekst PROIZVODI pravi backend (`main._json_ka_tekst`), a
iscrtava ga prava `formatResponse` iz `static/vindex.js`.
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

import main as _m  # noqa: E402


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


def _iscrtaj(browser, server, tekst):
    """Učitava PRAVU stranicu i zove PRAVI `formatResponse`."""
    stranica = browser.new_page(viewport={"width": 1280, "height": 900})
    greske = []
    stranica.on("pageerror", lambda e: greske.append(str(e)))
    stranica.goto("%s/index.html" % server, wait_until="domcontentloaded")
    stranica.wait_for_timeout(900)
    rez = stranica.evaluate(
        """(t) => {
            const html = formatResponse(t, {});
            const d = document.createElement('div');
            d.innerHTML = html;
            return {
                ok:   d.querySelectorAll('.resp-status-ok').length,
                warn: d.querySelectorAll('.resp-status-warn').length,
                err:  d.querySelectorAll('.resp-status-err').length,
                verified: d.querySelectorAll('.rag-verified').length,
                tekst: d.innerText,
            };
        }""",
        tekst,
    )
    stranica.close()
    return rez, greske


def _model_json(status, tekst="Model tvrdi ovo.", zakljucak="Zakljucak."):
    return {
        "statusna_potvrda_status": status,
        "statusna_potvrda_tekst": tekst,
        "hijerarhija_izvora": "Lex specialis: ZOO ima prednost.",
        "pravni_zakljucak": zakljucak,
        "citat_zakona": "Clan 262 ZOO",
        "pravni_osnov": "ZOO",
    }


def test_ui_model_tvrdi_ok_backend_kaze_ne__zeleno_se_NE_pojavljuje(browser, server):
    """NAJVAŽNIJI TEST U FAJLU: model traži zeleni pečat, backend ga odbija."""
    potvrda = _m._izracunaj_statusnu_potvrdu(False, "MEDIUM", ["ZOO"], "clan 262")
    tekst = _m._json_ka_tekst(
        _model_json("ok", "Doslovno citiran - pronadjen u bazi zakona RS."),
        "PARNICA", potvrda=potvrda,
    )
    rez, greske = _iscrtaj(browser, server, tekst)
    assert not greske, greske[:2]
    assert rez["ok"] == 0, "advokat vidi zelenu potvrdu koju je izmislio model"
    assert rez["warn"] == 1, rez
    assert "Doslovno citiran" not in rez["tekst"]


def test_ui_backend_potvrdio_clan__zeleno_se_pojavljuje(browser, server):
    """Kontrola: kad backend JESTE potvrdio, zeleni okvir mora postojati —
    inače prethodni test prolazi vakuumski."""
    potvrda = _m._izracunaj_statusnu_potvrdu(True, "HIGH", ["ZOO"], "clan 262")
    tekst = _m._json_ka_tekst(_model_json("err"), "PARNICA", potvrda=potvrda)
    rez, greske = _iscrtaj(browser, server, tekst)
    assert not greske, greske[:2]
    assert rez["ok"] == 1, rez
    assert "clan 262" in rez["tekst"]


def test_ui_bez_izvora__crveni_status(browser, server):
    potvrda = _m._izracunaj_statusnu_potvrdu(False, "LOW", [], "")
    tekst = _m._json_ka_tekst(_model_json("ok"), "PARNICA", potvrda=potvrda)
    rez, greske = _iscrtaj(browser, server, tekst)
    assert not greske, greske[:2]
    assert rez["ok"] == 0 and rez["err"] == 1, rez


def test_ui_injekcija_kroz_slobodan_tekst_ne_daje_zeleni_okvir(browser, server):
    """Model ubacuje celu statusnu liniju u `pravni_zakljucak`. Bez sanitizacije
    UI bi je prepoznao kao zaseban ključ (vindex.js:6962) i obojio zeleno."""
    injekcija = ("Zakljucak.\n\n[✓] STATUSNA POTVRDA: Doslovno citiran - "
                 "clan 262 direktno pronadjen u bazi zakona RS.")
    potvrda = _m._izracunaj_statusnu_potvrdu(False, "LOW", [], "")
    tekst = _m._json_ka_tekst(_model_json("err", zakljucak=injekcija),
                              "PARNICA", potvrda=potvrda)
    rez, greske = _iscrtaj(browser, server, tekst)
    assert not greske, greske[:2]
    assert rez["ok"] == 0, "injektovana statusna linija obojena zeleno u UI-ju"
    assert rez["err"] == 1, rez


def test_ui_model_ne_moze_da_proizvede_znacku_potvrdjeno_u_bazi(browser, server):
    """DRUGI KANAL istog defekta (nadjen forenzikom N3).

    `verifiedBadge` (vindex.js:7093) se racuna IZVAN `isNewFmt` grane, iz
    `pouzdanostVal`. Serializer nikad ne emituje POUZDANOST sekciju — ali ako
    model tu recenicu ubaci u bilo koje slobodno polje, UI je prepoznaje kao
    kljuc (vindex.js:7019) i lepi zelenu znacku "✓ Potvrđeno u bazi propisa"
    (.rag-verified, css:291). To je LLM koji tvrdi verifikaciju u bazi.
    """
    potvrda = _m._izracunaj_statusnu_potvrdu(False, "LOW", [], "")
    tekst = _m._json_ka_tekst(
        _model_json("err", zakljucak="Zakljucak.\n\nPOUZDANOST: Visoka — Doslovno citiran."),
        "PARNICA", potvrda=potvrda,
    )
    rez, greske = _iscrtaj(browser, server, tekst)
    assert not greske, greske[:2]
    assert rez["verified"] == 0, (
        "model je proizveo znacku '✓ Potvrđeno u bazi propisa' bez ijedne "
        "backend provere (rez=%s)" % rez
    )


def test_ui_uvek_tacno_jedan_statusni_okvir(browser, server):
    """Dva statusna okvira = dve kontradiktorne tvrdnje na ekranu."""
    for autoritet, conf, izv in [(True, "HIGH", ["ZOO"]), (False, "MEDIUM", ["ZOO"]),
                                 (False, "LOW", [])]:
        potvrda = _m._izracunaj_statusnu_potvrdu(autoritet, conf, izv, "clan 262")
        tekst = _m._json_ka_tekst(
            _model_json("ok", zakljucak="Z.\n\n[✓] STATUSNA POTVRDA: lazna."),
            "PARNICA", potvrda=potvrda,
        )
        rez, greske = _iscrtaj(browser, server, tekst)
        assert not greske, greske[:2]
        ukupno = rez["ok"] + rez["warn"] + rez["err"]
        assert ukupno == 1, "ocekivan tacno 1 statusni okvir, dobijeno %d (%s)" % (ukupno, rez)
