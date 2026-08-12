# -*- coding: utf-8 -*-
"""
FAZA 2 — FORENSIC CLEANUP: REMOVE / KEEP / MERGE / REWIRE.

Ovaj fajl zaključava tri vrste presude, jer sve tri mogu da se pokvare:

  REMOVE  uklonjeno ostrvo ne sme da se vrati kroz pola-refaktora
  REWIRE  „Štampaj" mora da štampa SADRŽAJ, ne prazan papir
  KEEP    funkcija bez ulazne tačke NE SME da bude obrisana sledeći put

Poslednje je najvažnije. `qiOtvori` i `bulkOtvori` izgledaju mrtvo — dugmad su
im trajno `display:none` i bez teksta. Ali iza njih stoje kompletni, ispravni
modali (6 dugmadi i 4 polja, odnosno 4 i 1). To je **mrtva ulazna tačka, ne
mrtva funkcija**, i razlika je razlog zbog kog Faza 2 nije „REMOVE sprint".
"""
import http.server
import os
import re
import socket
import socketserver
import threading

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JS_PUT = os.path.join(_KOREN, "static", "vindex.js")
_HTML_PUT = os.path.join(_KOREN, "index.html")


def _js():
    return open(_JS_PUT, encoding="utf-8").read()


def _html():
    return open(_HTML_PUT, encoding="utf-8").read()


def _bez_komentara(tekst: str) -> str:
    """Uklanja komentare — inače objašnjenje uklanjanja izgleda kao kod.

    Ista klasa greške koju je ovaj repo već tri puta uhvatio: test meri
    komentar umesto koda.
    """
    tekst = re.sub(r"<!--.*?-->", "", tekst, flags=re.S)
    tekst = re.sub(r"/\*.*?\*/", "", tekst, flags=re.S)
    tekst = re.sub(r"^\s*//.*$", "", tekst, flags=re.M)
    return tekst


# ═══════════════════════════════════════════════════════════════════════════
# 1. REMOVE — ostrvo `pred_openNewModal`
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ime", [
    "pred_openNewModal", "pred_closeNewModal", "pred_kreiraj",
])
def test_remove_funkcija_je_uklonjena(ime):
    js = _bez_komentara(_js())
    assert not re.search(r"function\s+" + re.escape(ime) + r"\s*\(", js), (
        f"`{ime}` je vraćena. Uklonjena je jer je celo ostrvo imalo NULA "
        f"pozivalaca (statičkih, dinamičkih i runtime); ako je vraćena, mora "
        f"imati i ulaznu tačku"
    )


@pytest.mark.parametrize("element_id", [
    "pred-new-modal", "pred-new-naziv", "pred-new-tip", "pred-new-opis", "pred-new-err",
])
def test_remove_dom_element_je_uklonjen(element_id):
    html = _bez_komentara(_html())
    assert f'id="{element_id}"' not in html, f"`#{element_id}` je vraćen u index.html"


def test_remove_nema_zaostalih_referenci():
    """Negativna kontrola nad uklanjanjem.

    Nije dovoljno da su funkcije nestale — ne sme ostati nijedan poziv ka
    njima, jer bi to bio tačno onaj obrazac koji je oborio `kalendarLoad`:
    definicija uklonjena, čitalac ostao.
    """
    js = _bez_komentara(_js())
    html = _bez_komentara(_html())
    for ime in ("pred_openNewModal", "pred_closeNewModal", "pred_kreiraj"):
        assert not re.search(r"\b" + re.escape(ime) + r"\s*\(", js + html), (
            f"postoji poziv ka uklonjenoj `{ime}` — `ReferenceError` na "
            f"najvišem nivou ubija ostatak fajla (v. P0-0)"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. KEEP — funkcija bez ulazne tačke se NE briše
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ime, overlay", [
    ("qiOtvori", "qi-overlay"),
    ("bulkOtvori", "bulk-overlay"),
])
def test_keep_funkcija_i_njen_modal_su_ocuvani(ime, overlay):
    """Presuda KEEP, sa razlogom upisanim u test.

    Ulazna dugmad (`#btn-hitan-hidden`, `#btn-csv-hidden`) su prazna i trajno
    `display:none`, a ništa u JS-u ih ne otkriva. Zato IZGLEDAJU mrtvo.
    Ali modali iza njih su kompletni i ispravni — brisanje bi uklonilo radeću
    funkciju, ne mrtav kod.
    """
    js = _js()
    html = _html()
    assert re.search(r"function\s+" + re.escape(ime) + r"\s*\(", js), (
        f"`{ime}` je obrisana. Njena ulazna tačka jeste mrtva, ali FUNKCIJA "
        f"nije — modal `#{overlay}` je kompletan. Ako se uklanja, uklanja se "
        f"cela funkcionalnost, i to je odluka vlasnika, ne čišćenje koda"
    )
    assert f'id="{overlay}"' in html, f"modal `#{overlay}` je nestao"


def test_keep_modali_su_i_dalje_upotrebljivi():
    """Bez ovoga bi test iznad prolazio i da je od modala ostala prazna ljuska."""
    html = _html()
    for overlay, min_dugmadi, min_polja in (("qi-overlay", 5, 3), ("bulk-overlay", 3, 1)):
        i = html.index(f'id="{overlay}"')
        segment = html[i:i + 9000]
        dugmadi = len(re.findall(r"<button", segment))
        polja = len(re.findall(r"<input|<select|<textarea", segment))
        assert dugmadi >= min_dugmadi and polja >= min_polja, (
            f"`#{overlay}` je osiromašen: {dugmadi} dugmadi, {polja} polja"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. REWIRE — „Štampaj" ne sme da štampa prazan predmet
# ═══════════════════════════════════════════════════════════════════════════

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
        window.fetch = () => Promise.resolve({ ok: true, status: 200,
          json: () => Promise.resolve({}), text: () => Promise.resolve('{}'),
          headers: { get: () => 'application/json' } });
        // Snima STANJE U TRENUTKU stampe -- posle `pred_print()` se svi paneli
        // vracaju na staro, pa merenje posle poziva ne bi dokazalo nista.
        window.__uTrenutkuStampe = null;
        window.print = function() {
          window.__uTrenutkuStampe = [...document.querySelectorAll('.pred-subtab-pane')]
            .filter(e => e.style.display !== 'none')
            .map(e => ({ id: e.id, tekst: (e.innerText || '').trim().length }));
        };
        """
    )
    p.goto(f"{server}/index.html", wait_until="load")
    p.wait_for_function("typeof pred_print === 'function'", timeout=20000)
    p.evaluate(
        """() => {
          window.currentSession = { access_token: 't' };
          window.currentUser    = { id: 'u1', email: 't@t.rs' };
          updateAuthUI();
          setTab(document.getElementById('tab-btn-p'), 'p');
          document.querySelectorAll('.pred-detail').forEach(e => e.style.display = 'block');
          pred_subtabSwitch('pregled');
        }"""
    )
    p.wait_for_timeout(300)
    try:
        yield p
    finally:
        p.close()


def test_rewire_stampa_prikazuje_panel_sa_sadrzajem(page):
    """SRŽ REWIRE-a.

    Pre popravke: `pred_print()` je sakrivao sve panele pa pokušavao da otkrije
    `#pred-pane-ccc`, koji ne postoji. `if (ccc)` je preskočio otkrivanje i
    `window.print()` je odštampao stranicu na kojoj je SVE sakriveno — prazan
    papir, bez ijedne poruke.
    """
    page.evaluate("() => pred_print()")
    page.wait_for_timeout(250)
    stanje = page.evaluate("() => window.__uTrenutkuStampe")

    assert stanje is not None, "`window.print()` nije ni pozvan"
    assert stanje, (
        "u trenutku štampe nijedan panel predmeta nije bio vidljiv — "
        "korisnik dobija prazan papir"
    )
    assert any(p["tekst"] > 0 for p in stanje), (
        f"vidljivi paneli u trenutku štampe nemaju sadržaj: {stanje}"
    )


def test_rewire_cilja_kanonskog_naslednika(page):
    """Odredište nije birano procenom — deklarisano je u samom kodu.

    `pred_subtabSwitch` drži `_legacyMap = { ccc:'pregled', … }`. Ako se ta mapa
    ikad promeni, ovaj test pada i tera da se i štampa uskladi s njom.
    """
    js = _js()
    m = re.search(r"_legacyMap\s*=\s*\{([^}]*)\}", js)
    assert m, "`_legacyMap` je nestala — kanonski naslednik više nije deklarisan"
    m2 = re.search(r"ccc\s*:\s*'([a-z-]+)'", m.group(1))
    assert m2, "`_legacyMap` više ne mapira `ccc`"
    naslednik = m2.group(1)

    stanje = page.evaluate("() => { pred_print(); return window.__uTrenutkuStampe; }")
    vidljivi = {p["id"] for p in (stanje or [])}
    assert f"pred-pane-{naslednik}" in vidljivi, (
        f"`_legacyMap` kaže `ccc → {naslednik}`, a štampa prikazuje {vidljivi}"
    )


def test_rewire_vraca_prethodno_stanje_panela(page):
    """Štampa ne sme da ostavi korisnika na drugom ekranu."""
    pre = page.evaluate(
        "() => [...document.querySelectorAll('.pred-subtab-pane')]"
        "        .map(e => e.style.display)"
    )
    page.evaluate("() => pred_print()")
    page.wait_for_timeout(250)
    posle = page.evaluate(
        "() => [...document.querySelectorAll('.pred-subtab-pane')]"
        "        .map(e => e.style.display)"
    )
    assert pre == posle, "štampa je promenila vidljivost panela i nije je vratila"


def test_uklanjanje_nije_pokvarilo_ucitavanje(page):
    """Posle P0-0 ovo je obavezno uz svako brisanje."""
    assert not page.greske, f"JS greške posle uklanjanja ostrva: {page.greske}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. BROJ MRTVIH REFERENCI NE SME DA RASTE
# ═══════════════════════════════════════════════════════════════════════════

def test_broj_mrtvih_dom_referenci_ne_raste():
    """Brava nad celom klasom.

    31 mrtva referenca je zatečeno stanje; ovim sprintom je smanjeno.
    Test ne traži nulu — traži da broj **ne raste**, jer bi svaka nova bila
    isti kvar koji je P0-1 već jednom sakrio od korisnika.
    """
    js = _js()
    html = _html()
    trazeni = set(re.findall(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", js))
    trazeni |= set(re.findall(r"querySelector(?:All)?\(\s*['\"]#([A-Za-z0-9_-]+)", js))
    staticki = set(re.findall(r'\bid="([^"]+)"', html))
    dinamicki = set(re.findall(r'\bid=[\\]?["\']([A-Za-z0-9_-]+)', js))
    dinamicki |= set(re.findall(r"\.id\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", js))

    mrtvi = sorted(trazeni - staticki - dinamicki)
    # 31 pre Faze 2 → 30 posle: `#pred-pane-ccc` je REWIRE-ovan na postojeći
    # `#pred-pane-pregled`. Uklanjanje ostrva `pred_openNewModal` NIJE smanjilo
    # ovaj broj — njegovih 5 ID-jeva je postojalo u HTML-u, pa nikad nije ni
    # bilo u ovom skupu. Prag je IZMERENA vrednost, ne željena.
    assert len(mrtvi) <= 30, (
        f"broj mrtvih DOM referenci je {len(mrtvi)} (izmereno posle Faze 2: 30):\n  "
        + "\n  ".join(mrtvi)
    )
