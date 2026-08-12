# -*- coding: utf-8 -*-
"""
DEAD-CODE FORENSICS — brave nad presudama.

Prolaz je nad `static/vindex.js` (816 funkcija) našao **27 kandidata bez ijednog
pozivaoca**. Uklonjene su **dve**. Ostatak je KEEP ili DEFER, i to je namerno:
detektor je na 22 provere dao **2 lažna pozitiva**, oba bi bila regresija.

Ovaj fajl čuva tri stvari:
  1. da uklonjene funkcije ne prošvercuju povratak bez ulazne tačke;
  2. da se dva LAŽNO mrtva kandidata nikad ne obrišu;
  3. da se pet funkcija bez vrata (Pravilo 9) ne obriše kao „mrtav kod".
"""
import os
import re

import pytest

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(_KOREN, "static", "vindex.js"), encoding="utf-8").read()


def _html():
    return open(os.path.join(_KOREN, "index.html"), encoding="utf-8").read()


def _bez_komentara(js: str) -> str:
    """Detektor je u prvoj verziji brojao komentar kao kod i prijavio
    `#onboard-overlay` kao živ, iako postoji samo u komentaru o njegovom
    uklanjanju. Peti put u ovom repou; zato se komentari uvek uklanjaju."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


# ═══════════════════════════════════════════════════════════════════════════
# 1. UKLONJENO — i ne sme da se vrati bez ulazne tačke
# ═══════════════════════════════════════════════════════════════════════════

_UKLONJENE = {
    "_analizaSwitchTab": (
        "tražila `.t-tab` sa `onclick` koji sadrži `'n'`/`'t'`; ti tabovi su "
        "zamenjeni `_AIWS_MODES` sistemom. Poslednja dva pozivaoca prevedena su "
        "na `openAITool()` u Fazi 2.1."
    ),
    "docTplGetAktivniIdx": (
        "trolinijski getter bez ijednog pozivaoca; nema korisničku semantiku."
    ),
}


@pytest.mark.parametrize("ime", sorted(_UKLONJENE))
def test_uklonjena_funkcija_nije_vracena(ime):
    js = _bez_komentara(_js())
    assert not re.search(r"function\s+" + re.escape(ime) + r"\s*\(", js), (
        f"`{ime}` je vraćena. Uklonjena je jer je imala NULA pozivalaca "
        f"(statičkih, dinamičkih, kao niska i u runtime-u). Ako se vraća, mora "
        f"doći sa ulaznom tačkom.\nRazlog uklanjanja: {_UKLONJENE[ime]}"
    )


@pytest.mark.parametrize("ime", sorted(_UKLONJENE))
def test_nema_zaostalog_citaoca(ime):
    """Lekcija iz P0-0.

    `kalendarLoad` je uklonjen a red koji ga ČITA je ostao — `ReferenceError`
    na najvišem nivou oborio je izvršavanje 9.469 redova. Nije dovoljno da
    definicija nestane; ne sme ostati nijedno čitanje imena.
    """
    js = _bez_komentara(_js())
    html = re.sub(r"<!--.*?-->", "", _html(), flags=re.S)
    assert not re.search(r"(?<![\w$.])" + re.escape(ime) + r"(?![\w$])", js + html), (
        f"postoji referenca ka uklonjenoj `{ime}`"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. LAŽNO MRTVI — detektor ih je prijavio, dokaz ih je spasao
# ═══════════════════════════════════════════════════════════════════════════

def test_crm_konflikt_je_dostupan_preko_aliasa():
    """`crmPokreniKonfliktNovi` ima 0 poziva pod svojim imenom.

    Dostupan je pod DRUGIM imenom: `window.crmPokreniKonflikt = crmPokreniKonfliktNovi`,
    a taj alias zove `index.html:2092`. Detektor koji traži samo ime funkcije
    ovo ne vidi — i obrisao bi proveru sukoba interesa.
    """
    js = _js()
    html = _html()
    assert re.search(r"function\s+crmPokreniKonfliktNovi\s*\(", js), (
        "`crmPokreniKonfliktNovi` je obrisana — dostupna je preko aliasa "
        "`window.crmPokreniKonflikt`, koji zove index.html"
    )
    assert "window.crmPokreniKonflikt = crmPokreniKonfliktNovi" in js, (
        "alias je uklonjen — funkcija time postaje stvarno nedostupna"
    )
    assert "crmPokreniKonflikt()" in html, "pozivalac aliasa je nestao iz index.html"


def test_sud_dropdown_hide_je_referenca_bez_zagrada():
    """`_sud_dropdown_hide` se ne poziva — PROSLEĐUJE se.

    `index.html:3024`: `setTimeout(_sud_dropdown_hide, 200)`. Provera koja traži
    `ime(` ovo ne vidi; provera koja traži samo ime — vidi.
    """
    js = _js()
    html = _html()
    assert re.search(r"function\s+_sud_dropdown_hide\s*\(", js)
    assert "_sud_dropdown_hide," in html, (
        "referenca u `setTimeout(_sud_dropdown_hide, …)` je nestala iz index.html"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. FUNKCIJE BEZ VRATA — Pravilo 9, ne brisati kao „mrtav kod"
# ═══════════════════════════════════════════════════════════════════════════

_BEZ_VRATA = {
    "crmObrisi":        "brisanje klijenta — zove API (`fetch`)",
    "crmUredi":         "izmena klijenta — zove API i puni 11 polja",
    "copyToMarkdown":   "kopiranje analize kao Markdown, sa porukom korisniku",
    "sazimiZaKlijenta": "sažetak za klijenta, sa porukom korisniku",
    "aicOtvoriPredmet": "otvaranje predmeta iz AI konteksta, sa porukom korisniku",
}


@pytest.mark.parametrize("ime", sorted(_BEZ_VRATA))
def test_funkcija_bez_vrata_nije_obrisana(ime):
    """PRAVILO 9: mrtva ulazna tačka nije mrtva funkcija.

    Ovih pet nemaju nijednog pozivaoca — ali su KOMPLETNE korisničke funkcije,
    ne pomoćni kod. Dve od njih zovu API. Brisanje bi uklonilo sposobnost i
    predstavilo to kao čišćenje.

    Da im se daju vrata je proizvodna odluka, ne odluka o brisanju.
    """
    js = _js()
    assert re.search(r"(?:async\s+)?function\s+" + re.escape(ime) + r"\s*\(", js), (
        f"`{ime}` je obrisana kao mrtav kod. Ona JESTE bez ulazne tačke, ali "
        f"je kompletna funkcija: {_BEZ_VRATA[ime]}. Uklanjanje je odluka o "
        f"proizvodu, ne o čišćenju koda."
    )


def test_dve_od_njih_i_dalje_zovu_api():
    """Bez ovoga bi test iznad prolazio i da je od funkcija ostala prazna ljuska."""
    js = _js()
    for ime in ("crmObrisi", "crmUredi"):
        m = re.search(r"(?:async\s+)?function\s+" + re.escape(ime) + r"\s*\([^)]*\)\s*\{", js)
        i = m.end() - 1
        d = 0
        for j in range(i, len(js)):
            if js[j] == "{":
                d += 1
            elif js[j] == "}":
                d -= 1
                if d == 0:
                    break
        assert "fetch(" in js[m.start():j], f"`{ime}` više ne zove API — osiromašena je"


# ═══════════════════════════════════════════════════════════════════════════
# 4. BROJ MRTVIH FUNKCIJA NE SME DA RASTE
# ═══════════════════════════════════════════════════════════════════════════

def test_broj_funkcija_bez_pozivaoca_ne_raste():
    """Brava nad celom klasom.

    27 je zatečeno stanje (od 816 funkcija); ovim prolazom smanjeno na 25.
    Prag je IZMERENA vrednost. Test ne traži nulu — traži da broj ne raste, jer
    svaka nova funkcija bez pozivaoca znači ili izgubljena vrata ili nedovršen
    posao.
    """
    js = _bez_komentara(_js())
    html = re.sub(r"<!--.*?-->", "", _html(), flags=re.S)

    imena = set(re.findall(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", js, re.M))
    bez_pozivaoca = []
    for ime in sorted(imena):
        if re.search(r"\b" + re.escape(ime) + r"\s*\(", html):
            continue
        # svaka pojava imena u JS-u osim same definicije
        pojave = len(re.findall(r"(?<![\w$.])" + re.escape(ime) + r"(?![\w$])", js))
        defs = len(re.findall(r"function\s+" + re.escape(ime) + r"\s*\(", js))
        if pojave <= defs:
            bez_pozivaoca.append(ime)

    assert len(bez_pozivaoca) <= 25, (
        f"funkcija bez ijednog pozivaoca ima {len(bez_pozivaoca)} "
        f"(izmereno posle dead-code prolaza: 25):\n  "
        + "\n  ".join(bez_pozivaoca)
    )
