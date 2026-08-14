# -*- coding: utf-8 -*-
"""
P0-1 — ADVOKAT MORA DA VIDI DA MU ORIGINAL NIJE SAČUVAN.

ŠTA SE DESILO

`POST /api/predmeti/{id}/upload` (`api.py:5608`) vraća `original_preserved`.
Polje je dodato u Final Beta Gate F7 jer je advokat čiji potpisani original
NIJE sačuvan u trezoru video isti ekran uspeha kao onaj čiji jeste.

`static/vindex.js:20110` to polje čita i gradi upozorenje. Zatim ga na `:20124`
upisuje u `#pred-procena-result` — kontejner koji je nestao iz `index.html` u
commit-u `010082aa` zajedno sa panelom `#pred-pane-ai-analiza`.

Zaštita `if (resEl)` je zbog toga tiho preskakala ceo ispis. Upload je i dalje
radio, backend je i dalje slao istinu, a korisnik je video potpun uspeh.

ZAŠTO OVAJ TEST IZGLEDA OVAKO

Postojeći test `test_iron_lawyer_frontend_fixes.py:245` proverava
`assert "if (d.original_preserved === false) {" in VINDEX_JS` — postojanje niske
u izvoru. Prolazio je sve vreme dok je funkcija bila nedostupna, jer meri jednu
stranu ugovora: da JS piše upozorenje, nikad da ga DOM prima.

Zato se ovde ništa ne čita iz fajla. Pokreće se pravi Chromium, učitava se pravi
`index.html` sa pravim `vindex.js`, poziva se prava `pred_upload_doc()`, i meri
se `innerText` — dakle tekst koji je STVARNO iscrtan na ekranu. `innerText`
vraća prazno za sve što je `display:none`, pa test ne može da prođe na skrivenom
elementu.

Mreža je zaključana na localhost; nijedan kredencijal se ne koristi.
"""
import http.server
import json
import os
import socket
import socketserver
import threading

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_UPOZORENJE = "Originalni fajl nije sačuvan u trezoru"

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright nije instaliran"
)


# ═══════════════════════════════════════════════════════════════════════════
# INFRASTRUKTURA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def server():
    """Servira repo koren. `index.html` traži `static/…` relativno."""
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
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
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


# `pred_upload_doc` čita polja odgovora koja backend stvarno šalje
# (`api.py:5595-5608`). Oblik je prepisan odatle, ne izmišljen.
def _odgovor(original_preserved: bool) -> dict:
    return {
        "ok": True,
        "naziv_fajla": "tuzba-potpisana.pdf",
        "doc_type": "ugovor",
        "procena": "1. PRAVNI OSNOV\nČlan 1. ZOO.\n",
        "metadata": {},
        "predlozi_povezivanja": [],
        "mozda_duplikat": False,
        "original_preserved": original_preserved,
    }


def _otvori(browser, base, odgovor, ukloni_kontejner=False):
    """Učita aplikaciju, izvrši pravi upload tok, vrati VIDLJIV tekst."""
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Ništa ne sme napolje. Sve što nije naš server se prekida.
    page.route(
        "**/*",
        lambda r: r.continue_() if r.request.url.startswith(base) else r.abort(),
    )

    page.add_init_script(
        """
        window.__upload_odgovor = %s;
        window.__pozvane = [];
        window.fetch = function(url, opt) {
          var u = String(url);
          window.__pozvane.push(u);
          var telo = /\\/upload$/.test(u) ? window.__upload_odgovor : {};
          return Promise.resolve({
            ok: true, status: 200,
            json: function() { return Promise.resolve(telo); },
            text: function() { return Promise.resolve(JSON.stringify(telo)); },
            headers: { get: function() { return 'application/json'; } }
          });
        };
        """
        % json.dumps(odgovor)
    )

    page.goto(f"{base}/index.html", wait_until="load")
    page.wait_for_function("typeof pred_upload_doc === 'function'", timeout=20000)

    # Stanje koje `pred_upload_doc` zahteva. Prava prijava se ne koristi.
    page.evaluate(
        """() => {
          window.currentSession   = { access_token: 'test' };
          window.currentUser      = { id: 'u1', email: 't@t.rs' };
          window.activePredmetId  = '11111111-1111-1111-1111-111111111111';
          window.activePredmetNaziv = 'Test';
          // Do panela se ide APLIKACIJINOM navigacijom, ne ručnim otkrivanjem
          // predaka. `#vx-shell` i `#tab-p` su `display:none` do prijave, pa bi
          // ručno postavljanje `display` dokazalo samo da CSS može da se
          // prepiše — ne i da korisnik može da stigne do ekrana.
          updateAuthUI();                                   // otkriva #vx-shell
          setTab(document.getElementById('tab-btn-p'), 'p'); // otvara #tab-p
          // Detalj predmeta se otvara tek kad se klikne red u listi, a lista
          // ovde nije učitana; ovo je jedini korak koji se ne može odigrati
          // navigacijom bez podataka.
          document.querySelectorAll('.pred-detail').forEach(e => e.style.display = 'block');
          pred_subtabSwitch('dokumenti');
        }"""
    )

    if ukloni_kontejner:
        # NEGATIVNA KONTROLA NAD SAMIM TESTOM — vraća kvar u prethodno stanje.
        page.evaluate(
            "() => { var e = document.getElementById('pred-procena-result');"
            "        if (e) e.remove(); }"
        )

    page.evaluate(
        """async () => {
          const f = new File([new Uint8Array(64)], 'tuzba-potpisana.pdf',
                             { type: 'application/pdf' });
          await pred_upload_doc(f);
        }"""
    )
    page.wait_for_timeout(400)

    vidljiv = page.evaluate(
        """() => {
          const e = document.getElementById('pred-procena-result');
          if (!e) return { postoji: false, tekst: '', visina: 0 };
          return {
            postoji: true,
            tekst: e.innerText || '',
            visina: e.getBoundingClientRect().height,
            skriven: e.offsetParent === null
          };
        }"""
    )
    pozvane = page.evaluate("() => window.__pozvane")
    page.close()
    return vidljiv, pozvane


# ═══════════════════════════════════════════════════════════════════════════
# 1. PUT KOJI JE BIO SLOMLJEN
# ═══════════════════════════════════════════════════════════════════════════

def test_original_nije_sacuvan_advokat_vidi_upozorenje(browser, server):
    """NAJVAŽNIJI TEST U FAJLU.

    Ne meri da JS ima ispravnu granu. Meri da je tekst upozorenja STVARNO na
    ekranu posle pravog uploada.
    """
    v, pozvane = _otvori(browser, server, _odgovor(original_preserved=False))

    assert any("/upload" in u for u in pozvane), (
        "tok uploada nije ni pokrenut — test ne meri ono što tvrdi"
    )
    assert v["postoji"], "`#pred-procena-result` ne postoji u index.html"
    assert not v["skriven"], "kontejner je iscrtan ali nije vidljiv korisniku"
    assert v["visina"] > 0, "kontejner ima nultu visinu — nema šta da se vidi"
    assert _UPOZORENJE in v["tekst"], (
        "advokat čiji original NIJE sačuvan i dalje ne vidi upozorenje.\n"
        f"vidljiv tekst: {v['tekst'][:400]!r}"
    )


def test_original_jeste_sacuvan_nema_laznog_upozorenja(browser, server):
    """Druga strana. Bez ovoga bi test iznad prošao i da kontejner uvek ispisuje
    upozorenje — što bi bilo jednako štetno, samo u suprotnom smeru."""
    v, _ = _otvori(browser, server, _odgovor(original_preserved=True))

    assert v["postoji"] and not v["skriven"]
    assert _UPOZORENJE not in v["tekst"], (
        "upozorenje se prikazuje i kad je original uredno sačuvan"
    )
    assert v["tekst"].strip(), (
        "kontejner je prazan — znači ni gornja provera ništa ne dokazuje, "
        "jer bi 'nema upozorenja' bilo tačno i da se ništa ne iscrtava"
    )


def test_procena_dokumenta_stize_do_ekrana(browser, server):
    """Upozorenje nije jedino što je nestajalo. Nestajala je i sama analiza."""
    v, _ = _otvori(browser, server, _odgovor(original_preserved=True))
    assert "PRAVNI OSNOV" in v["tekst"].upper(), (
        f"AI procena dokumenta se ne iscrtava; vidljivo: {v['tekst'][:300]!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. NEGATIVNA KONTROLA NAD TESTOM
# ═══════════════════════════════════════════════════════════════════════════

def test_test_pada_ako_se_kontejner_ukloni(browser, server):
    """Vraća kvar i dokazuje da ga merenje hvata.

    Bez ove provere ne bismo znali da li testovi iznad prolaze zato što je
    popravka radi, ili zato što mere nešto što je uvek tačno.
    """
    v, _ = _otvori(
        browser, server, _odgovor(original_preserved=False), ukloni_kontejner=True
    )
    assert not v["postoji"], "kontejner nije uklonjen — negativna kontrola ne važi"
    assert _UPOZORENJE not in v["tekst"], (
        "upozorenje je 'vidljivo' i bez kontejnera — merenje ne diskriminiše"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. STRUKTURNA ZAŠTITA — DA SE ISTI KVAR NE VRATI TIHO
# ═══════════════════════════════════════════════════════════════════════════

def test_svaki_dom_id_koji_vindex_js_trazi_za_ovaj_tok_postoji():
    """Kvar je nastao tako što je HTML izgubio element, a JS to nije primetio.

    Ovo je uža verzija provere iz CANONICAL_INVENTORY §7 — ograničena na tok
    uploada, jer puna provera svih 1490 `getElementById` poziva pripada
    zasebnoj CI kapiji, ne ovom P0 patch-u.
    """
    html = open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()
    for element_id in (
        "pred-upload-input",
        "pred-upload-zone",
        "pred-upload-loading",
        "pred-upload-error",
        "pred-procena-result",
    ):
        assert f'id="{element_id}"' in html, (
            f"`{element_id}` traži `pred_upload_doc()` u static/vindex.js, "
            f"a u index.html ga nema — ista klasa kvara kao P0-1"
        )
