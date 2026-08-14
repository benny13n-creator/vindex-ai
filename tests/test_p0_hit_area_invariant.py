# -*- coding: utf-8 -*-
"""
P0-2 / P0-3 — INVARIANT DOSTUPNOSTI KLIKOM.

PRAVILO KOJE OVAJ FAJL ČUVA

    Nijedna vidljiva interaktivna kontrola ne sme biti potpuno prekrivena
    drugom interaktivnom kontrolom, ni na jednoj podržanoj širini ekrana.

ZAŠTO OVAKO, A NE „CSS SADRŽI right: 24px"

Prethodni test (`test_dashboard_polish.py`) je merio odnos glasovnog dugmeta
prema BOČNOJ TRACI i prolazio. Nikad nije pitao šta je već u donjem desnom uglu,
pa je `#feedback-fab` završio 100% prekriven — 49/49 tačaka blokirano na svih 7
merenih širina.

Isti test je tvrdio `"right" in blok` za mobilno pravilo i prolazio, dok je
pravilo u `@media (max-width: 768px)` istovremeno držalo `left: 18px`. Kad su
zadati i `left` i `right` uz fiksnu širinu, `left` pobeđuje — dakle test je
merio deklaraciju koja ne odlučuje.

Zato se ovde ne čita nijedan CSS. Pokreće se Chromium, uzima se
`getBoundingClientRect()` svake vidljive kontrole, i preko `elementFromPoint`
se za svaku tačku mreže pita KO STVARNO PRIMA KLIK. To je jedina provera koju
inline stil u `index.html` ne može da zaobiđe.

Mreža je zaključana na localhost; nijedan kredencijal se ne koristi.
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

# Širine: desktop opseg + tri stvarne širine telefona koje je vlasnik tražio.
_SIRINE_DESKTOP = [1920, 1440, 1366, 1280, 1024]
_SIRINE_MOBILNE = [768, 412, 390, 375]
_SVE_SIRINE = _SIRINE_DESKTOP + _SIRINE_MOBILNE

# ── EVIDENCIJA NEIZMIRENIH KVAROVA ─────────────────────────────────────────
# Ovo NIJE spisak izuzetaka. Ovo je spisak kvarova koji su POTVRĐENI i nisu
# popravljeni u ovom sprintu, sa razlogom zašto nisu.
#
# Da se ne bi pretvorio u tiho gašenje testa, vezan je za dve tvrdnje:
#   · `test_evidentirani_kvarovi_se_i_dalje_reprodukuju` — svaki upisani kvar
#     MORA i dalje da postoji. Čim ga neko popravi, taj test pada i tera da se
#     zapis obriše. Zapis ne može da preživi svoju popravku.
#   · opšti invarianti ispod izuzimaju isključivo ove `id`-jeve; svaka nova
#     kontrola u istom stanju i dalje obara test.
# PRAZNO. `mic-qi` je bio jedini zapis i zatvoren je u P0F-001 sprintu
# (`tests/test_p0f001_mobile_collision.py`) — zato je i obrisan odavde, kako
# `test_evidentirani_kvarovi_se_i_dalje_reprodukuju` i nalaže.
_EVIDENTIRANI_KVAROVI = {}


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


# ── Merenje ────────────────────────────────────────────────────────────────
# Za svaku VIDLJIVU interaktivnu kontrolu mere se DVE stvari, jer jedan broj
# ne može da izrazi obe polovine pravila:
#
#   `jezgro`  — mreža 7×7 preko središnjih 70% pravougaonika. Tu korisnik cilja
#               i tu ništa ne sme da presreće klik. Zašto 70%: kod okruglog
#               dugmeta (`border-radius: 50%`) uglovi pravougaonika padaju VAN
#               oblika, pa merenje po punom pravougaoniku prijavljuje lažnih
#               ~6% promašaja. Kvadrat upisan u krug ima stranicu 70,7% —
#               središnjih 70% je zato uvek unutar oblika, i za krug i za
#               pravougaonik.
#   `pun`     — ista mreža preko celog pravougaonika. Služi samo da se uhvati
#               kontrola koja je potpuno izgubljena.
#
# Beleži se i KO presreće, i da li je presretač i sam interaktivan — jer
# „preklopio ga je kontejner" i „pojelo ga je drugo dugme" nisu isti nalaz.
_MERI = """
() => {
  const SEL = 'button, a[href], input, select, textarea, [role="button"], [onclick]';
  const out = [];

  function skeniraj(el, r, udeo) {
    let pogodak = 0, uOkviru = 0;
    const krivci = {}, krivciInteraktivni = {};
    const dx = r.width * (1 - udeo) / 2, dy = r.height * (1 - udeo) / 2;
    const L = r.left + dx, T = r.top + dy;
    const W = r.width * udeo, H = r.height * udeo;
    for (let i = 1; i <= 7; i++) {
      for (let j = 1; j <= 7; j++) {
        const x = L + W * i / 8, y = T + H * j / 8;
        if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
        uOkviru++;
        const t = document.elementFromPoint(x, y);
        if (t && (t === el || el.contains(t) || t.contains(el))) { pogodak++; continue; }
        if (t) {
          const k = t.closest(SEL);
          const ime = String(k ? (k.id || k.className || k.tagName)
                               : (t.id || t.className || t.tagName)).slice(0, 60);
          krivci[ime] = (krivci[ime] || 0) + 1;
          if (k && k !== el && !el.contains(k)) {
            krivciInteraktivni[ime] = (krivciInteraktivni[ime] || 0) + 1;
          }
        }
      }
    }
    return {
      uOkviru, pogodak,
      procenat: uOkviru ? Math.round(100 * pogodak / uOkviru) : -1,
      krivci, krivciInteraktivni
    };
  }

  document.querySelectorAll(SEL).forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    // NE koristiti `offsetParent === null` kao proveru vidljivosti: ono je
    // `null` i za svaki `position: fixed` element. Prva verzija ovog testa je
    // zbog toga izbacila iz merenja BAŠ ona dva plutajuća dugmeta radi kojih
    // je napisan. Element unutar `display:none` pretka ima nulti pravougaonik,
    // pa provera dimenzija ispod pokriva taj slučaj ispravno.
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;

    const jezgro = skeniraj(el, r, 0.70);
    const pun    = skeniraj(el, r, 1.00);
    out.push({
      id: el.id || '',
      opis: (el.id || el.getAttribute('aria-label') || (el.textContent || '').trim().slice(0, 40)
             || el.className || el.tagName).toString().slice(0, 60),
      w: Math.round(r.width), h: Math.round(r.height),
      jezgro, pun
    });
  });
  return out;
}
"""


def _pripremi(browser, base, sirina, otvori_intake=False):
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
        }"""
    )
    if otvori_intake:
        page.evaluate("() => intakeOtvori()")
        page.wait_for_timeout(450)   # panel ima 0.25s tranziciju
    else:
        page.wait_for_timeout(250)
    return page


# ═══════════════════════════════════════════════════════════════════════════
# 1. INVARIANT — NIJEDNA VIDLJIVA KONTROLA NIJE POTPUNO PREKRIVENA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina", _SVE_SIRINE)
def test_nijedna_vidljiva_kontrola_nije_potpuno_prekrivena(browser, server, sirina):
    page = _pripremi(browser, server, sirina)
    mereno = page.evaluate(_MERI)
    page.close()

    assert len(mereno) > 20, (
        f"na {sirina}px izmereno samo {len(mereno)} kontrola — aplikacija se "
        f"nije iscrtala, pa test ne meri ono što tvrdi"
    )

    # `uOkviru == 0` znači da je kontrola van vidnog polja (npr. ispod skrola);
    # to je zasebno pitanje i ne meri se ovim invariantom.
    prekrivene = [
        m for m in mereno
        if m["pun"]["uOkviru"] > 0 and m["pun"]["pogodak"] == 0
        and m["id"] not in _EVIDENTIRANI_KVAROVI
    ]
    assert not prekrivene, (
        f"na {sirina}px sledeće vidljive kontrole ne primaju nijedan klik:\n"
        + "\n".join(
            f"  · {m['opis']} ({m['w']}×{m['h']}) — umesto nje klik prima: "
            f"{', '.join(m['pun']['krivci']) or 'ništa (van vidnog polja)'}"
            for m in prekrivene
        )
    )


@pytest.mark.parametrize("sirina", _SVE_SIRINE)
def test_nijednu_kontrolu_ne_presrece_druga_kontrola_u_jezgru(browser, server, sirina):
    """Druga polovina pravila, i stroža.

    Kontrola može biti „dostupna" a da joj drugo dugme jede deo mete — tada
    promašen klik pokrene tuđu radnju. U pravnoj aplikaciji to nije kozmetika:
    susedi su „pošalji" i „obriši" tipa radnji.

    Presretanje NEinteraktivnim kontejnerom se ovde ne broji — to je najčešće
    samo pozadina i ne krade klik korisniku.
    """
    page = _pripremi(browser, server, sirina)
    mereno = page.evaluate(_MERI)
    page.close()

    sudari = [
        m for m in mereno
        if m["jezgro"]["krivciInteraktivni"] and m["id"] not in _EVIDENTIRANI_KVAROVI
    ]
    assert not sudari, (
        f"na {sirina}px drugoj kontroli odlazi klik namenjen ovoj:\n"
        + "\n".join(
            f"  · {m['opis']} ({m['w']}×{m['h']}) — "
            + ", ".join(
                f"{k} na {v}/49 tačaka jezgra"
                for k, v in m["jezgro"]["krivciInteraktivni"].items()
            )
            for m in sudari
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. P0-2 — DVA PLUTAJUĆA DUGMETA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina", _SVE_SIRINE)
def test_feedback_i_voice_dugme_su_oba_potpuno_dostupna(browser, server, sirina):
    """Srž P0-2. Oba dugmeta žive u istom uglu; nijedno ne sme jesti drugo."""
    page = _pripremi(browser, server, sirina)
    mereno = {m["id"]: m for m in page.evaluate(_MERI) if m["id"]}
    page.close()

    for dugme in ("feedback-fab", "vx-voice-fab"):
        m = mereno.get(dugme)
        assert m, f"`#{dugme}` nije vidljivo na {sirina}px"
        assert m["jezgro"]["procenat"] == 100, (
            f"na {sirina}px `#{dugme}` prima klik na "
            f"{m['jezgro']['procenat']}% svog jezgra; presreće: "
            f"{', '.join(m['jezgro']['krivci']) or '—'}"
        )


def test_dugmad_se_ne_preklapaju_medjusobno(browser, server):
    """Ne samo „oba se mogu kliknuti" nego i „ne dodiruju se".

    Dva dugmeta mogu oba biti 100% dostupna a da im se pravougaonici i dalje
    dodiruju po ivici — to je krhko stanje koje sledeći `bottom` postane kvar.
    """
    page = _pripremi(browser, server, 1440)
    boks = page.evaluate(
        """() => ['feedback-fab','vx-voice-fab'].map(id => {
             const e = document.getElementById(id);
             const r = e.getBoundingClientRect();
             return { id, top: r.top, bottom: r.bottom, left: r.left, right: r.right };
           })"""
    )
    page.close()
    a, b = boks
    razmak = min(abs(a["top"] - b["bottom"]), abs(b["top"] - a["bottom"]))
    assert razmak >= 8, (
        f"`{a['id']}` i `{b['id']}` su razmaknuti samo {razmak:.0f}px — "
        f"premalo da promašen klik ne pogodi pogrešno dugme"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. P0-3 — ČAROBNJAK NOVI PREDMET NA TELEFONU
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina", _SIRINE_MOBILNE + [1920, 1366])
def test_dalje_dugme_carobnjaka_je_dostupno(browser, server, sirina):
    """Glavni CTA čarobnjaka. Ako je prekriven, čarobnjak staje na koraku 1."""
    page = _pripremi(browser, server, sirina, otvori_intake=True)
    mereno = {m["id"]: m for m in page.evaluate(_MERI) if m["id"]}
    page.close()

    m = mereno.get("intake-btn-next")
    assert m, (
        f"`#intake-btn-next` nije vidljiv na {sirina}px — čarobnjak se nije "
        f"otvorio ili je dugme van vidnog polja"
    )
    assert m["jezgro"]["procenat"] == 100, (
        f"na {sirina}px dugme „Dalje →\" prima klik na "
        f"{m['jezgro']['procenat']}% jezgra; presreće: "
        f"{', '.join(m['jezgro']['krivci']) or '—'}"
    )


@pytest.mark.parametrize("sirina", _SIRINE_MOBILNE)
def test_otvoren_carobnjak_je_iznad_mobilne_navigacije(browser, server, sirina):
    """Uzrok, ne posledica.

    Ako panel ikada ponovo padne ispod trake, ovo pada čak i kad bi dugme
    slučajno bilo negde gde traka ne stiže.
    """
    page = _pripremi(browser, server, sirina, otvori_intake=True)
    z = page.evaluate(
        """() => {
          const p = document.querySelector('.intake-panel');
          const n = document.getElementById('vx-mobile-nav');
          const zi = e => e ? parseInt(getComputedStyle(e).zIndex || '0', 10) || 0 : null;
          return { panel: zi(p), nav: zi(n),
                   navVidljiv: n ? getComputedStyle(n).display !== 'none' : false };
        }"""
    )
    page.close()
    if not z["navVidljiv"]:
        pytest.skip(f"mobilna navigacija nije prikazana na {sirina}px")
    assert z["panel"] > z["nav"], (
        f"na {sirina}px panel čarobnjaka ({z['panel']}) je ispod mobilne "
        f"navigacije ({z['nav']})"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. STRUKTURNA ZAŠTITA — JEDAN IZVOR POZICIJE
# ═══════════════════════════════════════════════════════════════════════════

def test_feedback_dugme_nema_inline_poziciju():
    """Koren P0-2 nije bio pogrešan `bottom`, nego to što je pozicija stajala
    INLINE — pa je svaka provera koja gleda `static/vindex.css` bila slepa.

    Dodatno: `id` i `style` su bili u RAZLIČITIM redovima, pa ga ni pretraga
    `index.html` po redu nije nalazila.
    """
    import re
    html = open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()
    m = re.search(r'<button id="feedback-fab".*?>', html, re.S)
    assert m, "`#feedback-fab` je nestao iz index.html"
    oznaka = m.group(0)
    for svojstvo in ("position:", "bottom:", "right:", "left:", "z-index:"):
        assert svojstvo not in oznaka.replace(" ", ""), (
            f"`{svojstvo}` je vraćen u inline stil `#feedback-fab` — pozicija "
            f"mora ostati isključivo u static/vindex.css, uz #vx-voice-fab"
        )
    assert 'onclick="feedbackOpen()"' in oznaka, "rukovalac je izgubljen"


# ═══════════════════════════════════════════════════════════════════════════
# 5. EVIDENCIJA NE SME DA NADŽIVI POPRAVKU
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("sirina", [375])
def test_evidentirani_kvarovi_se_i_dalje_reprodukuju(browser, server, sirina):
    """Brava na spisku neizmirenih kvarova.

    Bez ovoga bi `_EVIDENTIRANI_KVAROVI` bio običan izuzetak: neko bi upisao
    `id` i zauvek ugasio proveru za njega. Ovako zapis mora da bude ISTINIT —
    čim kvar prestane da postoji, ovaj test pada i tera brisanje zapisa.
    """
    page = _pripremi(browser, server, sirina)
    mereno = {m["id"]: m for m in page.evaluate(_MERI) if m["id"]}
    page.close()

    for element_id, obrazlozenje in _EVIDENTIRANI_KVAROVI.items():
        m = mereno.get(element_id)
        assert m, (
            f"`#{element_id}` je u evidenciji kvarova, a više se ne prikazuje "
            f"na {sirina}px — zapis je zastareo, obrisati ga"
        )
        assert m["jezgro"]["krivciInteraktivni"], (
            f"`#{element_id}` VIŠE NIJE PREKRIVEN — kvar je popravljen. "
            f"Obrišite ga iz `_EVIDENTIRANI_KVAROVI` da bi opšti invariant "
            f"ponovo počeo da ga čuva. Zapis je glasio: {obrazlozenje}"
        )


def test_evidencija_je_kratka_i_obrazlozena():
    """Spisak neizmirenih kvarova mora ostati mali i sa razlogom uz svaki.

    Dugačak spisak znači da se invariant koristi kao ukras.
    """
    assert len(_EVIDENTIRANI_KVAROVI) <= 3, (
        "previše evidentiranih kvarova — invariant prestaje da štiti"
    )
    for element_id, obrazlozenje in _EVIDENTIRANI_KVAROVI.items():
        assert len(obrazlozenje) > 120, (
            f"zapis za `#{element_id}` nema obrazloženje zašto nije popravljeno"
        )
