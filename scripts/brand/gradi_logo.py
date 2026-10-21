"""Vindex znak: rimsko V, jonski stub u otvoru, lovorove grane. Tanke, oštre linije.

Izlaz: SVG fajlovi (znak, horizontalni i uspravni lockup, tamna i svetla površina).
Slova VINDEX su pretvorena u putanje iz fonta Cinzel (SIL OFL 1.1), pa ne zavise od fontova.

Pokretanje (samo za razvoj; `pip install fonttools`):
    python scripts/brand/gradi_logo.py <izlazni-folder>
U `frontend-v2-ng/brand/` idu `vindex-lockup-tamna.svg` i `vindex-lockup-svetla.svg`.
PNG ikone u `static/` (favicon-vindex-v4-*, icon-*-v4) su iscrtane iz `vindex-ikona-tamna.svg`
(favicon) i `vindex-znak-tamna.svg` (ikona aplikacije) na podlozi #0B0B0B, u Chromium-u.
"""
import math, sys
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.instancer import instantiateVariableFont

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
FONT = Path(__file__).parent / "Cinzel.ttf"   # SIL OFL 1.1, Cinzel-OFL.txt

BOJE = {
    "tamna": {"v": "#ECE6D8", "zlato": "#C4A46B", "tekst": "#ECE6D8"},   # na crnoj
    "svetla": {"v": "#141414", "zlato": "#8E6B34", "tekst": "#141414"},  # na boji kosti
}

def f(x): return f"{x:.2f}".rstrip("0").rstrip(".")

def P(pts): return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"

# ── Geometrija znaka (viewBox 0 0 200 200) ───────────────────────────────────
VT, AX, AY = 44.0, 100.0, 174.0          # vrh krakova, teme V
LO, LI, RI, RO = 50.0, 61.5, 143.0, 150.0   # levi krak deblji (rimski kontrast), desni tanak
dl, dr = (AX - LO, AY - VT), (AX - RO, AY - VT)
t = (RI - LI) / (dl[0] - dr[0])
UX, UY = LI + dl[0] * t, VT + dl[1] * t      # unutrašnje teme
CX = (LI + RI) / 2 + (UX - (LI + RI) / 2) * 0.5  # osa stuba = sredina otvora

def V_putanja():
    s = 1.6   # debljina serifa
    return " ".join([
        P([(LO, VT), (LI, VT), (UX, UY), (RI, VT), (RO, VT), (AX, AY)]),
        P([(LO - 9, VT - s), (LI + 6, VT - s), (LI + 6, VT), (LO - 9, VT)]),   # serif levo
        P([(RI - 5, VT - s), (RO + 8, VT - s), (RO + 8, VT), (RI - 5, VT)]),   # serif desno
    ])

def stub():
    d = []
    w, top, dno = 25.0, 39.0, 150.0
    x0 = CX - w / 2
    # žlebovi: 5 traka sa uskim razmakom (oštre ivice, bez obrisa)
    n, raz = 5, 1.5
    tr = (w - raz * (n - 1)) / n
    for i in range(n):
        a = x0 + i * (tr + raz)
        d.append(P([(a, top), (a + tr, top), (a + tr, dno), (a, dno)]))
    # vrat
    d.append(P([(CX - 15, top - 3.2), (CX + 15, top - 3.2), (CX + 15, top - 1.6), (CX - 15, top - 1.6)]))
    # ehinus: blago zakrivljen jastuk
    d.append(f"M{f(CX-22)} {f(top-11)} L{f(CX+22)} {f(top-11)} Q{f(CX+20)} {f(top-5)} {f(CX+14)} {f(top-4.4)} "
             f"L{f(CX-14)} {f(top-4.4)} Q{f(CX-20)} {f(top-5)} {f(CX-22)} {f(top-11)} Z")
    # abakus
    d.append(P([(CX - 30, top - 16), (CX + 30, top - 16), (CX + 30, top - 12.4), (CX - 30, top - 12.4)]))
    return " ".join(d)

def voluta(cx, cy, smer):
    """Spirala tankom linijom (kao obris), smer=-1 levo, +1 desno."""
    tacke = []
    for i in range(0, 64):
        a = i / 63 * 2.6 * math.pi
        r = 4.6 * (1 - i / 63 * 0.8)
        tacke.append((cx + smer * r * math.cos(a + math.pi), cy + r * math.sin(a + math.pi)))
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in tacke)

def bez(p0, p1, p2, p3, t):
    m = 1 - t
    return tuple(m**3 * a + 3 * m * m * t * b + 3 * m * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))

def bez_d(p0, p1, p2, p3, t):
    m = 1 - t
    return tuple(3 * m * m * (b - a) + 6 * m * t * (c - b) + 3 * t * t * (d - c) for a, b, c, d in zip(p0, p1, p2, p3))

def list(px, py, ugao, duz, sir):
    """Lovorov list: dva luka koja se sastaju u oštrom vrhu."""
    ca, sa = math.cos(ugao), math.sin(ugao)
    def tr(u, v): return (px + u * ca - v * sa, py + u * sa + v * ca)
    a, b = tr(0, 0), tr(duz, 0)
    c1, c2 = tr(duz * 0.35, sir), tr(duz * 0.75, sir * 0.75)
    d1, d2 = tr(duz * 0.75, -sir * 0.75), tr(duz * 0.35, -sir)
    return (f"M{f(a[0])} {f(a[1])} C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(b[0])} {f(b[1])} "
            f"C{f(d1[0])} {f(d1[1])} {f(d2[0])} {f(d2[1])} {f(a[0])} {f(a[1])} Z")

def grana(ogledalo):
    """Leva grana; desna je ogledalo oko x=100."""
    p0, p1, p2, p3 = (90, 186), (52, 180), (24, 140), (34, 76)
    stablo = []
    listovi = []
    for i in range(41):
        stablo.append(bez(p0, p1, p2, p3, i / 40))
    N = 9
    for k in range(N):
        tt = 0.1 + k * 0.84 / (N - 1)
        x, y = bez(p0, p1, p2, p3, tt)
        dx, dy = bez_d(p0, p1, p2, p3, tt)
        ug = math.atan2(dy, dx)
        duz = 17 - k * 0.9
        sir = 3.6 - k * 0.12
        for strana in (1, -1):
            if strana == 1 and k % 2: pass
            # spoljašnji list (leva strana grane = dalje od V) je veći; unutrašnji manji i pomeren
            if strana == -1:
                listovi.append(list(x, y, ug - 0.62, duz, sir))
            else:
                x2, y2 = bez(p0, p1, p2, p3, min(tt + 0.045, 1))
                listovi.append(list(x2, y2, ug + 0.55, duz * 0.82, sir * 0.9))
    # vršni list
    x, y = bez(p0, p1, p2, p3, 1.0); dx, dy = bez_d(p0, p1, p2, p3, 1.0)
    listovi.append(list(x, y, math.atan2(dy, dx), 11, 2.6))
    stablo_d = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in stablo)
    if ogledalo:
        def m(d):
            import re
            nums = re.findall(r"[A-Z]|-?\d+(?:\.\d+)?", d)
            out, xs = [], True
            for tok in nums:
                if tok.isalpha(): out.append(tok); xs = True; continue
                out.append(f(200 - float(tok)) if xs else tok); xs = not xs
            return " ".join(out)
        return m(stablo_d), [m(l) for l in listovi]
    return stablo_d, listovi

def ikona_telo(b):
    vol = voluta(CX - 22, 39 - 8.2, -1) + " " + voluta(CX + 22, 39 - 8.2, 1)
    return znak_svg_telo(b, lovor=False)

def znak_svg_telo(b, lovor=True):
    gl, ll = grana(False); gd, ld = grana(True)
    vol = voluta(CX - 22, 39 - 8.2, -1) + " " + voluta(CX + 22, 39 - 8.2, 1)
    lov = (f'''<g fill="none" stroke="{b['zlato']}" stroke-width="1.2" stroke-linecap="round"><path d="{gl}"/><path d="{gd}"/></g>
<g fill="{b['zlato']}"><path d="{' '.join(ll)}"/><path d="{' '.join(ld)}"/></g>''') if lovor else ""
    return f'''<defs><mask id="vx-otvor" maskUnits="userSpaceOnUse" x="0" y="0" width="200" height="200">
<rect width="200" height="200" fill="#fff"/><path d="{V_putanja()}" fill="#000" stroke="#000" stroke-width="5" stroke-linejoin="miter"/></mask>
<clipPath id="vx-zaV"><path d="M0 0 L200 0 L200 {f(VT)} L{f(RI)} {f(VT)} L{f(UX)} {f(UY)} L{f(LI)} {f(VT)} L0 {f(VT)} Z"/></clipPath></defs>
<g fill="{b['zlato']}" mask="url(#vx-otvor)" clip-path="url(#vx-zaV)"><path d="{stub()}"/></g>
<path d="{vol}" fill="none" stroke="{b['zlato']}" stroke-width="1.1" stroke-linecap="round"/>
{lov}
<path d="{V_putanja()}" fill="{b['v']}"/>'''

# ── Slova ────────────────────────────────────────────────────────────────────
_font = instantiateVariableFont(TTFont(FONT), {"wght": 420})
_gs, _cmap, _hm = _font.getGlyphSet(), _font.getBestCmap(), _font["hmtx"]
_UPM = _font["head"].unitsPerEm
_CAP = _font["OS/2"].sCapHeight

def rec(tekst, visina_slova, razmak_em, x0, osnovna):
    """Putanja reči: visina_slova = visina verzala u jedinicama izlaza."""
    s = visina_slova / _CAP
    pen = SVGPathPen(_gs)
    x = 0.0
    for i, ch in enumerate(tekst):
        g = _cmap[ord(ch)]
        tp = TransformPen(pen, (s, 0, 0, -s, x0 + x * s, osnovna))
        _gs[g].draw(tp)
        x += _hm[g][0] + (razmak_em * _UPM if i < len(tekst) - 1 else 0)
    # stvarna širina: bez bočnog prostora prvog i poslednjeg slova
    bp = BoundsPen(_gs); x = 0.0
    for i, ch in enumerate(tekst):
        g = _cmap[ord(ch)]
        tp = TransformPen(bp, (1, 0, 0, 1, x, 0)); _gs[g].draw(tp)
        x += _hm[g][0] + (razmak_em * _UPM if i < len(tekst) - 1 else 0)
    xmin, _, xmax, _ = bp.bounds
    return pen.getCommands(), xmin * s, xmax * s

def zapisi(ime, w, h, telo):
    (OUT / ime).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}" width="{f(w)}" height="{f(h)}">'
                           f'<title>Vindex</title>{telo}</svg>\n', encoding="utf-8")

for tema, b in BOJE.items():
    # 0) ikona: V i stub, bez lovora, isečeno na kvadrat oko znaka
    zapisi(f"vindex-ikona-{tema}.svg", 200, 200, f'<g transform="translate(100 100) scale(1.32) translate(-100 -104)">{ikona_telo(b)}</g>')
    # 1) samo znak
    zapisi(f"vindex-znak-{tema}.svg", 200, 200, znak_svg_telo(b))
    # 2) horizontalni lockup: znak 200 visine (sa 6 jed. vazduha), reč desno
    cap = 64.0
    d, xmin, xmax = rec("VINDEX", cap, 0.16, 0, 0)
    x_rec = 214 - xmin
    sir = math.ceil(x_rec + xmax + 6)
    osn = 100 + cap / 2 + 4
    d, _, _ = rec("VINDEX", cap, 0.16, x_rec, osn)
    zapisi(f"vindex-lockup-{tema}.svg", sir, 200,
           f'<g transform="translate(0 0)">{znak_svg_telo(b)}</g><path d="{d}" fill="{b["tekst"]}"/>')
    # 3) uspravni lockup: znak gore, reč i tanka linija dole
    cap2 = 44.0
    d2, xmin2, xmax2 = rec("VINDEX", cap2, 0.2, 0, 0)
    W = 320; sw = xmax2 - xmin2
    d2, _, _ = rec("VINDEX", cap2, 0.2, (W - sw) / 2 - xmin2, 262)
    zapisi(f"vindex-uspravni-{tema}.svg", W, 290,
           f'<g transform="translate(60 6)">{znak_svg_telo(b)}</g><path d="{d2}" fill="{b["tekst"]}"/>'
           f'<rect x="{f(W/2-18)}" y="276" width="36" height="1.2" fill="{b["zlato"]}"/>')
print("ok", CX, UX, UY)
