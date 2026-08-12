# -*- coding: utf-8 -*-
"""
REGISTAR ODLOŽENIH KVAROVA — „nije u scope-u" ≠ „nije problem".

ZAŠTO OVAJ FAJL POSTOJI

`_EVIDENTIRANI_KVAROVI` u `test_p0_hit_area_invariant.py` može da primi samo
kvar koji **opšti invariant ume da reprodukuje**. P0F-002 to ne može: jezgro
kontrole je čisto, pa ga invariant s pravom ne smatra kvarom. Da je ipak upisan
tamo, brava `test_evidentirani_kvarovi_se_i_dalje_reprodukuju` bi pala — i to
bi napravilo lažnu sigurnost u suprotnom smeru.

Rezultat bi bio najgori mogući: savršen sistem za zatvaranje kvarova, iz kog
ispadaju baš oni kvarovi koji se ne uklapaju u trenutni invariant.

Zato odloženi kvar ovde dobija:
  · **status** — `DEFERRED` / `VERIFIED` / `OUT-OF-SCOPE`
  · **vlasnika** — ko odlučuje kad se rešava
  · **dokaz reprodukcije** — izvršiv, ne opis
  · **uslov zatvaranja** — šta konkretno mora da se desi

Svaki zapis je zaključan sa dve strane:
  1. kvar MORA i dalje da se reprodukuje — čim se popravi, test pada i tera
     brisanje zapisa (isti princip kao `_EVIDENTIRANI_KVAROVI`);
  2. zapis mora imati sva polja i uslov zatvaranja — bez toga se ne prima.
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


# ═══════════════════════════════════════════════════════════════════════════
# REGISTAR
# ═══════════════════════════════════════════════════════════════════════════

_ODLOZENI = {
    "P0F-002": {
        "naslov": "Leva kolona plutajućih dugmadi pada preko polja za pravni upit",
        "status": "DEFERRED / VERIFIED / OUT-OF-SCOPE",
        "vlasnik": "founder — odluka o mobilnom rasporedu",
        "nadjeno": "2026-08-12, P0F-001 sprint",
        "poreklo": (
            "Regresija uvedena u P0-2 (`41de2f79`), kada su `#feedback-fab` i "
            "`#vx-voice-fab` premešteni u levu kolonu da bi se razdvojili od "
            "`#vx-mobile-fab`. Nije zatečen kvar — naš je."
        ),
        "opis": (
            "`#feedback-fab` (y 686–730) i `#vx-voice-fab` (y 744–792) padaju "
            "preko uglova polja `#qi` (y 673–773, puna širina ekrana). Dodir u "
            "krajnjem uglu polja otvara povratnu informaciju umesto da fokusira "
            "polje. Jezgro polja je 100% čisto, pa opšti invariant ovo ne "
            "prijavljuje."
        ),
        "tezina": (
            "NIŽA od P0F-001. Polje je 297×100 sa 100% dostupnim jezgrom; "
            "pogođeno je 3/49 odnosno 1–3/49 tačaka u samim uglovima. "
            "P0F-001 je bio 0/49 — potpuna nedostupnost."
        ),
        "zasto_odlozeno": (
            "Uzrok nije pozicija nego arhitektura mobilnog rasporeda: polje za "
            "upit zauzima punu širinu donjeg pojasa, pa SVAKO plutajuće dugme u "
            "tom pojasu pada preko njega. Merenjem utvrđeno da nema slobodnog "
            "mesta: kompozer drži y 673–773, navigacija y 800–860, procep je "
            "27px a pojasu treba 52px. Popravka traži rezervisanu traku u koju "
            "sadržaj ne ulazi — dakle mobilni raspored, ne pomeranje dugmeta."
        ),
        "uslov_zatvaranja": (
            "Plutajuća dugmad dobijaju rezervisanu geometriju koju sadržaj ne "
            "sme da zauzme (`dedicated interaction zone`), umesto da plutaju "
            "preko toka sadržaja. Tada `#qi` više ne deli prostor ni sa jednim "
            "plutajućim dugmetom, a vertikalni položaj mikrofona prestaje da "
            "zavisi od količine sadržaja iznad njega."
        ),
        "reprodukcija": {
            "sirine": [375, 390, 412],
            "zrtva": "qi",
            "krivci": ["feedback-fab", "vx-voice-fab"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# INFRASTRUKTURA
# ═══════════════════════════════════════════════════════════════════════════

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


_KO_PRESRECE = """
(zrtvaId) => {
  const SEL = 'button, a[href], input, select, textarea, [role="button"], [onclick]';
  const el = document.getElementById(zrtvaId);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return null;
  const krivci = {};
  for (let i = 1; i <= 7; i++) {
    for (let j = 1; j <= 7; j++) {
      const x = r.left + r.width * i / 8, y = r.top + r.height * j / 8;
      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
      const t = document.elementFromPoint(x, y);
      if (t && (t === el || el.contains(t) || t.contains(el))) continue;
      if (t) {
        const k = t.closest(SEL);
        if (k && k !== el && !el.contains(k)) {
          const ime = String(k.id || k.className || k.tagName).slice(0, 40);
          krivci[ime] = (krivci[ime] || 0) + 1;
        }
      }
    }
  }
  return krivci;
}
"""


def _ekran(browser, base, sirina):
    page = browser.new_page(viewport={"width": sirina, "height": 860})
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
    return page


# ═══════════════════════════════════════════════════════════════════════════
# 1. ZAPIS NE SME DA NADŽIVI SVOJU POPRAVKU
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sifra", sorted(_ODLOZENI))
def test_odlozeni_kvar_se_i_dalje_reprodukuje(browser, server, sifra):
    """Brava registra.

    Bez ovoga bi registar bio spisak lepih namera koji preživi i sopstveno
    rešenje. Ovako je zapis ISTINIT: čim kvar nestane, test pada i tera da se
    zapis obriše — što je jedini trenutak kada smemo reći da je zatvoren.
    """
    zapis = _ODLOZENI[sifra]
    rep = zapis["reprodukcija"]

    potvrdjeno_na = []
    for sirina in rep["sirine"]:
        page = _ekran(browser, server, sirina)
        krivci = page.evaluate(_KO_PRESRECE, rep["zrtva"])
        page.close()
        assert krivci is not None, (
            f"`#{rep['zrtva']}` nije vidljiv na {sirina}px — dokaz reprodukcije "
            f"za {sifra} više ne važi; proveriti da li je ekran promenjen"
        )
        if any(k in krivci for k in rep["krivci"]):
            potvrdjeno_na.append((sirina, {k: v for k, v in krivci.items()
                                           if k in rep["krivci"]}))

    assert potvrdjeno_na, (
        f"{sifra} SE VIŠE NE REPRODUKUJE ni na jednoj od širina {rep['sirine']}.\n"
        f"Ako je popravljen — obrišite zapis iz `_ODLOZENI` i iz\n"
        f"`docs/ux_audit/DEFERRED_DEFECTS.md`.\n\n"
        f"Zapis je glasio: {zapis['naslov']}\n"
        f"Uslov zatvaranja bio je: {zapis['uslov_zatvaranja']}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. ZAPIS MORA BITI UPOTREBLJIV ZA NEKOGA KO NIJE BIO U OVOM SPRINTU
# ═══════════════════════════════════════════════════════════════════════════

_OBAVEZNA_POLJA = (
    "naslov", "status", "vlasnik", "nadjeno", "poreklo",
    "opis", "tezina", "zasto_odlozeno", "uslov_zatvaranja", "reprodukcija",
)

_DOZVOLJENI_STATUSI = {"DEFERRED", "VERIFIED", "OUT-OF-SCOPE", "BLOCKED"}


@pytest.mark.parametrize("sifra", sorted(_ODLOZENI))
def test_zapis_ima_sva_polja(sifra):
    zapis = _ODLOZENI[sifra]
    nedostaju = [p for p in _OBAVEZNA_POLJA if not zapis.get(p)]
    assert not nedostaju, f"{sifra} nema polja: {nedostaju}"


@pytest.mark.parametrize("sifra", sorted(_ODLOZENI))
def test_status_je_iz_dozvoljenog_recnika(sifra):
    """Slobodan tekst u statusu znači da za pola godine niko ne zna šta je
    stanje. Rečnik je mali namerno."""
    delovi = {d.strip() for d in _ODLOZENI[sifra]["status"].split("/")}
    nepoznati = delovi - _DOZVOLJENI_STATUSI
    assert not nepoznati, (
        f"{sifra} ima status van rečnika: {nepoznati}; "
        f"dozvoljeno: {sorted(_DOZVOLJENI_STATUSI)}"
    )


@pytest.mark.parametrize("sifra", sorted(_ODLOZENI))
def test_uslov_zatvaranja_je_proverljiv(sifra):
    """„Popraviti kasnije" nije uslov zatvaranja.

    Uslov mora opisati STANJE SISTEMA po kome se vidi da je gotovo — inače
    kvar ostaje odložen zauvek jer niko ne zna kad sme da ga zatvori.
    """
    uslov = _ODLOZENI[sifra]["uslov_zatvaranja"]
    assert len(uslov) > 100, f"{sifra}: uslov zatvaranja je prekratak da bi značio nešto"
    prazne_fraze = ("kasnije", "kad bude vremena", "u nekom trenutku", "TBD")
    for fraza in prazne_fraze:
        assert fraza.lower() not in uslov.lower(), (
            f"{sifra}: uslov zatvaranja sadrži praznu frazu „{fraza}"
        )


def test_registar_ostaje_mali():
    """Dugačak registar odloženih kvarova je tehnički dug pod drugim imenom."""
    assert len(_ODLOZENI) <= 5, (
        f"{len(_ODLOZENI)} odloženih kvarova — registar prestaje da bude "
        f"izuzetak i postaje zaostatak koji niko ne čita"
    )


def test_registar_je_i_dokumentovan():
    """Test je brava, dokument je objašnjenje. Oba moraju postojati."""
    put = os.path.join(_KOREN, "docs", "ux_audit", "DEFERRED_DEFECTS.md")
    assert os.path.exists(put), "nema docs/ux_audit/DEFERRED_DEFECTS.md"
    sadrzaj = open(put, encoding="utf-8").read()
    for sifra in _ODLOZENI:
        assert sifra in sadrzaj, f"{sifra} nije opisan u DEFERRED_DEFECTS.md"
