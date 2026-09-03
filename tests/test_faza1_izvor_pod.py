# -*- coding: utf-8 -*-
"""FAZA 1 — DETERMINISTIČKA DOPUNA MERENJU U PREGLEDAČU.

ZAŠTO OVAJ FAJL POSTOJI
=======================
Mutacija **M1** je preživela prvi prolaz: vraćanje JEDNE vrednosti `color` sa
`0.48` na `0.28` u `index.html` nije oborilo nijedan test.

Uzrok nije bio loš prag nego **pokrivenost**. Playwright meri samo ono što se
statički renderuje — 221 element. Najveći deo interfejsa (tabele, liste,
rezultati) nastaje iz `vindex.js` tek kada stignu podaci sa servera, pa se u
statičkom merenju nikada ne pojavi.

Merenje u pregledaču ostaje **glavni** dokaz: ono jedino zna ko pobeđuje u
kaskadi od 13 definicija `.t-tab` i 2.119 `!important` pravila. Ali ono ne
pokriva ceo proizvod. Zato mu treba deterministička dopuna — ovaj fajl.

Ova dva testa NE zamenjuju merenje. Oni zatvaraju rupu koju merenje ima.
"""
import io
import os
import re

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

POD_ALFE = 0.48       # 4.99 : 1 na #0d1117
POD_FONTA = 11.0      # px

# Zaključani ekran: `.kc-sphere` / `#tab-h`. Isti opsezi kojima je vođena
# transformacija u Fazi 1 — ako se ovde razmimoiđu, test bi lagao.
CSS_ZAKLJUCANO = re.compile(r"\.kc-|\.vx2-|#tab-h|kc-sphere")
JS_ZAKLJUCANO = [(1335, 1377), (1496, 1506), (1519, 1521), (1539, 1578),
                 (1591, 1631), (1657, 1820), (1843, 1856), (1858, 1937),
                 (1940, 2063), (2066, 2073)]

# `color:` kao PRAVO svojstvo. Negativni pogled unazad je obavezan: bez njega
# regex hvata i `border-color:` i `background-color:`, što je prvo merenje ove
# faze i uradilo — i dalo 829 umesto 759 pogodaka.
BELA = re.compile(r"(?<![-a-zA-Z])color:\s*rgba\(255,\s*255,\s*255,\s*([01]?\.?\d+)\s*\)")
FONT = re.compile(r"font-size:\s*([0-9.]+)(rem|em|px)")


def _linije(rel):
    return io.open(os.path.join(_KOREN, rel), encoding="utf-8").read().split("\n")


def _u_pikselima(m):
    v = float(m.group(1))
    return v * 16 if m.group(2) in ("rem", "em") else v


def _css_van_zakljucanog():
    """Vraća (broj_linije, tekst) za svaku CSS liniju izvan zaključanog ekrana."""
    sel = ""
    for i, l in enumerate(_linije("static/vindex.css"), 1):
        m = re.match(r"^\s*([^{}/][^{}]*)\{", l)
        if m:
            sel = m.group(1)
        if CSS_ZAKLJUCANO.search(sel) or CSS_ZAKLJUCANO.search(l):
            continue
        yield i, l


def _js_van_zakljucanog():
    for i, l in enumerate(_linije("static/vindex.js"), 1):
        if any(a <= i <= b for a, b in JS_ZAKLJUCANO):
            continue
        yield i, l


def test_nijedna_deklaracija_teksta_nije_ispod_poda_alfe():
    prekrsaji = []
    for i, l in enumerate(_linije("index.html"), 1):
        for m in BELA.finditer(l):
            if float(m.group(1)) < POD_ALFE:
                prekrsaji.append("index.html:%d  alfa=%s" % (i, m.group(1)))
    for i, l in _css_van_zakljucanog():
        for m in BELA.finditer(l):
            if float(m.group(1)) < POD_ALFE:
                prekrsaji.append("vindex.css:%d  alfa=%s" % (i, m.group(1)))
    for i, l in _js_van_zakljucanog():
        for m in BELA.finditer(l):
            if float(m.group(1)) < POD_ALFE:
                prekrsaji.append("vindex.js:%d  alfa=%s" % (i, m.group(1)))
    assert not prekrsaji, "%d deklaracija ispod poda alfe %.2f:\n  %s" % (
        len(prekrsaji), POD_ALFE, "\n  ".join(prekrsaji[:15]))


def test_nijedna_velicina_teksta_nije_ispod_poda():
    prekrsaji = []
    for i, l in enumerate(_linije("index.html"), 1):
        for m in FONT.finditer(l):
            if _u_pikselima(m) < POD_FONTA:
                prekrsaji.append("index.html:%d  %.1fpx" % (i, _u_pikselima(m)))
    for i, l in _css_van_zakljucanog():
        for m in FONT.finditer(l):
            if _u_pikselima(m) < POD_FONTA:
                prekrsaji.append("vindex.css:%d  %.1fpx" % (i, _u_pikselima(m)))
    for i, l in _js_van_zakljucanog():
        for m in FONT.finditer(l):
            if _u_pikselima(m) < POD_FONTA:
                prekrsaji.append("vindex.js:%d  %.1fpx" % (i, _u_pikselima(m)))
    assert not prekrsaji, "%d veličina ispod %.0fpx:\n  %s" % (
        len(prekrsaji), POD_FONTA, "\n  ".join(prekrsaji[:15]))


def test_smanjeno_kretanje_je_globalno():
    """Mutacija M11 nije oborila nijedan test — `prefers-reduced-motion` nije
    bio meren nigde. Pre Faze 1 postojala su 2 LOKALNA bloka; animacija koju
    korisnik nije mogao da isključi nije stilsko pitanje nego pristupačnost
    (vestibularni poremećaji)."""
    css = io.open(os.path.join(_KOREN, "static", "vindex.css"), encoding="utf-8").read()
    assert "@media (prefers-reduced-motion: reduce)" in css, \
        "nema nijednog bloka za smanjeno kretanje"
    i = css.rindex("@media (prefers-reduced-motion: reduce)")
    odsecak = css[i:i + 500]
    assert "*, *::before, *::after" in odsecak, \
        "blok postoji ali nije globalan — pogađa samo pojedine selektore"
    assert "animation-duration" in odsecak and "transition-duration" in odsecak, \
        "globalni blok ne gasi ni animacije ni prelaze"


def test_zakljucani_ekran_je_stvarno_izuzet_a_ne_prazan():
    """Pozitivna kontrola nad samim izuzećem.

    Ako bi regex za zaključani ekran slučajno prestao da pogađa (npr. neko
    preimenuje `.kc-` u `.dash-`), gornja dva testa bi počela da traže i
    zaključani ekran i pala bi — ili, gore, izuzeće bi obuhvatilo ceo fajl i
    testovi bi prolazili prazni. Ovde se meri da je izuzeće **usko**."""
    ukupno = len(_linije("static/vindex.css"))
    van = sum(1 for _ in _css_van_zakljucanog())
    izuzeto = ukupno - van
    assert izuzeto > 200, (
        "izuzeto je samo %d linija — obrazac za zaključani ekran verovatno "
        "više ne pogađa `.kc-*`" % izuzeto)
    assert izuzeto < ukupno * 0.35, (
        "izuzeto je %d od %d linija (%.0f%%) — izuzeće je preširoko, testovi "
        "iznad mere premalo" % (izuzeto, ukupno, 100.0 * izuzeto / ukupno))

    js_izuzeto = sum(b - a + 1 for a, b in JS_ZAKLJUCANO)
    js_ukupno = len(_linije("static/vindex.js"))
    assert js_izuzeto < js_ukupno * 0.05, (
        "u vindex.js je izuzeto %d od %d linija — previše" % (js_izuzeto, js_ukupno))
