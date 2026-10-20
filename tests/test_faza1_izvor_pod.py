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

Testovi alfe i kretanja NE zamenjuju merenje; zatvaraju rupu koju merenje ima.
Veličina teksta se od NS4 meri u pregledaču (vidi `test_nijedna_velicina_teksta_nije_ispod_poda`).
"""
import io
import os
import re

import pytest

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


# ── VELIČINA TEKSTA: meri se ono što korisnik vidi ──────────────────────────
#
# Prethodna verzija je brojala SIROVE deklaracije `font-size` u izvoru (567) i bila
# je crvena od uvođenja (7eb32be1). Deklaracija ne dokazuje prikaz: pregazi je drugo
# pravilo, ne pogađa nijedan prikazan element ili pripada skrivenom stanju. Odluka
# osnivača (NS4, opcija 2): ugovor je EFEKTIVNA veličina vidljivog teksta u stvarnim
# legacy scenarijima, merena u Chromium-u kroz `getComputedStyle`. Prag ostaje 11px.
#
# Scenariji (tests/assets/font_pod_merenje.py): početni ekran, svaki tab aplikacije,
# lista i detalj predmeta i lista klijenata sa determinističkim podacima — tamna i
# svetla tema, desktop i mobilni prikaz, zatvorena mreža. Merenje se izvršava kao
# zaseban proces interpretera sa Playwright-om (`VINDEX_PLAYWRIGHT_PYTHON`, inače
# tekući). Nedostupan pregledač ili neučitan scenario je NEUSPEH, nikada preskok.

_MERENJE = os.path.join(_KOREN, "tests", "assets", "font_pod_merenje.py")


def _meri(*argumenti):
    import json
    import subprocess
    import sys

    py = os.environ.get("VINDEX_PLAYWRIGHT_PYTHON") or sys.executable
    r = subprocess.run([py, _MERENJE] + list(argumenti), capture_output=True, text=True, timeout=600)
    izlaz = r.stdout.strip().splitlines()
    podaci = json.loads(izlaz[-1]) if izlaz else {}
    if r.returncode != 0 or "greska" in podaci:
        pytest.fail("merenje u pregledaču nije izvršeno (izlaz %d): %s\n%s"
                    % (r.returncode, podaci.get("greska", "bez izlaza"), r.stderr[-1500:]))
    return podaci


def _staticki_broj():
    """Dijagnostika (NIJE dokaz prikaza): sirove deklaracije < 11px u izvoru."""
    return sum(_u_pikselima(m) < POD_FONTA
               for rel in ("index.html", "static/vindex.css", "static/vindex.js")
               for l in _linije(rel) for m in FONT.finditer(l))


@pytest.mark.parametrize("ekran", ["desktop", "mobilni"])
@pytest.mark.parametrize("tema", ["dark", "light"])
def test_nijedna_velicina_teksta_nije_ispod_poda(tema, ekran):
    scenariji = _meri("scenariji", tema, ekran)["scenariji"]

    assert [k for k, _ in scenariji] == [
        "LANDING", "tab-h", "tab-p", "predmet-detalj", "tab-k", "tab-kal", "tab-aiws", "tab-s", "tab-dok",
        "tab-zadaci-g", "tab-fin", "tab-kanc", "tab-settings"]
    ispod = {}
    for kontekst, r in scenariji:
        for x in r["ispod"]:
            ispod.setdefault((x["putanja"], x["tekst"], x["px"]), (x, []))[1].append(kontekst)
    opis = "\n".join(
        "  %.2fpx  %dx%d  %s  %r  [%s]  pravilo: %s %s"
        % (x["px"], x["w"], x["h"], x["putanja"][-70:], x["tekst"], ",".join(gde[:3]),
           (x["poreklo"] or {}).get("sel", "?"), (x["poreklo"] or {}).get("v", ""))
        for x, gde in sorted(ispod.values(), key=lambda z: z[0]["px"])[:25])
    assert not ispod, ("tema=%s ekran=%s: %d vidljivih tekstualnih elemenata ispod %.0fpx "
                       "(u izvoru ima %d sirovih deklaracija < 11px — dijagnostika, ne dokaz):\n%s"
                       % (tema, ekran, len(ispod), POD_FONTA, _staticki_broj(), opis))


def test_merilo_prijavljuje_vidljiv_tekst_od_10px():
    """Negativna kontrola: vidljiv red liste predmeta sveden na efektivnih 10px MORA biti prijavljen."""
    r = _meri("kontrola-10px")
    assert r["pre"]["izmereno"] >= 10 and not r["pre"]["ispod"], r["pre"]["ispod"][:3]
    assert [(x["tekst"], x["px"]) for x in r["posle"]["ispod"]] == [
        ("Tužba — poništaj rešenja o otkazu", 10.0)], r["posle"]["ispod"]


def test_merilo_ne_prijavljuje_pregazenu_skrivenu_ni_neaktivnu_deklaraciju():
    """Kontrola lažnog pozitiva: 9px pregaženo jačim pravilom, 6px koje ne pogađa ništa i 8px na
    skrivenom elementu nisu efektivni sitan tekst."""
    r = _meri("kontrola-pregazeno")
    assert r["efektivno"] == "13px", r["efektivno"]
    assert r["rez"]["izmereno"] >= 10
    assert not r["rez"]["ispod"], r["rez"]["ispod"][:3]


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
