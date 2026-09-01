# -*- coding: utf-8 -*-
"""RG-1 — REFRESH KOJI NIJE NIŠTA ANALIZIRAO NE SME PRIJAVITI USPEH.

ŠTA JE BIO PROBLEM
==================
`_refresh_case_dna_body` ima rani izlaz za slučaj „nijedan dokument nema
čitljiv tekst" (tačno ono što ostane posle neuspelog OCR-a). Taj izlaz nosi
tačnu `poruka`, ali NE nosi nijedan ključ na koji se frontend grana:

    {"predmet_id", "case_dna": {}, "poruka", "docs_analizirano": 0,
     "dokumenti_bez_teksta"}

`_voice_refresh_case_dna` proverava tačno dva diskriminatora pre uspeha —
`dna.greska` i `data.case_dna_persisted === false`. Nijedan nije prisutan, pa
poziv pada u granu uspeha:

    showToast('Procena predmeta ažurirana', 'ok')

Advokat uploaduje skeniranu presudu, OCR ne uspe, klikne „Osveži procenu" i
dobije ZELENU potvrdu — a `poruka` koja objašnjava da ništa nije analizirano
biva odbačena. To je isti razred kvara koji je L6
(`test_living_system_fixes.py::test_genome_refresh_toast_checks_case_dna_persisted_flag`)
već zatvorio za pad upisa; ovaj rani izlaz je bio nepokrivena grana istog toka.

ZAŠTO SE MERE OBE STRANE
========================
Zelen test koji proverava samo backend (`poruka` postoji) ili samo frontend
(grana postoji) ne dokazuje ništa korisniku — poruka može postojati i nikad
ne biti prikazana, što je tačno stanje koje je zateknuto. Zato test spaja
ključeve koje backend ŠALJE sa ključevima na koje se frontend GRANA i traži
neprazan presek.

GRANICA
=======
Ne uvodi se nov diskriminator. Koristi se POSTOJEĆI `case_dna_persisted: False`
(Singular Intelligence, 2026-08-07) koji već znači „nije sačuvano" i koji
frontend već ispravno obrađuje prikazujući `data.poruka` kao grešku.
"""
import io
import os
import re

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..")
IZVOR_PY = os.path.join(REPO, "routers", "case_dna.py")
IZVOR_JS = os.path.join(REPO, "static", "vindex.js")

_MARKER_JS = "async function _voice_refresh_case_dna(predmetId) {"


def _telo_py(ime: str) -> str:
    s = io.open(IZVOR_PY, encoding="utf-8").read()
    poc = s.index(f"async def {ime}(")
    telo = s[poc:]
    for m in ("\nasync def ", "\n@router"):
        k = telo.find(m, 10)
        if k != -1:
            telo = telo[:k]
    return telo


def _rani_izlaz_bez_teksta() -> str:
    telo = _telo_py("_refresh_case_dna_body")
    i = telo.index("if not docs:")
    return telo[i:telo.index("}\n", i) + 1]


def _blok_js() -> str:
    s = io.open(IZVOR_JS, encoding="utf-8").read()
    return s.split(_MARKER_JS, 1)[1][:3500]


def _kljucevi_koje_backend_salje() -> set:
    return set(re.findall(r'"(\w+)":', _rani_izlaz_bez_teksta()))


def _diskriminatori_pre_uspeha() -> set:
    """Ključevi odgovora na koje se frontend grana PRE uspešnog toast-a."""
    blok = _blok_js()
    kraj = blok.index("Procena predmeta ažurirana")
    pre = blok[:kraj]
    nadjeni = set()
    if "dna.greska" in pre:
        nadjeni.add("greska")
    for m in re.finditer(r"data\.(\w+)\s*===\s*false", pre):
        nadjeni.add(m.group(1))
    return nadjeni


# ═══════════════════════════════════════════════════════════════════════════
# 1. UGOVOR PREKO OBE STRANE — ovo je sam kvar
# ═══════════════════════════════════════════════════════════════════════════

def test_prazan_rezultat_nosi_kljuc_na_koji_se_frontend_grana():
    salje = _kljucevi_koje_backend_salje()
    grana = _diskriminatori_pre_uspeha()
    presek = salje & grana
    assert presek, (
        "rani izlaz šalje %s, a frontend se pre uspeha grana na %s — presek je "
        "prazan, pa refresh koji NIJE ništa analizirao prikazuje zelen "
        "'Procena predmeta ažurirana'" % (sorted(salje), sorted(grana))
    )


def test_frontend_i_dalje_prikazuje_poruku_a_ne_izmisljen_tekst():
    """Diskriminator bez `data.poruka` bi dao tačan tip toast-a sa netačnim
    tekstom — korisnik mora videti RAZLOG, ne generičku grešku."""
    blok = _blok_js()
    kraj = blok.index("Procena predmeta ažurirana")
    assert "data.poruka" in blok[:kraj], \
        "grana neuspeha ne prikazuje `data.poruka` iz backend-a"


# ═══════════════════════════════════════════════════════════════════════════
# 2. BRAVE — ono što se ne sme tiho izgubiti
# ═══════════════════════════════════════════════════════════════════════════

def test_poruka_i_dalje_kaze_koliko_dokumenata_nije_procitano():
    blok = _rani_izlaz_bez_teksta()
    assert "len(_bez_teksta)" in blok, "poruka ne kaže KOLIKO dokumenata nije pročitano"
    assert "dokumenti_bez_teksta" in blok, "odgovor ne nosi listu nepročitanih dokumenata"


def test_provera_neuspeha_ide_pre_uspesnog_toasta():
    """Redosled JESTE deo ugovora, ali sam redosled nije dovoljan.

    Prva verzija je tražila samo da se `dna.greska` pojavi pre toast-a — pa je
    mutacija `if (false && dna.greska)` preživela: uslov je i dalje stajao na
    istom mestu, a grana je bila mrtva. Zato se traži TAČAN oblik čuvara, ne
    puko prisustvo imena polja."""
    blok = _blok_js()
    i_uspeh = blok.index("Procena predmeta ažurirana")
    for cuvar in ("if (dna.greska) {", "if (data.case_dna_persisted === false) {"):
        assert cuvar in blok, f"čuvar `{cuvar}` je izmenjen ili uklonjen"
        assert blok.index(cuvar) < i_uspeh, f"`{cuvar}` se izvršava tek posle uspešnog toast-a"


def test_rani_izlaz_ne_tvrdi_da_je_genome_sacuvan():
    """`case_dna_persisted: True` ovde bi bila tvrdnja o upisu koji se nije
    desio — gori ishod od današnjeg ćutanja."""
    blok = _rani_izlaz_bez_teksta()
    assert '"case_dna_persisted": True' not in blok
