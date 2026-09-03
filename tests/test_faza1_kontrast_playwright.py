# -*- coding: utf-8 -*-
"""FAZA 1 — pristupacnost i citljivost: TAMNA I SVETLA TEMA.

Ovo NIJE staticka analiza CSS-a. Stranica se stvarno iscrtava u Chromium-u,
tema se postavlja kroz produkcioni put (localStorage -> vindex.js sam dodaje
klasu), a boja se cita iz `getComputedStyle` pa kompozituje kroz stvarni lanac
predaka. Merenje, ne citanje izvora, je arbitar: `.t-tab` ima 17 konkurentskih
`color` deklaracija i nijedno citanje izvora ne kaze koja pobedjuje.

Tri gejta:
  1. KONTRAST    -- nijedan vidljiv tekstualni cvor ispod WCAG 2.1 AA praga.
  2. HIJERARHIJA -- tokenska lestvica ima 4 razdvojena nivoa u OBE teme.
  3. FOKUS       -- svako zaustavljanje Tab-a menja piksele (dokaz snimkom).
"""
import http.server
import io
import os
import socket
import socketserver
import threading

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "kontrast_motor.js")

playwright_api = pytest.importorskip("playwright.sync_api", reason="playwright nije instaliran")

TABOVI = ["h", "p", "k", "kal", "aiws", "s", "dok", "zadaci-g", "fin", "kanc", "settings"]

SONDE = (
    "<span class='vx-probe-tx1' style='color:var(--tx-1)'>Aa</span>"
    "<span class='vx-probe-tx2' style='color:var(--tx-2)'>Aa</span>"
    "<span class='vx-probe-tx3' style='color:var(--tx-3)'>Aa</span>"
    "<span class='vx-probe-tx4' style='color:var(--tx-4)'>Aa</span>"
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
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Tih)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield "http://127.0.0.1:%d" % port
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(scope="module")
def motor():
    return io.open(_MOTOR, encoding="utf-8").read()


def _stranica(pw, server, tema):
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('vx_theme','%s')}catch(e){}" % tema)
    pg = ctx.new_page()
    pg.goto(server + "/index.html", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    stvarna = pg.evaluate("document.body.className")
    assert ("light-theme" in stvarna) == (tema == "light"), (
        "tema nije primenjena kroz produkcioni put: trazeno=%s body=%r" % (tema, stvarna))
    return b, pg


def _u_aplikaciju(pg):
    """Ulazak kroz STVARNU funkciju koja se izvrsava i posle prave prijave."""
    pg.evaluate("""()=>{
        window.currentUser = {email:'advokat@kancelarija.rs', id:'u-faza1'};
        var nu=document.getElementById('nav-user'); if(nu) nu.style.display='flex';
        if(typeof updateAuthUI==='function') updateAuthUI();
    }""")
    pg.wait_for_timeout(500)
    vidi = pg.evaluate("()=>{var s=document.getElementById('vx-shell');"
                       "return s?getComputedStyle(s).display:'NEMA'}")
    assert vidi not in ("none", "NEMA"), "aplikacija se nije otvorila (vx-shell=%r)" % vidi


# ── GEJT 1: KONTRAST ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("tema", ["dark", "light"])
def test_kontrast_wcag_aa(server, motor, tema):
    with playwright_api.sync_playwright() as pw:
        b, pg = _stranica(pw, server, tema)
        try:
            pg.add_script_tag(content=motor)
            pali = [x for x in pg.evaluate("()=>window.__vxContrast.skeniraj('LANDING')")
                    if x["pada"]]
            _u_aplikaciju(pg)
            for k in TABOVI:
                pg.evaluate(
                    "(k)=>{var b=document.getElementById('tab-btn-'+k);"
                    "if(b&&typeof setTab==='function'){try{setTab(b,k)}catch(e){}}"
                    "var p=document.getElementById('tab-'+k); if(p)p.style.display='block';}", k)
                pg.wait_for_timeout(200)
                pali += [x for x in pg.evaluate("(k)=>window.__vxContrast.skeniraj(k)", k)
                         if x["pada"]]
        finally:
            b.close()

    jedinstveni = {}
    for x in pali:
        jedinstveni[(x["putanja"], x["tekst"])] = x
    if jedinstveni:
        opis = "\n".join(
            "  %5.2f:1 (prag %s)  %s  %r  fg=%s bg=%s"
            % (x["odnos"], x["prag"], x["putanja"][-60:], x["tekst"][:40],
               x["fg_efektivno"], x["bg_efektivno"])
            for x in sorted(jedinstveni.values(), key=lambda y: y["odnos"])[:25])
        pytest.fail("tema=%s: %d tekstualnih cvorova ispod WCAG 2.1 AA\n%s"
                    % (tema, len(jedinstveni), opis))


# ── GEJT 2: HIJERARHIJA ──────────────────────────────────────────────────────

@pytest.mark.parametrize("tema", ["dark", "light"])
def test_tokenska_lestvica_ima_cetiri_razdvojena_nivoa(server, motor, tema):
    """Pre Faze 1 su u SVETLOJ temi sva cetiri nivoa bila IDENTICNA (12.51:1)
    jer je `body.light-theme *` gazio svaki token -- hijerarhija nije postojala."""
    with playwright_api.sync_playwright() as pw:
        b, pg = _stranica(pw, server, tema)
        try:
            pg.add_script_tag(content=motor)
            pg.evaluate("""(html)=>{var d=document.createElement('div');
                d.id='vx-probe-host'; d.style.cssText='position:fixed;left:0;top:0;width:200px;';
                d.innerHTML=html; document.body.appendChild(d);}""", SONDE)
            pg.wait_for_timeout(150)
            red = pg.evaluate(
                "()=>window.__vxContrast.lestvica({l:['.vx-probe-tx1','.vx-probe-tx2',"
                "'.vx-probe-tx3','.vx-probe-tx4']}).l")
        finally:
            b.close()

    assert all(not r.get("nema") for r in red), "sonde nisu iscrtane: %r" % red
    odnosi = [r["odnos"] for r in red]
    for i, o in enumerate(odnosi):
        assert o >= 4.5, "tema=%s: --tx-%d je %.2f:1, ispod 4.5:1 (%r)" % (tema, i + 1, o, odnosi)
    for i in range(3):
        assert odnosi[i] - odnosi[i + 1] >= 1.5, (
            "tema=%s: nivoi --tx-%d i --tx-%d se ne razlikuju dovoljno (%.2f vs %.2f) -- "
            "hijerarhija je sabijena: %r" % (tema, i + 1, i + 2, odnosi[i], odnosi[i + 1], odnosi))


# ── GEJT 3: FOKUS ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tema", ["dark", "light"])
def test_svako_zaustavljanje_taba_ima_vidljiv_fokus(server, tema):
    """Dokaz je PIKSEL, ne CSS vrednost: analiza `outline` vrednosti je u prvom
    prolazu dala dva lazna pozitiva (prsten iznad providne pozadine)."""
    Image = pytest.importorskip("PIL.Image", reason="Pillow nije instaliran")

    def razlika(a, b):
        ia = Image.open(io.BytesIO(a)).convert("RGB")
        ib = Image.open(io.BytesIO(b)).convert("RGB")
        if ia.size != ib.size:
            return 100.0
        pa, pb = ia.load(), ib.load()
        n = razl = 0
        for y in range(ia.size[1]):
            for x in range(ia.size[0]):
                n += 1
                if max(abs(pa[x, y][i] - pb[x, y][i]) for i in range(3)) > 12:
                    razl += 1
        return 100.0 * razl / max(n, 1)

    nevidljivi = []
    with playwright_api.sync_playwright() as pw:
        b, pg = _stranica(pw, server, tema)
        try:
            _u_aplikaciju(pg)
            pg.evaluate("()=>document.body.focus()")
            vidjeni = set()
            for _ in range(60):
                pg.keyboard.press("Tab")
                meta = pg.evaluate("""()=>{var e=document.activeElement;
                    if(!e||e===document.body)return null;
                    var r=e.getBoundingClientRect(); if(r.width<2||r.height<2)return null;
                    e.setAttribute('data-fz','1');
                    var kl=(e.className&&typeof e.className==='string'&&e.className.trim())
                           ? '.'+e.className.trim().split(/\\s+/)[0] : '';
                    return {opis:(e.tagName+(e.id?'#'+e.id:'')+kl).slice(0,52),
                            x:r.x,y:r.y,w:r.width,h:r.height};}""")
                if not meta or meta["opis"] in vidjeni:
                    pg.evaluate("()=>{var e=document.querySelector('[data-fz]');"
                                "if(e)e.removeAttribute('data-fz');}")
                    continue
                vidjeni.add(meta["opis"])
                M = 6
                klip = {"x": max(0, meta["x"] - M), "y": max(0, meta["y"] - M),
                        "width": min(1440 - max(0, meta["x"] - M), meta["w"] + 2 * M),
                        "height": min(900 - max(0, meta["y"] - M), meta["h"] + 2 * M)}
                if klip["width"] < 3 or klip["height"] < 3:
                    pg.evaluate("()=>{var e=document.querySelector('[data-fz]');"
                                "if(e)e.removeAttribute('data-fz');}")
                    continue
                sa = pg.screenshot(clip=klip)
                pg.evaluate("()=>{var e=document.querySelector('[data-fz]'); if(e)e.blur();}")
                pg.wait_for_timeout(50)
                bez = pg.screenshot(clip=klip)
                if razlika(bez, sa) < 1.0:
                    nevidljivi.append(meta["opis"])
                pg.evaluate("""()=>{var e=document.querySelector('[data-fz]');
                    if(e){e.removeAttribute('data-fz'); e.focus({preventScroll:true});}}""")
            assert vidjeni, "nijedno zaustavljanje Tab-a nije zabelezeno"
        finally:
            b.close()

    assert not nevidljivi, ("tema=%s: %d kontrola ne menja nijedan piksel pri fokusu "
                            "tastaturom: %s" % (tema, len(nevidljivi), ", ".join(nevidljivi)))
