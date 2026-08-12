# -*- coding: utf-8 -*-
"""
P0-4 — GLAVNA NAVIGACIJA MORA DA RADI TASTATUROM.

ŠTA JE BILO

15 stavki glavne navigacije (`index.html:444-511`) su `<div class="t-tab"
onclick=...>` bez `role` i bez `tabindex`. Izmereno u pregledaču: 60 pritisaka
`Tab` i **0 zaustavljanja** na bilo kom `.t-tab`. `grep -c tabindex index.html`
je vraćao **0**.

Korisnik bez miša nije mogao da pređe ni na jedan ekran aplikacije — a to je
prva radnja posle prijave.

ŠTA OVAJ FAJL NE PRIHVATA KAO DOKAZ

Da atribut postoji. `tabindex="0"` na `<div>` čini element fokusabilnim, ali
`<div>` i dalje NE aktivira `onclick` na `Enter` ni `Space` — to radi samo
`<button>`. „Dodali smo tabindex" je zato tačna izjava i nedovoljna popravka.

Zato se ovde šalju stvarni pritisci tastera pravom pregledaču i meri se da li
se ekran ZAISTA promenio.
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
    p.route(
        "**/*",
        lambda r: r.continue_() if r.request.url.startswith(server) else r.abort(),
    )
    p.add_init_script(
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
    p.goto(f"{server}/index.html", wait_until="load")
    p.wait_for_function("typeof updateAuthUI === 'function'", timeout=20000)
    p.evaluate(
        """() => {
          window.currentSession = { access_token: 't' };
          window.currentUser    = { id: 'u1', email: 't@t.rs' };
          updateAuthUI();
        }"""
    )
    p.wait_for_timeout(250)
    try:
        yield p
    finally:
        p.close()


def _vidljivi_tabovi(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('.t-tab')]
              .filter(e => { const cs = getComputedStyle(e);
                             return cs.display !== 'none' && cs.visibility !== 'hidden'; })
              .map(e => e.id)"""
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. DOSTUPNOST — `Tab` MORA DA STIGNE DO SVAKE STAVKE
# ═══════════════════════════════════════════════════════════════════════════

def test_tab_stize_do_svake_stavke_glavne_navigacije(page):
    """NAJVAŽNIJI TEST U FAJLU. Ranije: 60 pritisaka, 0 zaustavljanja."""
    ocekivani = _vidljivi_tabovi(page)
    assert len(ocekivani) >= 10, (
        f"izmereno samo {len(ocekivani)} vidljivih tabova — aplikacija se nije "
        f"iscrtala, pa test ne meri ono što tvrdi"
    )

    page.evaluate("() => document.body.focus()")
    posecen = []
    for _ in range(140):
        page.keyboard.press("Tab")
        aktivan = page.evaluate(
            "() => { const a = document.activeElement;"
            "        return a && a.classList.contains('t-tab') ? a.id : null; }"
        )
        if aktivan and aktivan not in posecen:
            posecen.append(aktivan)
        if len(posecen) == len(ocekivani):
            break

    nedostupni = [t for t in ocekivani if t not in posecen]
    assert not nedostupni, (
        "do sledećih stavki glavne navigacije se ne može doći tasterom `Tab`:\n  "
        + "\n  ".join(nedostupni)
    )


def test_shift_tab_vraca_unazad(page):
    """Kretanje mora da radi u oba smera. Navigacija iz koje se ne može nazad
    je zamka, ne navigacija."""
    page.evaluate("() => document.getElementById('tab-btn-p').focus()")
    page.keyboard.press("Tab")
    napred = page.evaluate("() => document.activeElement.id")
    page.keyboard.press("Shift+Tab")
    nazad = page.evaluate("() => document.activeElement.id")
    assert nazad == "tab-btn-p", (
        f"`Shift+Tab` nije vratio fokus na polazni tab "
        f"(napred: {napred!r}, nazad: {nazad!r})"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. UPOTREBLJIVOST — FOKUS NIJE DOVOLJAN, MORA I DA SE AKTIVIRA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("taster", ["Enter", "Space"])
def test_taster_stvarno_otvara_ekran(page, taster):
    """Srž razlike između „fokusabilno" i „upotrebljivo".

    `<div tabindex="0">` prima fokus, ali NE aktivira `onclick` na `Enter` ni
    `Space` — to radi samo `<button>`. Ovde se meri da li se ekran promenio,
    ne da li je rukovalac pozvan.
    """
    pre = page.evaluate(
        "() => document.getElementById('tab-p').style.display"
    )
    page.evaluate("() => document.getElementById('tab-btn-p').focus()")
    page.keyboard.press(taster)
    page.wait_for_timeout(200)

    posle = page.evaluate(
        """() => ({
             prikazan: document.getElementById('tab-p').style.display,
             aktivan:  document.querySelector('.t-tab.active')?.id || null
           })"""
    )
    assert posle["prikazan"] != "none", (
        f"posle tastera `{taster}` panel „Predmeti" f"" f" nije prikazan "
        f"(pre: {pre!r}, posle: {posle['prikazan']!r})"
    )
    assert posle["aktivan"] == "tab-btn-p", (
        f"posle tastera `{taster}` aktivan tab je {posle['aktivan']!r}"
    )


def test_space_ne_skroluje_stranicu(page):
    """`Space` na `<div>` podrazumevano skroluje. Ako se ne spreči, korisnik
    otvori ekran i istovremeno izgubi mesto na njemu."""
    page.evaluate("() => document.getElementById('tab-btn-p').focus()")
    pre = page.evaluate("() => window.scrollY")
    page.keyboard.press("Space")
    page.wait_for_timeout(200)
    posle = page.evaluate("() => window.scrollY")
    assert posle == pre, f"`Space` je pomerio stranicu sa {pre} na {posle}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. VIDLJIVOST FOKUSA — ZAMKA `outline: none !important`
# ═══════════════════════════════════════════════════════════════════════════

def test_fokusiran_tab_ima_vidljiv_prsten(page):
    """`.t-tab` nosi `outline: none !important` iz vremena kad tabovi nisu ni
    bili fokusabilni. Čim su dobili `tabindex`, to je postalo zamka: element
    prima fokus, a korisnik ne vidi gde je.

    Meri se IZRAČUNATI stil pod stvarnim fokusom sa tastature, ne prisustvo
    pravila u CSS-u.
    """
    page.evaluate("() => document.getElementById('tab-btn-h').focus()")
    page.keyboard.press("Tab")          # kretanje tastaturom pali `:focus-visible`
    stil = page.evaluate(
        """() => {
             const a = document.activeElement;
             const cs = getComputedStyle(a);
             return {
               id: a.id,
               jeTab: a.classList.contains('t-tab'),
               fokusVidljiv: a.matches(':focus-visible'),
               outlineStyle: cs.outlineStyle,
               outlineWidth: cs.outlineWidth
             };
           }"""
    )
    assert stil["jeTab"], f"fokus nije na tabu nego na {stil['id']!r}"
    assert stil["fokusVidljiv"], "`:focus-visible` se ne poklapa pri kretanju tastaturom"
    assert stil["outlineStyle"] != "none", (
        f"fokusiran tab `{stil['id']}` nema vidljiv prsten — "
        f"`outline: none !important` je i dalje jači"
    )
    assert stil["outlineWidth"] not in ("0px", "0"), (
        f"prsten ima nultu debljinu: {stil['outlineWidth']}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. SEMANTIKA ZA ČITAČ EKRANA
# ═══════════════════════════════════════════════════════════════════════════

def test_svaki_tab_ima_ulogu_i_stanje(page):
    manjkavi = page.evaluate(
        """() => [...document.querySelectorAll('.t-tab')]
              .filter(e => e.getAttribute('role') !== 'tab'
                        || e.getAttribute('aria-selected') === null)
              .map(e => e.id || e.className)"""
    )
    assert not manjkavi, f"stavke bez `role=\"tab\"` ili `aria-selected`: {manjkavi}"


def test_aria_selected_prati_otvoren_ekran(page):
    """Bez ovoga čitač ekrana izgovara da je izabran tab koji više nije otvoren."""
    page.evaluate("() => setTab(document.getElementById('tab-btn-k'), 'k')")
    page.wait_for_timeout(150)
    stanje = page.evaluate(
        """() => ({
             izabrani: [...document.querySelectorAll('.t-tab')]
                         .filter(e => e.getAttribute('aria-selected') === 'true')
                         .map(e => e.id),
             aktivan: document.querySelector('.t-tab.active')?.id || null
           })"""
    )
    assert stanje["izabrani"] == ["tab-btn-k"], (
        f"`aria-selected=\"true\"` stoji na {stanje['izabrani']}, "
        f"a otvoren je {stanje['aktivan']!r}"
    )


def test_navigacija_je_oznacena_kao_tablist(page):
    uloga = page.evaluate(
        "() => document.getElementById('t-tabs-el')?.getAttribute('role')"
    )
    assert uloga == "tablist", (
        f"kontejner navigacije ima `role={uloga!r}` — stavke sa `role=\"tab\"` "
        f"moraju stajati u `tablist`, inače je odnos izgubljen"
    )
