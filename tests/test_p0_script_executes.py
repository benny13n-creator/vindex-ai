# -*- coding: utf-8 -*-
"""
P0-0 — `static/vindex.js` MORA DA SE IZVRŠI DO KRAJA.

ŠTA SE DESILO

Program Omega, Sprint 005 (2026-08-06) uklonio je `function kalendarLoad()` kao
zasenčen mrtav kod. Definicija je nestala, ali je ostao red koji je taj
identifikator čitao:

    var _kalendarLoad_orig = kalendarLoad;   // vindex.js:14212

To je bacalo `ReferenceError: kalendarLoad is not defined` na najvišem nivou
skripte — a takva greška zaustavlja izvršavanje CELOG ostatka fajla. Od 23.681
reda, poslednjih 9.469 nikad se nije izvršilo.

ZAŠTO GA NIJEDNA POSTOJEĆA PROVERA NIJE VIDELA

Deklaracije funkcija se podižu (hoisting), pa je posle pada svaka funkcija i
dalje POSTOJALA. Statičke provere — „da li `onclick` pokazuje na postojeće ime"
— zato su prijavljivale nula problema. Kvar postoji isključivo u izvršavanju:
nestale su `var` dodele i registracije događaja posle tog reda.

Zato ovaj fajl ne čita nijedan izvor. Učitava stranicu u pravom pregledaču i
sluša `pageerror`. Ništa se ne stubuje — greška je bila potpuno nezavisna od
mreže, pa bi svaki stub samo zamaglio merenje.
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

# Globali koji se dodeljuju POSLE mesta pada. Dok je greška postojala, svi su
# bili `undefined`. Namerno su izabrani iz raznih delova repa fajla, da provera
# ne zavisi od jednog reda.
_GLOBALI_POSLE_PADA = {
    "kalendarLoad": "function",        # 14213 — sam Kalendar
    "_iStep": "number",                # 20648 — čarobnjak Novi predmet
    "_INTAKE_STEP_LABELS": "object",   # 20659 — nazivi koraka čarobnjaka
    "_genomeDnaCache": "object",       # upload dokumenta
}


@pytest.fixture(scope="module")
def stranica():
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
    base = f"http://127.0.0.1:{port}"

    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        greske = []
        page.on("pageerror", lambda e: greske.append(str(e).split("\n")[0]))
        # Spoljni CDN-ovi se prekidaju (nema izlaza na mrežu), sve ostalo prolazi.
        page.route(
            "**/*",
            lambda r: r.continue_() if r.request.url.startswith(base) else r.abort(),
        )
        page.goto(f"{base}/index.html", wait_until="load")
        page.wait_for_timeout(1500)
        try:
            yield page, greske
        finally:
            b.close()
            srv.shutdown()
            srv.server_close()


def test_ucitavanje_ne_baca_nijednu_js_gresku(stranica):
    """NAJVAŽNIJI TEST U FAJLU.

    Jedna neuhvaćena greška na najvišem nivou ćuti u interfejsu, a pojede sve
    što je iza nje u fajlu.
    """
    page, greske = stranica
    assert not greske, (
        "učitavanje aplikacije baca JavaScript greške — sve što u "
        "`static/vindex.js` sledi iza mesta pada se ne izvršava:\n  "
        + "\n  ".join(greske)
    )


@pytest.mark.parametrize("ime, tip", sorted(_GLOBALI_POSLE_PADA.items()))
def test_globali_iz_donjeg_dela_fajla_su_inicijalizovani(stranica, ime, tip):
    """Pozitivna potvrda da je izvršavanje stiglo do kraja.

    Provera greške iznad kaže da nije puklo; ova kaže da je i STIGLO dokle
    treba. Bez nje bi test prošao i da neko ceo donji deo fajla zakomentariše.
    """
    page, _ = stranica
    dobijeno = page.evaluate(f"() => typeof {ime}")
    assert dobijeno == tip, (
        f"`{ime}` je `{dobijeno}`, očekivano `{tip}` — izvršavanje "
        f"`static/vindex.js` nije stiglo do njegove dodele"
    )


def test_svaka_procitana_globalna_funkcija_je_i_deklarisana():
    """Strukturna zaštita protiv tačno ovog obrasca.

    Kvar je nastao tako što je uklonjena definicija funkcije, a red koji je
    ČITA je ostao. Ovde se traži svaka `var X = imeFunkcije;` dodela na najvišem
    nivou i proverava da desna strana zaista postoji u fajlu.

    Statička provera je ovde dovoljna i namerna: ovaj obrazac (`snimi staru
    verziju pa je zameni`) je jedini način na koji je greška mogla nastati, i
    jeftino je zaključati ga bez pokretanja pregledača.
    """
    import re
    js = open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()

    # `var _x_orig = imeNecega;` na početku reda — bez zagrada, bez `function`.
    obrazac = re.compile(r"^var\s+\w+\s*=\s*([A-Za-z_$][\w$]*)\s*;\s*$", re.M)
    nedostaju = []
    for m in obrazac.finditer(js):
        ime = m.group(1)
        # Literali i ugrađeni objekti nisu reference na kod ovog fajla.
        if ime in {
            "true", "false", "null", "undefined", "NaN", "Infinity",
            "this", "window", "document", "navigator", "location",
        }:
            continue
        deklarisano = re.search(
            rf"(?:^|\s)(?:function\s+{re.escape(ime)}\s*\(|"
            rf"var\s+{re.escape(ime)}\s*=|"
            rf"window\.{re.escape(ime)}\s*=)",
            js,
        )
        if not deklarisano:
            red = js[: m.start()].count("\n") + 1
            nedostaju.append(f"vindex.js:{red} čita `{ime}`, a `{ime}` nije nigde deklarisan")

    assert not nedostaju, (
        "top-level dodela čita nedeklarisan identifikator — to baca "
        "`ReferenceError` i ubija ostatak fajla:\n  " + "\n  ".join(nedostaju)
    )
