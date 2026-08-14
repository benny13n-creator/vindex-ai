# -*- coding: utf-8 -*-
"""
P0F-001 — SUDAR RADNJI U DONJOJ ZONI NA TELEFONU.

ŠTA JE BILO

`#mic-qi` (diktat u polju za pravni upit) i `#vx-mobile-fab` (Novi predmet)
zauzimali su isti prostor:

    375px  `#mic-qi` [309,733,44,44]  vs  FAB [305,732,52,52]  →  0/49 dostupno
    390px                                                      →  21/49 (43%)
    412px                                                      →  21/49 (43%)

Posledica nije bila „mikrofon se ne vidi". Korisnik je hteo **diktat**, a sistem
je izvršavao **kreiranje predmeta**. Sudar radnji sa pogrešnom posledicom.

ŠTA OVAJ FAJL MERI — I ŠTA NAMERNO NE MERI

Ne proverava se nijedna CSS deklaracija i ne pominje se `align-items`. Da test
tvrdi „mikrofon je poravnat uz vrh", zaključao bi jednu implementaciju i pao bi
na svaku drugu ispravnu popravku.

Meri se ishod: **svaka tačka u meti kontrole mora pripadati toj kontroli.**
Zato ovaj isti test prolazi i ako se umesto mikrofona pomeri dugme Novi predmet
— što je i dokazano mutacijom (v. `docs/ux_audit/P0F001_REPORT.md`).
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

# Tri stvarne širine telefona koje je vlasnik tražio.
_SIRINE = [375, 390, 412]

# VISINE — dodate u drugoj iteraciji P0F-001.
#
# Prva verzija ovog fajla merila je samo na visini 860px i na osnovu toga je
# kvar proglašen zatvorenim. Re-audit kritičnih kontrola je pokazao da se na
# 740px vraćao (21/49 tačaka mikrofona pripadalo je dugmetu Novi predmet), jer
# se ceo kompozer pomera naniže i njegov vrh ponovo ulazi u pojas plutajućih
# dugmadi. Jedna visina ekrana nije dokaz.
#
# 667 = iPhone SE · 740 ≈ iPhone 13/14 sa trakama pregledača · 800 · 860
_VISINE = [667, 740, 800, 860]

_MATRICA = [(w, h) for w in _SIRINE for h in _VISINE]

# Kontrole donje akcione zone koje moraju biti neokrnjene.
_AKCIONA_ZONA = ["mic-qi", "vx-mobile-fab", "vx-voice-fab", "feedback-fab"]

# PLUTAJUĆA DUGMAD — presretanje od njih je UVEK kvar.
# Ona stoje na istom mestu bez obzira na skrol, pa korisnik nema način da sazna
# da mu neko drugi uzima dodir; a pritisak izvršava tuđu radnju.
_PLUTAJUCA = {"vx-mobile-fab", "vx-voice-fab", "feedback-fab", "pred-fab"}

# FIKSNA DONJA TRAKA je drugi razred i NIJE kvar sama po sebi.
# Sadržaj legitimno skroluje ispod nje — tako radi svaka mobilna aplikacija.
# Obaveza je da kontrola bude POTPUNO dostupna kad se doskroluje, što se ovde
# posebno dokazuje (`test_kontrole_su_potpuno_dostupne_kad_se_doskroluju`).
# Bez tog para tvrdnji bi ovo bilo spuštanje kriterijuma, a ne njegovo
# preciziranje.


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


_MERI = """
() => {
  const SEL = 'button, a[href], input, select, textarea, [role="button"], [onclick]';

  function skeniraj(el, r, udeo) {
    let pogodak = 0, uOkviru = 0;
    const krivci = {};
    const dx = r.width * (1 - udeo) / 2, dy = r.height * (1 - udeo) / 2;
    const L = r.left + dx, T = r.top + dy, W = r.width * udeo, H = r.height * udeo;
    for (let i = 1; i <= 7; i++) {
      for (let j = 1; j <= 7; j++) {
        const x = L + W * i / 8, y = T + H * j / 8;
        if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
        uOkviru++;
        const t = document.elementFromPoint(x, y);
        if (t && (t === el || el.contains(t) || t.contains(el))) { pogodak++; continue; }
        if (t) {
          const k = t.closest(SEL);
          if (k && k !== el && !el.contains(k)) {
            const ime = String(k.id || k.className || k.tagName).slice(0, 40);
            krivci[ime] = (krivci[ime] || 0) + 1;
          }
        }
      }
    }
    return { uOkviru, pogodak,
             procenat: uOkviru ? Math.round(100 * pogodak / uOkviru) : -1, krivci };
  }

  const out = {};
  document.querySelectorAll(SEL).forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const kljuc = el.id || null;
    if (!kljuc) return;
    out[kljuc] = {
      rect: [Math.round(r.left), Math.round(r.top),
             Math.round(r.right), Math.round(r.bottom)],
      jezgro: skeniraj(el, r, 0.70),
      pun:    skeniraj(el, r, 1.00)
    };
  });
  return out;
}
"""


def _ekran(browser, base, sirina, visina=860, na_dno=False):
    """Otvara ekran Vindex Intelligence — tamo gde `#mic-qi` živi."""
    page = browser.new_page(viewport={"width": sirina, "height": visina})
    page.route(
        "**/*",
        lambda r: r.continue_() if r.request.url.startswith(base) else r.abort(),
    )
    page.add_init_script(
        """
        window.fetch = function() {
          return Promise.resolve({
            ok: true, status: 200,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve('{}'),
            headers: { get: () => 'application/json' }
          });
        };
        """
    )
    page.goto(f"{base}/index.html", wait_until="load")
    page.wait_for_function("typeof updateAuthUI === 'function'", timeout=20000)
    page.evaluate(
        """() => {
          window.currentSession = { access_token: 't' };
          window.currentUser    = { id: 'u1', email: 't@t.rs' };
          updateAuthUI();
          setTab(document.getElementById('tab-btn-aiws'), 'aiws');
        }"""
    )
    page.wait_for_timeout(350)
    if na_dno:
        # `.vx-panels-wrap` je stvarni skrol kontejner (`overflow-y: auto`).
        # `.vx-body` to NIJE — merenje njega je u prvoj iteraciji dalo pogrešan
        # zaključak „panel se ne skroluje".
        page.evaluate(
            "() => { const w = document.querySelector('.vx-panels-wrap');"
            "        if (w) w.scrollTop = w.scrollHeight; }"
        )
        page.wait_for_timeout(250)
    return page


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — DIKTAT NE SME DA POKRENE KREIRANJE PREDMETA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_mikrofon_ne_deli_metu_sa_dugmetom_novi_predmet(browser, server, sirina, visina):
    """NAJVAŽNIJI TEST U FAJLU.

    Ne meri „da li se vidi" nego „ko prima dodir". Dok je kvar postojao, na
    375px je svih 49 tačaka mikrofona pripadalo dugmetu Novi predmet.
    """
    page = _ekran(browser, server, sirina, visina)
    mereno = page.evaluate(_MERI)
    page.close()

    mic = mereno.get("mic-qi")
    assert mic, (
        f"`#mic-qi` nije vidljiv na {sirina}×{visina}px na vrhu skrola — "
        f"to je dozvoljeno (sadržaj se skroluje), ali onda ovaj test ne meri "
        f"ništa; pokriva ga test o doskrolovanoj kontroli"
    )
    krivci_fab = {k: v for k, v in mic["pun"]["krivci"].items() if k in _PLUTAJUCA}
    assert not krivci_fab, (
        f"na {sirina}×{visina}px dodir namenjen diktatu pogađa plutajuće dugme: "
        f"{krivci_fab} (`#mic-qi` {mic['rect']})"
    )


@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_mikrofon_ne_deli_metu_ni_kad_je_doskrolovan(browser, server, sirina, visina):
    """Ista tvrdnja na drugom kraju skrola.

    Plutajuće dugme se ne pomera sa sadržajem, pa skrolovanje menja KOJI deo
    sadržaja je pod njim. Provera na jednoj poziciji skrola ne dokazuje ništa —
    isto kao što provera na jednoj visini ekrana nije dokazala ništa.
    """
    page = _ekran(browser, server, sirina, visina, na_dno=True)
    mereno = page.evaluate(_MERI)
    page.close()

    mic = mereno.get("mic-qi")
    assert mic, f"`#mic-qi` nije vidljiv ni posle skrolovanja na {sirina}×{visina}px"
    krivci_fab = {k: v for k, v in mic["pun"]["krivci"].items() if k in _PLUTAJUCA}
    assert not krivci_fab, (
        f"na {sirina}×{visina}px, doskrolovano, diktat i dalje deli metu sa "
        f"plutajućim dugmetom: {krivci_fab}"
    )


@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_kontrole_su_potpuno_dostupne_kad_se_doskroluju(browser, server, sirina, visina):
    """Druga polovina kriterijuma — bez nje bi gornje tvrdnje bile prazne.

    Dozvoljeno je da sadržaj bude iza fiksne donje trake dok se ne doskroluje.
    NIJE dozvoljeno da ostane nedostupan i posle toga.
    """
    page = _ekran(browser, server, sirina, visina, na_dno=True)
    mereno = page.evaluate(_MERI)
    page.close()

    for element_id in ("mic-qi", "qi", "exec-btn"):
        m = mereno.get(element_id)
        assert m, (
            f"`#{element_id}` nije vidljiv ni posle skrolovanja na "
            f"{sirina}×{visina}px — kontrola je nedohvatljiva, ne samo skrivena"
        )
        assert m["pun"]["procenat"] == 100, (
            f"na {sirina}×{visina}px `#{element_id}` je i posle skrolovanja "
            f"dostupan {m['pun']['procenat']}%; presreće: {m['pun']['krivci']}"
        )


@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_mikrofon_i_novi_predmet_se_geometrijski_ne_seku(browser, server, sirina, visina):
    """Uzrok, ne posledica.

    Dve mete mogu obe biti dostupne a da im se pravougaonici i dalje dodiruju —
    to je krhko stanje koje sledeća promena visine kompozera pretvara u kvar.
    """
    page = _ekran(browser, server, sirina, visina)
    mereno = page.evaluate(_MERI)
    page.close()

    a = mereno.get("mic-qi")
    b = mereno.get("vx-mobile-fab")
    assert a and b, f"nedostaje jedna od dve kontrole na {sirina}×{visina}px"

    al, at, ar, ab = a["rect"]
    bl, bt, br, bb = b["rect"]
    presek_x = max(0, min(ar, br) - max(al, bl))
    presek_y = max(0, min(ab, bb) - max(at, bt))
    assert presek_x * presek_y == 0, (
        f"na {sirina}×{visina}px pravougaonici se seku {presek_x}×{presek_y}px "
        f"(mic {a['rect']}, Novi predmet {b['rect']})"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. CELA DONJA AKCIONA ZONA, NE SAMO JEDAN PAR
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_svaka_kontrola_akcione_zone_ima_cistu_metu(browser, server, sirina, visina):
    """Vlasnikov zahtev: ne samo da se elementi ne preklapaju, nego da svaka
    tačka u meti pripada nameravanoj kontroli."""
    page = _ekran(browser, server, sirina, visina)
    mereno = page.evaluate(_MERI)
    page.close()

    problemi = []
    for element_id in _AKCIONA_ZONA:
        m = mereno.get(element_id)
        if not m:
            continue   # van vidnog polja na vrhu skrola — pokriva drugi test
        kriv = {k: v for k, v in m["jezgro"]["krivci"].items() if k in _PLUTAJUCA}
        if kriv:
            problemi.append(f"`#{element_id}` — jezgro presreće plutajuće dugme {kriv}")
    assert not problemi, (
        f"donja akciona zona na {sirina}×{visina}px:\n  " + "\n  ".join(problemi)
    )


@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_nijedna_kontrola_ekrana_nije_potpuno_prekrivena(browser, server, sirina, visina):
    """Šira mreža nad istim ekranom — da popravka jednog para ne stvori drugi.

    Upravo ovo je uhvatilo grešku u prvoj verziji P0-2 popravke, kad je
    premeštanje glasovnog dugmeta napravilo nov sudar sa `#vx-mobile-fab`.
    """
    page = _ekran(browser, server, sirina, visina)
    mereno = page.evaluate(_MERI)
    page.close()

    izgubljene = [
        f"`#{k}` — klik prima {', '.join(v['pun']['krivci'])}"
        for k, v in mereno.items()
        if v["pun"]["uOkviru"] > 0 and v["pun"]["pogodak"] == 0
        and any(c in _PLUTAJUCA for c in v["pun"]["krivci"])
    ]
    assert not izgubljene, (
        f"na {sirina}×{visina}px kontrole ne primaju nijedan klik:\n  "
        + "\n  ".join(izgubljene)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. MERENJE MORA DA BUDE ISPRAVNO POSTAVLJENO
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina, visina", _MATRICA)
def test_meri_se_pravi_ekran(browser, server, sirina, visina):
    """Negativna kontrola nad postavkom.

    Bez ovoga bi svi testovi iznad „prolazili" da se ekran Vindex Intelligence
    nikad nije otvorio — jer kontrole koje ne postoje ne mogu da se sudare.
    """
    page = _ekran(browser, server, sirina, visina)
    stanje = page.evaluate(
        """() => ({
             aiws: getComputedStyle(document.getElementById('tab-aiws')).display,
             mic:  !!document.getElementById('mic-qi'),
             nav:  getComputedStyle(document.getElementById('vx-mobile-nav')).display,
             fab:  getComputedStyle(document.getElementById('vx-mobile-fab')).display
           })"""
    )
    page.close()
    assert stanje["aiws"] != "none", "ekran Vindex Intelligence nije otvoren"
    assert stanje["mic"], "`#mic-qi` ne postoji u DOM-u"
    assert stanje["nav"] != "none", (
        f"mobilna navigacija nije prikazana na {sirina}×{visina}px — ovo nije mobilni "
        f"raspored, pa merenje ne odgovara scenariju"
    )
    assert stanje["fab"] != "none", (
        "`#vx-mobile-fab` nije prikazan — druga strana sudara nedostaje"
    )
