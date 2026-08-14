# -*- coding: utf-8 -*-
"""
BETA-P1-PORTAL-READONLY §UI — ONO ŠTO KLIJENT VIDI KAD OTVORI ADVOKATOV LINK.

Meri se izvršenje stranice, ne njen izvor: koja ruta je pozvana, u kom
zaglavlju je otišao token, i šta piše na ekranu kad podataka nema.
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

_ODGOVOR = {
    "predmet": {"naziv": "Marković protiv Beograd d.o.o.", "opis": "Radni spor.",
                "tip": "parnicni", "status": "aktivan", "kreiran": "2026-01-15"},
    "hronologija": [{"dogadjaj": "Podneta tužba", "datum_iso": "2026-01-20",
                     "vaznost": "važan"}],
    "rocista": [{"sud": "Osnovni sud u Novom Sadu", "datum": "2026-09-05",
                 "vreme": "10:00", "sudnica": "12",
                 "broj_predmeta_suda": "P 1/26", "status": "zakazano"}],
    "kriticni_rokovi": [{"dogadjaj": "Rok: žalba na rešenje",
                         "datum_iso": "2026-09-01", "vaznost": "kritičan"}],
    "token_expires_at": "2026-12-31T00:00:00Z",
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


def _otvori(browser, server, *, status=200, telo=None, token="tok-123"):
    st = browser.new_page(viewport={"width": 900, "height": 1200})
    greske = []
    st.on("pageerror", lambda e: greske.append(str(e)))

    pozivi = []

    def _kanonska(r):
        pozivi.append({"url": r.request.url,
                       "zaglavlje": r.request.headers.get("x-portal-token")})
        r.fulfill(status=status, content_type="application/json",
                  body=json.dumps(telo if telo is not None else _ODGOVOR))

    st.route(re.compile(r".*/api/client-portal/view"), _kanonska)
    # Stara, pogresna ruta: ako je stranica ikad pozove, poziv se ovde vidi.
    stara = []
    st.route(re.compile(r".*/api/portal/predmet.*"), lambda r: (
        stara.append(r.request.url),
        r.fulfill(status=404, content_type="application/json",
                  body='{"detail":"Token nije pronađen."}')))

    st.goto(f"{server}/client_portal.html?token={token}", wait_until="domcontentloaded")
    st.wait_for_timeout(700)
    stanje = st.evaluate(
        """() => {
             const t = (id) => { const e = document.getElementById(id);
                                 return e ? e.innerText : null; };
             return {
               naslov:   t('predmet-naziv'),
               tip:      t('predmet-tip'),
               istice:   t('pristup-istice'),
               opis:     t('predmet-opis'),
               rokovi:   t('timeline-list'),
               dokumenti:t('docs-list'),
               greska:   t('error-msg'),
               naslov_greske: t('error-title'),
               sadrzaj_vidljiv: document.getElementById('portal-content').style.display !== 'none',
               greska_vidljiva: document.getElementById('error-state').style.display !== 'none',
               ima_fajl_polje: !!document.querySelector('input[type=file]')
             };
           }""")
    st.close()
    stanje["kanonskih_poziva"] = len(pozivi)
    stanje["zaglavlje"] = pozivi[0]["zaglavlje"] if pozivi else None
    stanje["url"] = pozivi[0]["url"] if pozivi else None
    stanje["starih_poziva"] = len(stara)
    return stanje, greske


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — LINK KOJI ADVOKAT POŠALJE MORA DA SE OTVORI
# ═══════════════════════════════════════════════════════════════════════════

def test_portal_zove_KANONSKU_rutu_a_ne_staru(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    Stranica je zvala `/api/portal/predmet`, koja token traži u
    `privremeni_pristup` — a advokatov link živi u `client_portal_tokens`.
    Svaki klijent je dobijao 404 pre nego što bi ijedan podatak bio pročitan.
    """
    stanje, greske = _otvori(browser, server)
    assert not greske, greske[:2]
    assert stanje["kanonskih_poziva"] == 1, "kanonska ruta nije pozvana"
    assert stanje["starih_poziva"] == 0, "stranica i dalje zove staru rutu"


def test_token_ide_u_zaglavlju_a_ne_u_url(browser, server):
    """Token u URL-u završava u server logovima i istoriji pregledača."""
    stanje, _ = _otvori(browser, server, token="tajni-token-999")
    assert stanje["zaglavlje"] == "tajni-token-999"
    assert "tajni-token-999" not in (stanje["url"] or "")


def test_klijent_vidi_predmet(browser, server):
    stanje, _ = _otvori(browser, server)
    assert stanje["sadrzaj_vidljiv"]
    assert "Marković" in stanje["naslov"]
    assert "parnicni" in stanje["tip"]
    assert "Radni spor" in stanje["opis"]


def test_klijent_vidi_i_rociste_i_rok(browser, server):
    """Dva izvora, jedna lista — po datumu."""
    stanje, _ = _otvori(browser, server)
    assert "Rok: žalba na rešenje" in stanje["rokovi"]
    assert "Osnovni sud u Novom Sadu" in stanje["rokovi"]
    assert stanje["rokovi"].index("Rok: žalba") < \
           stanje["rokovi"].index("Osnovni sud"), "nije poređano po datumu"


# ═══════════════════════════════════════════════════════════════════════════
# 2. PRAZNO I NEUSPEŠNO SE NE MEŠAJU
# ═══════════════════════════════════════════════════════════════════════════

def test_prazna_lista_je_stvarno_prazna_a_ne_nepoznato(browser, server):
    """Odgovor je stigao sa 200 i obe liste su pročitane iz baze — tek tada
    „nema rokova" jeste istina."""
    telo = dict(_ODGOVOR, rocista=[], kriticni_rokovi=[])
    stanje, _ = _otvori(browser, server, telo=telo)
    assert "Nema zakazanih rokova" in stanje["rokovi"]
    assert stanje["sadrzaj_vidljiv"]


def test_opozvan_token_ne_prikazuje_nikakav_sadrzaj(browser, server):
    stanje, _ = _otvori(browser, server, status=401,
                        telo={"detail": "Token je opozvan od strane advokata."})
    assert stanje["greska_vidljiva"]
    assert stanje["sadrzaj_vidljiv"] is False
    assert "opozvan" in stanje["greska"]
    assert "vise ne vazi" in (stanje["naslov_greske"] or "").lower()


def test_bez_tokena_u_linku_nema_ni_poziva(browser, server):
    stanje, _ = _otvori(browser, server, token="")
    assert stanje["kanonskih_poziva"] == 0
    assert stanje["greska_vidljiva"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. READ-ONLY
# ═══════════════════════════════════════════════════════════════════════════

def test_portal_nema_slanje_fajlova(browser, server):
    stanje, _ = _otvori(browser, server)
    assert stanje["ima_fajl_polje"] is False, (
        "portal nudi slanje dokumenta, a ta putanja ne šifruje fajl"
    )


def test_odsustvo_dokumenata_se_ne_predstavlja_kao_prazan_predmet(browser, server):
    """„Nema dostupnih dokumenata" klijentu zvuči kao da u predmetu nema
    dokumenata. Portal ih naprosto ne deli — i to mora reći."""
    stanje, _ = _otvori(browser, server)
    assert "ne dele kroz portal" in stanje["dokumenti"]
    assert "Nema dostupnih dokumenata" not in stanje["dokumenti"]
