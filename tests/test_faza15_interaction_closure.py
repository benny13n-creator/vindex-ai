# -*- coding: utf-8 -*-
"""
FAZA 1.5 — INTERACTION CLOSURE (R-001 … R-004).

Četiri nalaza koje je re-audit kritičnih kontrola ostavio otvorene. Svaki se
ovde zatvara po istoj matrici:

    reprodukcija pre → popravka → granični uslovi → mutacija → runtime

`R-001`  „Pomoć & podrška" nije imala NIJEDAN rukovalac
`R-002`  „Otpremi dokument" nedostupno tastaturom
`R-003`  polje za pravni upit bez pristupačnog imena
`R-004`  „Prijavi netačan odgovor" — potvrda uspeha bez ishoda

NIŠTA SE NE ČITA IZ IZVORA. Sve se izvršava u pravom Chromium-u nad pravim
`index.html`. Za `R-003` se čita **stablo pristupačnosti**, ne atribut — jer
`aria-label` koji postoji a ne stiže do stabla ne pomaže nikome.
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


_STUB = """
window.__req = [];
window.__supaInsert = [];
window.__supaDostupan = true;
window.__supaGreska = null;
window.fetch = function(u, o) {
  window.__req.push({ u: String(u), m: (o && o.method) || 'GET' });
  return Promise.resolve({
    ok: true, status: 200,
    json: () => Promise.resolve({}), text: () => Promise.resolve('{}'),
    headers: { get: () => 'application/json' }
  });
};
"""


@pytest.fixture
def page(browser, server):
    p = browser.new_page(viewport={"width": 1440, "height": 900})
    p.greske = []
    p.on("pageerror", lambda e: p.greske.append(str(e).split("\n")[0]))
    p.route(
        "**/*",
        lambda r: r.continue_() if r.request.url.startswith(server) else r.abort(),
    )
    p.add_init_script(_STUB)
    p.goto(f"{server}/index.html", wait_until="load")
    p.wait_for_function("typeof updateAuthUI === 'function'", timeout=20000)
    p.evaluate(
        """() => {
          window.currentSession = { access_token: 't' };
          window.currentUser    = { id: 'u1', email: 't@t.rs' };
          updateAuthUI();
          // `_waitSupa` čeka na CDN koji je u testu blokiran; zamenjuje se
          // upravljivim dvojnikom TEK POSLE učitavanja skripte, da ga
          // deklaracija iz `vindex.js` ne prepiše.
          window._waitSupa = function() {
            if (!window.__supaDostupan) return Promise.resolve(null);
            return Promise.resolve({
              from: function(t) {
                return { insert: function(row) {
                  window.__supaInsert.push({ t: t, row: row });
                  return Promise.resolve(
                    window.__supaGreska ? { error: { message: window.__supaGreska } } : {}
                  );
                }};
              }
            });
          };
        }"""
    )
    p.wait_for_timeout(250)
    try:
        yield p
    finally:
        p.close()


def _pristupacno_ime(page, selektor):
    """Ime iz STABLA PRISTUPAČNOSTI — ono što čitač ekrana stvarno izgovori.

    `page.accessibility` u ovoj verziji Playwright-a ne postoji, pa se koristi
    `Locator.aria_snapshot()` — isti izvor, ARIA stablo koje pregledač izlaže
    pomoćnim tehnologijama. Namerno se NE čitaju atributi: `aria-label` koji
    postoji a ne stigne do stabla (npr. jer ga nadjača `aria-labelledby` ili
    element nema ulogu) ne pomaže nikome.
    """
    lok = page.locator(selektor).first
    assert lok.count() > 0, f"element {selektor} ne postoji"
    snimak = lok.aria_snapshot()
    # Oblik: `- button "Ime"` / `- textbox "Ime"` — ime je u navodnicima.
    m = re.search(r'"([^"]*)"', snimak or "")
    return m.group(1) if m else ""


# ═══════════════════════════════════════════════════════════════════════════
# R-001 — „POMOĆ & PODRŠKA" VODI NA POSTOJEĆE ODREDIŠTE
# ═══════════════════════════════════════════════════════════════════════════

def test_r001_pomoc_ima_rukovalac(page):
    """Pre popravke: nijedan `onclick`, nijedan slušalac. CSS joj je davao
    `cursor:pointer` i hover — lažna affordance."""
    stanje = page.evaluate(
        """() => {
             const e = document.querySelector('.vx-sidebar-help');
             return e ? { onclick: !!e.getAttribute('onclick'),
                          uloga: e.getAttribute('role'),
                          tabindex: e.tabIndex } : null;
           }"""
    )
    assert stanje, "`.vx-sidebar-help` je nestala iz index.html"
    assert stanje["onclick"], "Pomoć i podrška i dalje nema rukovalac"
    assert stanje["uloga"] == "button", "nije označena kao dugme za čitač ekrana"
    assert stanje["tabindex"] >= 0, "nije dohvatljiva tastaturom"


def test_r001_pomoc_ima_pristupacno_ime(page):
    ime = _pristupacno_ime(page, ".vx-sidebar-help")
    assert "podršk" in ime.lower() or "pomoć" in ime.lower(), (
        f"pristupačno ime je {ime!r} — čitač ekrana ne kaže čemu kontrola služi"
    )


def test_r001_klik_vodi_na_kanonsko_odrediste(page):
    """SRŽ. Ne proverava se da je funkcija pozvana, nego da je korisnik
    STVARNO stigao do sekcije za podršku.

    Odredište nije izmišljeno: `#pomoc-section` (FAQ + forma koja šalje na
    `/api/support/poruka`) postoji u Podešavanjima i do njega do sada nije
    vodila nijedna kontrola.
    """
    page.evaluate("() => document.querySelector('.vx-sidebar-help').click()")
    page.wait_for_timeout(400)
    stanje = page.evaluate(
        """() => {
             const s = document.getElementById('pomoc-section');
             const t = document.getElementById('tab-settings');
             return {
               tabOtvoren: t ? getComputedStyle(t).display !== 'none' : false,
               sekcijaPostoji: !!s,
               sekcijaVidljiva: s ? (s.getBoundingClientRect().height > 0) : false,
               aktivanTab: (document.querySelector('.t-tab.active') || {}).id || null
             };
           }"""
    )
    assert stanje["sekcijaPostoji"], "`#pomoc-section` ne postoji — odredište je nestalo"
    assert stanje["tabOtvoren"], "Podešavanja se nisu otvorila"
    assert stanje["aktivanTab"] == "tab-btn-settings", (
        f"aktivan tab je {stanje['aktivanTab']!r}"
    )
    assert stanje["sekcijaVidljiva"], "sekcija za podršku nije iscrtana"


def test_r001_radi_i_tastaturom(page):
    """`<div role=\"button\">` ne aktivira `onclick` na `Enter` sam od sebe."""
    page.evaluate("() => document.querySelector('.vx-sidebar-help').focus()")
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    aktivan = page.evaluate(
        "() => (document.querySelector('.t-tab.active') || {}).id || null"
    )
    assert aktivan == "tab-btn-settings", (
        f"`Enter` nije otvorio podršku (aktivan tab: {aktivan!r})"
    )


# ═══════════════════════════════════════════════════════════════════════════
# R-002 — „OTPREMI DOKUMENT" TASTATUROM
# ═══════════════════════════════════════════════════════════════════════════

def _otvori_dokumente(page):
    page.evaluate(
        """() => {
             setTab(document.getElementById('tab-btn-p'), 'p');
             document.querySelectorAll('.pred-detail').forEach(e => e.style.display = 'block');
             pred_subtabSwitch('dokumenti');
             // Špijun na skrivenom polju za fajl — `pred_upload_trigger()` ga klikne.
             window.__pickerOtvoren = 0;
             const inp = document.getElementById('pred-upload-input');
             inp.addEventListener('click', function(e) {
               window.__pickerOtvoren++; e.preventDefault();
             });
           }"""
    )
    page.wait_for_timeout(250)


def test_r002_zona_je_dohvatljiva_tastaturom(page):
    _otvori_dokumente(page)
    stanje = page.evaluate(
        """() => {
             const e = document.getElementById('pred-upload-zone');
             return { uloga: e.getAttribute('role'), tabindex: e.tabIndex };
           }"""
    )
    assert stanje["uloga"] == "button", "zona za otpremanje nije označena kao dugme"
    assert stanje["tabindex"] >= 0, "do zone za otpremanje se ne može doći tastaturom"


@pytest.mark.parametrize("taster", ["Enter", "Space"])
def test_r002_taster_stvarno_otvara_izbor_fajla(page, taster):
    """SRŽ R-002. Ne meri se da je funkcija pozvana, nego da je izbor fajla
    STVARNO otvoren — jer `tabindex=\"0\"` na `<div>` daje fokus, a ne radnju."""
    _otvori_dokumente(page)
    page.evaluate("() => document.getElementById('pred-upload-zone').focus()")
    page.keyboard.press(taster)
    page.wait_for_timeout(250)
    puta = page.evaluate("() => window.__pickerOtvoren")
    assert puta == 1, (
        f"taster `{taster}` je otvorio izbor fajla {puta} puta (očekivano tačno 1)"
    )


def test_r002_ima_pristupacno_ime(page):
    _otvori_dokumente(page)
    ime = _pristupacno_ime(page, "#pred-upload-zone")
    assert "otpremi" in ime.lower() or "dokument" in ime.lower(), (
        f"pristupačno ime zone za otpremanje je {ime!r}"
    )


def test_r002_klik_misem_i_dalje_radi(page):
    """Negativna kontrola nad popravkom: dodavanje tastature ne sme da pokvari miš."""
    _otvori_dokumente(page)
    page.evaluate("() => document.getElementById('pred-upload-zone').click()")
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__pickerOtvoren") == 1, (
        "klik mišem više ne otvara izbor fajla"
    )


# ═══════════════════════════════════════════════════════════════════════════
# R-003 — POLJE ZA PRAVNI UPIT IMA IME U STABLU PRISTUPAČNOSTI
# ═══════════════════════════════════════════════════════════════════════════

def test_r003_polje_ima_pristupacno_ime(page):
    """Meri se STABLO PRISTUPAČNOSTI, ne atribut.

    `placeholder` nije pristupačno ime: nestaje čim korisnik počne da kuca, a
    kod nekih polja u ovoj aplikaciji je i izmišljeno lično ime, pa čitač
    ekrana izgovori osobu umesto naziva polja.
    """
    page.evaluate("() => setTab(document.getElementById('tab-btn-aiws'), 'aiws')")
    page.wait_for_timeout(250)
    ime = _pristupacno_ime(page, "#qi")
    assert ime, "polje za pravni upit nema pristupačno ime"
    assert "pravno pitanje" in ime.lower(), (
        f"pristupačno ime je {ime!r} — očekivana je postojeća vidljiva labela"
    )


def test_r003_koristi_postojecu_vidljivu_labelu(page):
    """Bez dupliranja teksta: labela koja je već na ekranu je i programska.

    Da je dodat `aria-label` sa drugačijim tekstom, čitač ekrana bi izgovarao
    jedno a korisnik video drugo.
    """
    stanje = page.evaluate(
        """() => {
             const l = document.querySelector('label[for="qi"]');
             const q = document.getElementById('qi');
             return { povezana: !!l,
                      tekst: l ? l.textContent.trim() : null,
                      ariaLabel: q ? q.getAttribute('aria-label') : null };
           }"""
    )
    assert stanje["povezana"], "nema `<label for=\"qi\">` — veza je samo vizuelna"
    assert not stanje["ariaLabel"], (
        f"dodat je i `aria-label` ({stanje['ariaLabel']!r}) pored vidljive labele "
        f"— dva izvora imena za istu kontrolu"
    )


# ═══════════════════════════════════════════════════════════════════════════
# R-004 — PRIJAVA NETAČNOG ODGOVORA NE SME DA LAŽE O USPEHU
# ═══════════════════════════════════════════════════════════════════════════

def _iscrtaj_odgovor(page, pitanje="Uslovi za naknadu?", odgovor="Član 154 ZOO."):
    page.evaluate(
        """([p, o]) => {
             const d = document.createElement('div');
             d.innerHTML = _feedbackBar(p, o);
             document.getElementById('tab-aiws').appendChild(d);
           }""",
        [pitanje, odgovor],
    )
    page.wait_for_timeout(150)


def test_r004_dugme_se_pojavljuje_tek_uz_odgovor(page):
    assert page.evaluate("() => document.querySelectorAll('#fb-btn').length") == 0, (
        "traka za prijavu postoji i pre nego što je odgovor generisan"
    )
    _iscrtaj_odgovor(page)
    assert page.evaluate("() => document.querySelectorAll('#fb-btn').length") == 1


def test_r004_uspesna_prijava_zaista_upisuje_sadrzaj(page):
    """Sadržaj prijave postoji SAMO u `reported_errors`.

    `/api/feedback` po NO-STORAGE politici čuva isključivo heš pitanja i tip
    (`routers/drafting.py:796`), pa serverski poziv nije zamena za ovaj upis.
    """
    _iscrtaj_odgovor(page)
    page.evaluate("() => document.querySelector('#fb-btn').click()")
    page.wait_for_timeout(600)

    upisi = page.evaluate("() => window.__supaInsert")
    assert len(upisi) == 1, f"očekivan tačno 1 upis u bazu, dobijeno {len(upisi)}"
    assert upisi[0]["t"] == "reported_errors", f"upis je otišao u {upisi[0]['t']!r}"
    for polje in ("user_id", "original_prompt", "ai_response", "timestamp"):
        assert polje in upisi[0]["row"], f"upis nema polje `{polje}`"

    stanje = page.evaluate(
        "() => { const b = document.querySelector('#fb-btn');"
        "        return { tekst: b.textContent, onemogucen: b.disabled }; }"
    )
    assert "Prijavljeno" in stanje["tekst"], f"nema potvrde: {stanje['tekst']!r}"
    assert stanje["onemogucen"], "dugme ostaje aktivno posle uspešne prijave"


def test_r004_bez_veze_sa_bazom_NEMA_potvrde_uspeha(page):
    """NAJVAŽNIJI TEST U FAJLU.

    Pre popravke: `getSupabase()` vrati `null` dok se SDK ne učita, upis se
    tiho preskoči, a poruka „Prijavljeno — hvala" se postavljala BEZUSLOVNO.
    Advokat je dobijao potvrdu za prijavu koje nigde nema — a to je jedini
    kanal kojim se prijavljuje netačan pravni odgovor.
    """
    page.evaluate("() => { window.__supaDostupan = false; }")
    _iscrtaj_odgovor(page)
    page.evaluate("() => document.querySelector('#fb-btn').click()")
    page.wait_for_timeout(600)

    stanje = page.evaluate(
        """() => { const b = document.querySelector('#fb-btn');
                   return { tekst: b.textContent, onemogucen: b.disabled,
                            upisa: window.__supaInsert.length }; }"""
    )
    assert stanje["upisa"] == 0, "test ne meri ono što tvrdi — upis se ipak desio"
    assert "Prijavljeno" not in stanje["tekst"], (
        f"prikazana je potvrda uspeha bez ijednog upisa: {stanje['tekst']!r}"
    )
    assert not stanje["onemogucen"], (
        "dugme je onemogućeno iako prijava nije poslata — korisnik ne može da ponovi"
    )


def test_r004_greska_baze_takodje_ne_daje_potvrdu(page):
    """Supabase JS ne baca izuzetak — grešku vraća u objektu.

    Bez ove provere bi popravka pokrivala samo slučaj „nema klijenta", a
    odbijen upis bi i dalje izgledao kao uspeh.
    """
    page.evaluate("() => { window.__supaGreska = 'row-level security'; }")
    _iscrtaj_odgovor(page)
    page.evaluate("() => document.querySelector('#fb-btn').click()")
    page.wait_for_timeout(600)

    stanje = page.evaluate(
        "() => { const b = document.querySelector('#fb-btn');"
        "        return { tekst: b.textContent, onemogucen: b.disabled }; }"
    )
    assert "Prijavljeno" not in stanje["tekst"], (
        f"baza je odbila upis, a prikazana je potvrda: {stanje['tekst']!r}"
    )
    assert not stanje["onemogucen"], "korisnik ne može da ponovi prijavu"


def test_r004_dve_prijave_su_nezavisne(page):
    """Traka se crta po odgovoru; prijava jednog ne sme da zaključa drugi."""
    _iscrtaj_odgovor(page, "Prvo pitanje", "Prvi odgovor")
    _iscrtaj_odgovor(page, "Drugo pitanje", "Drugi odgovor")
    page.evaluate("() => document.querySelectorAll('#fb-btn')[0].click()")
    page.wait_for_timeout(600)
    stanje = page.evaluate(
        """() => { const b = document.querySelectorAll('#fb-btn');
                   return { prvi: b[0].disabled, drugi: b[1].disabled }; }"""
    )
    assert stanje["prvi"], "prvo dugme nije zaključano posle prijave"
    assert not stanje["drugi"], "prijava jednog odgovora zaključala je i drugi"


def test_r004_bez_js_gresaka(page):
    _iscrtaj_odgovor(page)
    page.evaluate("() => document.querySelector('#fb-btn').click()")
    page.wait_for_timeout(500)
    assert not page.greske, f"JS greške tokom prijave: {page.greske}"
