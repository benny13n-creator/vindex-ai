# -*- coding: utf-8 -*-
"""
FAZA 2.1 — UNRESOLVED RESOLUTION (stavke 2, 3, 4).

Stavka 1 (23 landing reference) je NAMERNO izvan ovog fajla — vodi se u
`tests/test_deferred_defects.py` kao odložena, sa sopstvenom bravom.

Sve tri stavke su se razrešile na **kanonske ulaze koji već postoje u kodu**.
Nijedan nije izabran procenom:

    stavka 2  `_intakeKreiraj` je jedini tok koji radi pun lanac
              conflict-check → kreiraj (vezuje klijenta) → pipeline
    stavka 3  `_AIWS_MODES = { …, n:'nacrti', … }` + `_selectPodnesakOption`
    stavka 4  isti `_AIWS_MODES`, preko `openAITool()` koji čuva PRO kapiju

Testovi čitaju te izvore, pa veza ostaje živa: ako se mapa promeni a poziv ne,
test pada.
"""
import http.server
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


def _js():
    return open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()


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


@pytest.fixture
def page(browser, server):
    p = browser.new_page(viewport={"width": 1440, "height": 900})
    p.greske = []
    p.on("pageerror", lambda e: p.greske.append(str(e).split("\n")[0]))
    p.route(
        "**/*",
        lambda r: r.continue_() if r.request.url.startswith(server) else r.abort(),
    )
    p.add_init_script(
        """
        window.__pozvano = [];
        window.fetch = function(u, o) {
          window.__pozvano.push(String(u));
          return Promise.resolve({ ok: true, status: 200,
            json: () => Promise.resolve({}), text: () => Promise.resolve('{}'),
            headers: { get: () => 'application/json' } });
        };
        """
    )
    p.goto(f"{server}/index.html", wait_until="load")
    p.wait_for_function("typeof openAITool === 'function'", timeout=20000)
    p.evaluate(
        """() => {
          window.currentSession = { access_token: 't' };
          window.currentUser    = { id: 'u1', email: 't@t.rs' };
          window.currentUserIsPro = true;          // `n` i `t` su PRO
          updateAuthUI();
          window._poslednja_analiza_tekst =
            'ANALIZA: tužilac traži naknadu štete po članu 154 ZOO.';
        }"""
    )
    p.wait_for_timeout(300)
    try:
        yield p
    finally:
        p.close()


# ═══════════════════════════════════════════════════════════════════════════
# STAVKA 2 — „Sačuvaj u predmet" vodi u KANONSKI tok kreiranja
# ═══════════════════════════════════════════════════════════════════════════

def test_s2_otvara_intake_carobnjak(page):
    """Pre popravke: prelazak na Predmete i — ništa.

    `#pred-novi-btn` ne postoji, a oba rezervna selektora pogađaju 0 elemenata.
    """
    page.evaluate("() => analizaSacuvajUPredmet()")
    page.wait_for_timeout(500)
    otvoren = page.evaluate(
        "() => document.getElementById('intake-overlay').classList.contains('open')"
    )
    assert otvoren, "„Sačuvaj u predmet" f"" " nije otvorio Intake čarobnjaka"


def test_s2_prenosi_analizu_u_opis(page):
    page.evaluate("() => analizaSacuvajUPredmet()")
    page.wait_for_timeout(500)
    opis = page.evaluate("() => document.getElementById('intake-opis').value")
    assert "154 ZOO" in opis, (
        f"analiza nije preneta u opis čarobnjaka; opis je {opis[:80]!r}"
    )


def test_s2_uvek_otvara_svez_carobnjak(page):
    """Granični uslov, ispravljen posle merenja.

    Prva verzija je tvrdila da se korisnikov ručni unos ne sme pregaziti. To je
    pogrešna premisa: `intakeOtvori()` po svom ugovoru RESETUJE sva polja — on
    otvara NOV predmet. Zaštita `if (opis.value.trim()) return;` zato nikad ne
    bi opalila, i uklonjena je iz koda kao mrtva.

    Ono što se stvarno mora garantovati je da posle otvaranja iz analize u opisu
    stoji analiza, a ne zaostatak prethodne sesije čarobnjaka.
    """
    page.evaluate("() => intakeOtvori()")
    page.wait_for_timeout(300)
    page.evaluate(
        "() => { document.getElementById('intake-opis').value = 'ZAOSTATAK'; }"
    )
    page.evaluate("() => analizaSacuvajUPredmet()")
    page.wait_for_timeout(500)
    opis = page.evaluate("() => document.getElementById('intake-opis').value")
    assert "ZAOSTATAK" not in opis, "čarobnjak nije resetovan pri otvaranju"
    assert "154 ZOO" in opis, f"analiza nije preneta; opis je {opis[:80]!r}"


def test_s2_ne_kreira_predmet_direktno(page):
    """SRŽ ODLUKE.

    Uklonjeni `pred_kreiraj` je slao go `POST /api/predmeti` bez klijenta, roka
    i dokumenata. Ovaj tok ne sme da napravi drugi takav put — samo otvara
    čarobnjaka i pušta korisnika da potvrdi.
    """
    page.evaluate("() => { window.__pozvano = []; }")
    page.evaluate("() => analizaSacuvajUPredmet()")
    page.wait_for_timeout(600)
    pozivi = page.evaluate("() => window.__pozvano")
    kreiranja = [u for u in pozivi if re.search(r"/api/predmeti/?$", u)]
    assert not kreiranja, (
        f"tok je sam kreirao predmet, zaobilazeći čarobnjaka: {kreiranja}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# STAVKA 4 — nacrt i strategija idu na kanonski AIWS mod
# ═══════════════════════════════════════════════════════════════════════════

def _aiws_mod(page):
    return page.evaluate("() => window._aiwsMode")


def test_s4_nacrt_otvara_mod_iz_aiws_mape(page):
    """Odredište nije birano — `_AIWS_MODES` ga deklariše."""
    js = _js()
    m = re.search(r"_AIWS_MODES\s*=\s*\{([^}]*)\}", js)
    assert m, "`_AIWS_MODES` je nestala — kanonska mapa modova više ne postoji"
    ocekivano = re.search(r"n:\s*'([a-z]+)'", m.group(1)).group(1)

    page.evaluate("() => analizaGenerisiNacrt()")
    page.wait_for_timeout(500)
    assert _aiws_mod(page) == ocekivano, (
        f"`_AIWS_MODES` kaže n → {ocekivano!r}, a otvoren je {_aiws_mod(page)!r}"
    )


def test_s4_nacrt_prenosi_analizu(page):
    page.evaluate("() => analizaGenerisiNacrt()")
    page.wait_for_timeout(500)
    opis = page.evaluate("() => document.getElementById('podnesak-opis').value")
    assert "154 ZOO" in opis, f"analiza nije preneta u opis podneska: {opis[:80]!r}"


def test_s4_strategija_otvara_svoj_mod_i_prenosi_tekst(page):
    js = _js()
    ocekivano = re.search(
        r"t:\s*'([a-z]+)'", re.search(r"_AIWS_MODES\s*=\s*\{([^}]*)\}", js).group(1)
    ).group(1)
    page.evaluate("() => analizaDodajUStrategiju()")
    page.wait_for_timeout(500)
    assert _aiws_mod(page) == ocekivano
    assert "154 ZOO" in page.evaluate("() => document.getElementById('strat-tekst').value")


def test_s4_pro_kapija_je_sacuvana(page):
    """`openAITool` gejtuje `n` i `t`. Rewire ne sme da otvori PRO funkciju
    korisniku bez PRO statusa."""
    page.evaluate("() => { window.currentUserIsPro = false; window.__proModal = 0;"
                  "        window.openProUpgradeModal = function(){ window.__proModal++; }; }")
    page.evaluate("() => analizaGenerisiNacrt()")
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.__proModal") >= 1, (
        "korisnik bez PRO statusa je ušao u nacrte bez ponude za nadogradnju"
    )


# ═══════════════════════════════════════════════════════════════════════════
# STAVKA 3 — glasovna komanda „generiši dokument"
# ═══════════════════════════════════════════════════════════════════════════

def test_s3_glas_otvara_generator_a_ne_pregled(page):
    """Pre popravke: `pred_subtabSwitch('nacrti')` — a `'nacrti'` NIJE u VALID
    listi te funkcije, pa je tiho padalo na `pregled`. Korisnik je dobijao
    poruku „Otvaram generator dokumenata" i ekran Pregleda."""
    page.evaluate(
        """() => { window.activePredmetId = 'p1';
                   voice_doAction('generate_document', {}); }"""
    )
    page.wait_for_timeout(600)
    assert _aiws_mod(page) == "nacrti", (
        f"glasovna komanda je otvorila {_aiws_mod(page)!r} umesto generatora"
    )


def test_s3_preselekcija_tipa_koristi_kanonski_postavljac(page):
    """`#tip-podneska` je zamenjen skrivenim `#podnesak-tip` uz 24 dugmeta.

    Vrednost se ne sme postavljati direktno — `_selectPodnesakOption()` uz nju
    ažurira i izabrano dugme i objašnjenje ispod njega.
    """
    page.evaluate(
        """() => { window.activePredmetId = 'p1';
                   voice_doAction('generate_document', { tip: 'zalba' }); }"""
    )
    page.wait_for_timeout(800)
    stanje = page.evaluate(
        """() => ({
             vrednost: document.getElementById('podnesak-tip').value,
             izabrano: [...document.querySelectorAll('.podnesak-option.selected')]
                         .map(b => b.dataset.value)
           })"""
    )
    assert "zalba" in stanje["vrednost"], (
        f"tip podneska nije preseletovan; vrednost je {stanje['vrednost']!r}"
    )
    assert stanje["izabrano"] == [stanje["vrednost"]], (
        f"skrivena vrednost i izabrano dugme se ne slažu: {stanje}"
    )


def test_s3_bez_predmeta_ne_otvara_nista(page):
    """Granični uslov koji je i pre popravke postojao — ne sme se izgubiti."""
    page.evaluate(
        """() => { window.activePredmetId = null; window.__toast = [];
                   window.showToast = function(m){ window.__toast.push(m); };
                   voice_doAction('generate_document', {}); }"""
    )
    page.wait_for_timeout(400)
    poruke = page.evaluate("() => window.__toast")
    assert any("predmet" in m.lower() for m in poruke), (
        f"bez otvorenog predmeta nema upozorenja; poruke: {poruke}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# STRUKTURNO
# ═══════════════════════════════════════════════════════════════════════════

def test_mrtve_reference_ovih_stavki_su_nestale():
    js = _js()
    for mrtva in ("getElementById('pred-novi-btn')",
                  "getElementById('tip-podneska')",
                  "#tab-n textarea"):
        assert mrtva not in js, f"mrtva referenca `{mrtva}` je vraćena"


def test_nema_js_gresaka(page):
    for f in ("analizaSacuvajUPredmet", "analizaGenerisiNacrt", "analizaDodajUStrategiju"):
        page.evaluate("(f) => window[f]()", f)
        page.wait_for_timeout(250)
    assert not page.greske, f"JS greške posle rewire-a: {page.greske}"
