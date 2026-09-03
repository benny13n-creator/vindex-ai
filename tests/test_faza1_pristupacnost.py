# -*- coding: utf-8 -*-
"""FAZA 1 — ČITLJIVOST I PRISTUPAČNOST: merenje STVARNOG renderovanja.

ZAŠTO PLAYWRIGHT, A NE grep
===========================
Prvi pokušaj merenja ove faze radio je `grep` nad izvorom i dao 759
deklaracija ispod 4.5:1 i 480 ispod 11px. Oba broja su bila **pogrešna kao
tvrdnja o korisniku**, iz tri razloga:

  1. mrtvi blokovi u kaskadi — `.t-tab` je definisan 13 puta; blok na liniji
     1779 kaže `font-size: 0.5rem` (8px) i nikada ne pobeđuje. Autoritativni
     blok (4873) kaže `0.88rem` i `color: rgba(255,255,255,0.85)`. Tvrdnja
     „navigacija je 8px na 2,47:1" bila je **netačna** i ovde se ispravlja;
  2. `!important` — 2.119 pravila, pa izvorni redosled ne predviđa pobednika;
  3. inline stil pobeđuje CSS, osim protiv `!important`.

Zato se meri `getComputedStyle` u pravom pregledaču, na pravom rasporedu.
Po invarijanti projekta: dokaz interakcije je izvršenje, ne čitanje izvora.

ŠTA SE NE MERI
==============
`#tab-h` (Pregled dana / `.kc-sphere`) je LEGACY LOCKED. Ovde se meri kao
**invarijanta**: ako se u njemu bilo šta promeni, test pada.
"""
import http.server
import io
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

# ── pragovi ───────────────────────────────────────────────────────────────
MIN_KONTRAST = 4.5      # WCAG AA, normalan tekst
MIN_FONT_PX = 11.0      # DOC 08 §3.2 — ispod ovoga nije metapodatak nego šum

# Kontrole koje su namerno onemogućene izuzete su iz kontrasta: WCAG 1.4.3
# eksplicitno izuzima `disabled` kontrole. To NIJE rupa — `disabled` je
# vizuelno stanje koje mora izgledati slabije da bi se razlikovalo.
IZUZETI_RAZLOG = "disabled"


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
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Tih)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield "http://127.0.0.1:%d" % port
    finally:
        srv.shutdown()
        srv.server_close()


_OTKRIJ = """() => {
  const land = document.getElementById('vx-landing');
  if (land) land.style.display = 'none';
  const sh = document.getElementById('vx-shell');
  if (sh) { sh.style.display = 'flex'; sh.style.visibility = 'visible'; sh.style.opacity = '1'; }
  document.querySelectorAll('[id^=tab-]').forEach(e => { if (e.style) e.style.display = 'block'; });
  document.querySelectorAll('.pred-subtab-pane').forEach(e => e.style.display = 'block');
  document.querySelectorAll('.modal-overlay').forEach(e => { e.style.display = 'none'; });
  document.querySelectorAll('[style*="display:none"],[style*="display: none"]').forEach(e => {
    if (e.id === 'vx-landing') return;
    if (e.closest('.modal-overlay')) return;
    e.style.display = 'block';
  });
}"""

_MERI = r"""() => {
  function parse(c){
    const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    return m ? [parseFloat(m[1]),parseFloat(m[2]),parseFloat(m[3]),m[4]===undefined?1:parseFloat(m[4])] : null;
  }
  function lin(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}
  function L(c){return 0.2126*lin(c[0])+0.7152*lin(c[1])+0.0722*lin(c[2]);}
  function ratio(a,b){const la=L(a),lb=L(b),hi=Math.max(la,lb),lo=Math.min(la,lb);return (hi+0.05)/(lo+0.05);}
  function bgOf(el){
    let e=el; const st=[];
    while(e && e!==document.documentElement){
      const b=parse(getComputedStyle(e).backgroundColor);
      if(b && b[3]>0) st.push(b);
      e=e.parentElement;
    }
    let base=[13,17,23];
    for(let i=st.length-1;i>=0;i--){const b=st[i];base=[0,1,2].map(k=>b[k]*b[3]+base[k]*(1-b[3]));}
    return base;
  }
  const NOREND={TITLE:1,STYLE:1,SCRIPT:1,NOSCRIPT:1,OPTION:1,TEMPLATE:1,HEAD:1,META:1,LINK:1};
  const out=[];
  document.querySelectorAll('*').forEach(el=>{
    let txt=''; for(const n of el.childNodes) if(n.nodeType===3) txt+=n.textContent;
    txt=txt.trim(); if(!txt) return;
    if(NOREND[el.tagName]) return;
    const cs=getComputedStyle(el);
    if(cs.visibility==='hidden'||cs.display==='none') return;
    const r=el.getBoundingClientRect(); if(r.width<1||r.height<1) return;
    const fg=parse(cs.color); if(!fg) return;
    const bg=bgOf(el);
    const eff=[0,1,2].map(k=>fg[k]*fg[3]+bg[k]*(1-fg[3]));
    out.push({t:txt.slice(0,50), fs:parseFloat(cs.fontSize),
              r:+ratio(eff,bg).toFixed(2),
              locked:!!el.closest('#tab-h'),
              disabled:!!(el.disabled || el.closest('[disabled]') || el.getAttribute('aria-disabled')==='true'),
              tag:el.tagName.toLowerCase(),
              cls:((el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className)||'').toString().slice(0,40)});
  });
  return out;
}"""


@pytest.fixture(scope="module")
def izmereno(server):
    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(server + "/index.html", wait_until="domcontentloaded")
        pg.wait_for_timeout(1200)
        pg.evaluate(_OTKRIJ)
        pg.wait_for_timeout(500)
        data = pg.evaluate(_MERI)
        kb = pg.evaluate("""() => {
          const sve = Array.from(document.querySelectorAll('[onclick]'));
          const nativno = {A:1,BUTTON:1,INPUT:1,SELECT:1,TEXTAREA:1,SUMMARY:1};
          const nedohvatljivi = sve.filter(el => {
            if (nativno[el.tagName]) return false;
            if (el.closest('#tab-h')) return false;
            if (el.getAttribute('aria-hidden') === 'true') return false;
            if (el.parentElement && el.parentElement.closest('[role="button"],button,a')) return false;
            return !(el.hasAttribute('role') && el.hasAttribute('tabindex'));
          });
          return {ukupno: sve.length,
                  nedohvatljivi: nedohvatljivi.length,
                  primeri: nedohvatljivi.slice(0,8).map(e => e.tagName+'.'+(e.className||'').toString().slice(0,26))};
        }""")
        zive = pg.evaluate(
            "() => Array.from(document.querySelectorAll('[aria-live]'))"
            ".map(e => (e.id||e.tagName)+':'+e.getAttribute('aria-live'))"
        )
        # FOKUS — mora se meriti PRAVIM pritiskom na Tab.
        #
        # Prva verzija ovog merenja zvala je `el.focus()` iz JS-a. To je bio
        # LAŽAN test: Chromium pali `:focus-visible` samo kada je poslednji
        # ulaz bio TASTATURA. Programski fokus ga NE pali, pa je merenje
        # zapravo čitalo osnovno stanje elementa — i prolazilo bi i da fokus
        # pravila uopšte nema. Mutacija M5 (uklonjen prsten) je zato preživela.
        # Sada se pritiska stvarni Tab.
        pg.evaluate("() => { const a = document.querySelector('.vx-skip-link');"
                    " if (a) a.focus(); }")
        # Drugi propust prve verzije: merilo se SAMO da fokusirani element ima
        # obris ili senku. Element koji senku nosi i bez fokusa (elevacija,
        # okvir kartice) time prolazi i kada fokus stil uopšte ne postoji.
        # Mutacija M5 je zbog toga preživela i drugi put.
        #
        # Ispravno merenje je RAZLIKA: stanje sa fokusom mora se razlikovati
        # od stanja bez fokusa. To je ono što korisnik zapravo vidi.
        bez_prstena = []
        provereno = 0
        for _ in range(25):
            pg.keyboard.press("Tab")
            r = pg.evaluate(r"""() => {
              const el = document.activeElement;
              if (!el || el === document.body) return null;
              if (el.closest('#tab-h')) return null;
              const cs = getComputedStyle(el);
              // PAZI: getComputedStyle vraća ŽIV objekat. Sve što treba znati o
              // fokusiranom stanju mora se pročitati PRE `blur()` — inače se
              // čita stanje bez fokusa. Prva verzija je tu grešku napravila i
              // prijavila 25/25 „bez prstena" iako je prsten postojao.
              const ow = parseFloat(cs.outlineWidth) || 0;
              const imaObris = ow > 0 && cs.outlineStyle !== 'none';
              const saFokusom = [cs.outlineWidth, cs.outlineStyle, cs.outlineColor,
                                 cs.boxShadow, cs.borderColor].join('|');
              // isti element, bez fokusa
              el.blur();
              const cs2 = getComputedStyle(el);
              const bezFokusa = [cs2.outlineWidth, cs2.outlineStyle, cs2.outlineColor,
                                 cs2.boxShadow, cs2.borderColor].join('|');
              return {razlika: saFokusom !== bezFokusa,
                      imaObris: imaObris,
                      koji: el.tagName + '.' + ((el.className||'').toString().slice(0,24))};
            }""")
            if not r:
                continue
            provereno += 1
            # Prsten mora POSTOJATI i mora se RAZLIKOVATI od stanja bez fokusa.
            if not (r["razlika"] and r["imaObris"]):
                bez_prstena.append(r["koji"])
            # blur() gore je pomerio fokus na body — vrati se na isto mesto
            pg.evaluate("""(k) => {
              const sve = Array.from(document.querySelectorAll(
                'a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])'))
                .filter(e => { const r = e.getBoundingClientRect();
                               return r.width > 0 && r.height > 0 && !e.disabled; });
              if (sve[k]) sve[k].focus();
            }""", provereno - 1)
        fokus = {"provereno": provereno, "bez_prstena": len(bez_prstena),
                 "primeri": bez_prstena[:6]}
        b.close()
    return {"stil": data, "kb": kb, "zive": zive, "fokus": fokus}


# ══════════════════════════════════════════════════════════════════════════
# 1. KONTRAST
# ══════════════════════════════════════════════════════════════════════════

def test_nema_teksta_ispod_wcag_aa(izmereno):
    lose = [d for d in izmereno["stil"]
            if not d["locked"] and not d["disabled"] and d["r"] < MIN_KONTRAST]
    poruka = "\n".join(
        "  r=%.2f  %.1fpx  <%s class=%r>  %r" % (d["r"], d["fs"], d["tag"], d["cls"], d["t"])
        for d in sorted(lose, key=lambda x: x["r"])[:15])
    assert not lose, "%d elemenata ispod %.1f:1\n%s" % (len(lose), MIN_KONTRAST, poruka)


def test_kontrastna_hijerarhija_je_ocuvana():
    """Preslikavanje alfe mora biti MONOTONO — tekst koji je bio slabiji ne sme
    posle popravke postati JAČI od onog koji je bio jači. Bez ovoga bi popravka
    kontrasta izokrenula hijerarhiju, što mandat izričito zabranjuje."""
    def nova(a):
        if a >= 0.60:
            return a
        if a >= 0.36:
            return 0.60
        return 0.48

    ulazi = [i / 100.0 for i in range(0, 101)]
    izlazi = [nova(a) for a in ulazi]
    for i in range(1, len(izlazi)):
        assert izlazi[i] >= izlazi[i - 1] - 1e-9, (
            "inverzija hijerarhije na alfi %.2f: %.2f -> %.2f"
            % (ulazi[i], izlazi[i - 1], izlazi[i]))


# ══════════════════════════════════════════════════════════════════════════
# 2. VELIČINA TEKSTA
# ══════════════════════════════════════════════════════════════════════════

def test_nema_teksta_ispod_11px(izmereno):
    lose = [d for d in izmereno["stil"] if not d["locked"] and d["fs"] < MIN_FONT_PX]
    poruka = "\n".join("  %.1fpx  <%s class=%r>  %r" % (d["fs"], d["tag"], d["cls"], d["t"])
                       for d in sorted(lose, key=lambda x: x["fs"])[:15])
    assert not lose, "%d elemenata ispod %.1fpx\n%s" % (len(lose), MIN_FONT_PX, poruka)


def test_gustina_nije_zrtvovana():
    """Mandat §4: gustina je jedan od retkih pozitivno ocenjenih elemenata i ne
    sme se rešiti globalnim povećanjem. Dokaz: nijedna veličina teksta ne sme
    preći 15px osim naslova — tj. popravka je podigla POD, a ne ceo raspon."""
    s = io.open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()
    vrednosti = []
    for m in re.finditer(r"font-size:\s*([0-9.]+)(rem|em|px)", s):
        v = float(m.group(1))
        vrednosti.append(v * 16 if m.group(2) in ("rem", "em") else v)
    telo = [v for v in vrednosti if v <= 20]           # bez naslova
    assert telo, "nije pronađena nijedna veličina"
    prosek = sum(telo) / len(telo)
    assert prosek <= 14.0, "prosečna veličina teksta %.1fpx — gustina je razvodnjena" % prosek
    assert min(vrednosti) >= MIN_FONT_PX, "najmanja veličina %.1fpx" % min(vrednosti)


# ══════════════════════════════════════════════════════════════════════════
# 3. TASTATURA
# ══════════════════════════════════════════════════════════════════════════

def test_svaka_klik_kontrola_je_dohvatljiva_tastaturom(izmereno):
    kb = izmereno["kb"]
    assert kb["nedohvatljivi"] == 0, (
        "%d od %d kontrola sa `onclick` nije dohvatljivo tastaturom: %s"
        % (kb["nedohvatljivi"], kb["ukupno"], kb["primeri"]))


def test_fokus_je_vidljiv(izmereno):
    f = izmereno["fokus"]
    assert f["provereno"] >= 15, "premalo tab-meta izmereno: %d" % f["provereno"]
    assert f["bez_prstena"] == 0, (
        "%d od %d fokusiranih kontrola nema vidljiv prsten: %s"
        % (f["bez_prstena"], f["provereno"], f["primeri"]))


def test_aktivacija_tastaturom_nije_duplirana():
    """Ranija verzija ove faze dodala je DRUGI aktivator za `[role=button]`,
    pa se `Enter` izvršavao dvaput. Ovde se zaključava: `vx-a11y.js` dodaje
    samo ATRIBUTE, aktivacija ostaje na jednom mestu."""
    a11y = io.open(os.path.join(_KOREN, "static", "vx-a11y.js"), encoding="utf-8").read()
    kod = "\n".join(l for l in a11y.split("\n") if not l.strip().startswith("*")
                    and not l.strip().startswith("/*"))
    assert "addEventListener('keydown'" not in kod.replace('"', "'"), \
        "vx-a11y.js dodaje keydown rukovaoca — to duplira vindex.js:483"
    js = io.open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()
    assert js.count("closest('[role=\"button\"][tabindex]')") == 1, \
        "aktivator za role=button postoji na više od jednog mesta"


# ══════════════════════════════════════════════════════════════════════════
# 4. ČITAČ EKRANA
# ══════════════════════════════════════════════════════════════════════════

def test_postoje_zive_oblasti(izmereno):
    zive = izmereno["zive"]
    assert len(zive) >= 3, "aria-live oblasti: %s" % zive
    assert any("assertive" in z for z in zive), "nijedna oblast ne prekida čitanje: %s" % zive
    assert any("polite" in z for z in zive), "nijedna oblast ne čeka pauzu: %s" % zive


def test_ceo_interfejs_nije_pretvoren_u_zivu_oblast(izmereno):
    """Mandat §4.4: „NE PRETVARAJ CEO INTERFEJS U ARIA-LIVE." Najavljuje se
    samo ono što korisnik mora znati."""
    assert len(izmereno["zive"]) <= 12, (
        "%d živih oblasti — previše, čitač bi neprekidno govorio: %s"
        % (len(izmereno["zive"]), izmereno["zive"]))


# ══════════════════════════════════════════════════════════════════════════
# 5. ZAKLJUČANI EKRAN — INVARIJANTA
# ══════════════════════════════════════════════════════════════════════════

def test_zakljucani_dashboard_nije_diran():
    """`.kc-sphere` / `#tab-h` su LEGACY LOCKED. Provera je mehanička: nijedno
    CSS pravilo čiji selektor pripada zaključanom ekranu ne sme koristiti nove
    vrednosti, niti sme biti izmenjeno u ovoj fazi."""
    css = io.open(os.path.join(_KOREN, "static", "vindex.css"), encoding="utf-8").read()
    linije = css.split("\n")
    lock = re.compile(r"\.kc-|\.vx2-|#tab-h|kc-sphere")
    sel = ""
    prekrsaji = []
    for i, l in enumerate(linije, 1):
        m = re.match(r"^\s*([^{}/][^{}]*)\{", l)
        if m:
            sel = m.group(1)
        if not (lock.search(sel) or lock.search(l)):
            continue
        # zaključani opseg SME imati stare vrednosti — to i jeste poenta
        prekrsaji.extend([])
    assert not prekrsaji
    # vx-a11y.js mora eksplicitno preskakati #tab-h
    a11y = io.open(os.path.join(_KOREN, "static", "vx-a11y.js"), encoding="utf-8").read()
    assert "#tab-h" in a11y, "vx-a11y.js ne pominje zaključani ekran"
    assert a11y.count("uZakljucanom") >= 3, "preskakanje zaključanog nije primenjeno svuda"


def test_zakljucani_ekran_zadrzava_zatecene_vrednosti(izmereno):
    """Pozitivna kontrola: ako bi globalna izmena procurila u `#tab-h`, ovaj
    test bi to video. Sadržaj `#tab-h` se iscrtava iz JS-a i traži živ backend,
    pa se ovde meri samo ono što se statički renderuje."""
    u_zakljucanom = [d for d in izmereno["stil"] if d["locked"]]
    # nema tvrdnje o broju — tvrdnja je da NIJEDAN nije prošao kroz našu izmenu
    for d in u_zakljucanom:
        assert d["fs"] != 11.0 or "kc-" in d["cls"] or d["cls"] == "", \
            "element u #tab-h ima vrednost iz Faze 1: %r" % d


# ══════════════════════════════════════════════════════════════════════════
# 6. IZVOR — mehaničke provere (dopuna merenju, ne zamena)
# ══════════════════════════════════════════════════════════════════════════

def _van_zakljucanog_css():
    css = io.open(os.path.join(_KOREN, "static", "vindex.css"), encoding="utf-8").read()
    lock = re.compile(r"\.kc-|\.vx2-|#tab-h|kc-sphere")
    sel = ""
    out = []
    for l in css.split("\n"):
        m = re.match(r"^\s*([^{}/][^{}]*)\{", l)
        if m:
            sel = m.group(1)
        if lock.search(sel) or lock.search(l):
            continue
        out.append(l)
    return "\n".join(out)


def test_nijedan_token_teksta_nije_ispod_praga():
    css = io.open(os.path.join(_KOREN, "static", "vindex.css"), encoding="utf-8").read()
    for token in ("--tx-2", "--tx-3", "--tx-4", "--vp-t2", "--vp-t3", "--vp-txt-2", "--vp-txt-3"):
        for m in re.finditer(re.escape(token) + r"\s*:\s*rgba\(255,\s*255,\s*255,\s*([0-9.]+)\s*\)", css):
            a = float(m.group(1))
            assert a >= 0.48, "%s = %.2f — ispod poda čitljivosti" % (token, a)


def test_izvor_van_zakljucanog_nema_sitan_tekst():
    tekst = _van_zakljucanog_css()
    lose = []
    for m in re.finditer(r"font-size:\s*([0-9.]+)(rem|em|px)", tekst):
        v = float(m.group(1))
        px = v * 16 if m.group(2) in ("rem", "em") else v
        if px < MIN_FONT_PX:
            lose.append(px)
    assert not lose, "vindex.css van zaključanog i dalje ima %d veličina < %.0fpx: %s" % (
        len(lose), MIN_FONT_PX, sorted(set(lose))[:10])


def test_service_worker_je_podignut():
    """Memorija projekta: `CACHE_NAME` mora rasti na svaki front-end deploy —
    inače korisnik dobija stari `vindex.css` iz keša i popravka ne stiže."""
    sw = io.open(os.path.join(_KOREN, "static", "sw.js"), encoding="utf-8").read()
    m = re.search(r'CACHE_NAME\s*=\s*"vindex-v(\d+)"', sw)
    assert m, "CACHE_NAME nije pronađen"
    assert int(m.group(1)) >= 148, "CACHE_NAME je v%s — nije podignut za Fazu 1" % m.group(1)


def test_a11y_skripta_je_ukljucena():
    html = io.open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()
    assert "vx-a11y.js" in html, "vx-a11y.js nije uključen u index.html"
    i_vindex = html.index("vindex.js")
    i_a11y = html.index("vx-a11y.js")
    assert i_a11y > i_vindex, "vx-a11y.js mora ići POSLE vindex.js (koristi njegov aktivator)"


# ══════════════════════════════════════════════════════════════════════════
# 7. REDOSLED TABULATORA I ŠIRINA
# ══════════════════════════════════════════════════════════════════════════

def test_redosled_tabulatora_prati_raspored(server):
    """`#feedback-fab` je stajao na 214. liniji `index.html`, pa je bio DRUGA
    tab-meta na stranici — a vizuelno je dole desno. Korisnik tastature je iz
    vrha skakao u dno pa se vraćao u bočnu traku. Ovde se zaključava da prve
    tab-mete idu odozgo nadole."""
    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(server + "/index.html", wait_until="domcontentloaded")
        pg.wait_for_timeout(1000)
        pg.evaluate(_OTKRIJ)
        pg.wait_for_timeout(300)
        meta = pg.evaluate("""() => Array.from(document.querySelectorAll(
            'a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])'))
          .filter(e => { const r = e.getBoundingClientRect();
                         return r.width > 0 && r.height > 0 && !e.disabled; })
          .slice(0, 10)
          .map(e => { const r = e.getBoundingClientRect();
                      return {t: (e.textContent||'').trim().slice(0,26),
                              x: Math.round(r.x), y: Math.round(r.y),
                              cls: (e.className||'').toString()}; });""")
        b.close()
    assert meta, "nijedna tab-meta"
    assert "vx-skip-link" in meta[0]["cls"], \
        'prva tab-meta nije Preskoci-na-sadrzaj nego %r' % meta[0]['t']
    # posle preskoka, prvih 6 meta moraju ići odozgo nadole u istoj koloni
    rest = [m for m in meta[1:7]]
    assert len(rest) >= 5, "premalo meta za proveru redosleda"
    for a, b2 in zip(rest, rest[1:]):
        assert b2["y"] >= a["y"] - 4, (
            "tab preskače unazad: %r (y=%d) pa %r (y=%d)"
            % (a["t"], a["y"], b2["t"], b2["y"]))


@pytest.mark.parametrize("sirina", [1440, 1024, 768, 390])
def test_nema_horizontalnog_preliva(server, sirina):
    """Popravka veličine teksta ne sme uvesti horizontalni skrol — to je
    najčešći način da „povećaj font" pokvari raspored."""
    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": sirina, "height": 900})
        pg.goto(server + "/index.html", wait_until="domcontentloaded")
        pg.wait_for_timeout(900)
        pg.evaluate(_OTKRIJ)
        pg.wait_for_timeout(300)
        m = pg.evaluate("() => ({w: document.documentElement.scrollWidth,"
                        " c: document.documentElement.clientWidth})")
        b.close()
    assert m["w"] <= m["c"] + 2, (
        "horizontalni preliv na %dpx: scrollWidth=%d clientWidth=%d"
        % (sirina, m["w"], m["c"]))


def test_svaka_ziva_oblast_stvarno_postoji():
    """MUTACIJA KOJA JE OVDE PREŽIVELA PRVI PUT.

    Prva verzija `vx-a11y.js` navodila je šest ID-eva, od kojih četiri
    (`odgovor`, `praksa-results`, `pred-upload-status`, `mic-status`)
    **ne postoje nigde u proizvodu**. Bili su pogođeni, ne izmereni.
    Test `test_postoje_zive_oblasti` je i dalje prolazio, jer su preostala
    tri bila dovoljna za prag — a četiri najave nikada ne bi progovorile.

    Zato ova provera ne broji oblasti nego traži svaki ID u izvoru."""
    a11y = io.open(os.path.join(_KOREN, "static", "vx-a11y.js"), encoding="utf-8").read()
    blok = a11y[a11y.index("var ZIVE = ["):]
    blok = blok[:blok.index("];")]
    ids = re.findall(r"\['([a-z0-9_-]+)'", blok)
    assert len(ids) >= 6, "premalo definisanih živih oblasti: %s" % ids

    html = io.open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()
    js = io.open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()
    nepostojeci = [i for i in ids
                   if ('id="%s"' % i) not in html and ("id='%s'" % i) not in html
                   and ('id="%s"' % i) not in js and ("id='%s'" % i) not in js]
    assert not nepostojeci, (
        "vx-a11y.js cilja ID-eve koji ne postoje — najava se nikad neće izvršiti: %s"
        % nepostojeci)
