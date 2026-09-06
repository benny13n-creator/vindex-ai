# -*- coding: utf-8 -*-
"""
Z017.16 — JUTARNJI BRIFING (H5), domen.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. MODEL NIJE AUTORITET NAD STANJEM IZVORA.
     `ai_briefing` je tekst koji je napisao model; `*_dostupni` su masinski
     proverive zastavice o tome sta je stvarno procitano. Ekran izvodi
     zakljucke IZ ZASTAVICA. Ovo je tacno onaj kvar koji je vec bio blocker
     (N5, B-U-001): brifing je tvrdio odsustvo iz palog upita.
     `test_pao_izvor_daje_nepotpun_brifing`.

  2. ZASTAVICA MORA BITI IZRICITO `true`.
     Odsutna zastavica znaci „ne znam", ne „procitano je".
     `test_odsutna_zastavica_je_nedostupno`, `test_string_true_nije_true`.

  3. NEPROCITAN BROJ NIJE NULA.
     `brojIzvora` vraca `null` kad izvor nije procitan, da ekran ne bi
     ispisao „0 hitnih rokova" iz upita koji nije uspeo.
     `test_broj_iz_nedostupnog_izvora_je_null`.

  4. TEKST MODELA SE NE PRETVARA U OZNAKE.
     `delovi()` deli `**podebljano**` na delove; nikad se ne koristi
     `innerHTML`, jer bi model mogao da unese oznake.
     `test_delovi_ne_prave_oznake`.

  5. IMENA IZVORA SU STABILNA.
     Poruka „nije očitano: rokovi" mora imenovati izvor na jeziku advokata.
     `test_imena_izvora`.
"""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as B from "file:///{V2}/domain/brifing.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


POTPUN = {
    "datum": "2026-09-06",
    "ai_briefing": "**Dobro jutro.** Nema hitnih rokova.",
    "rokovi_dostupni": True, "rocista_dostupna": True,
    "predmeti_dostupni": True, "akcije_dostupne": True,
    "statistike": {"aktivnih_predmeta": 20, "rokova_ove_nedelje": 2,
                   "rokova_hitnih": 1, "rocista_danas": 0, "rocista_sedmica": 3,
                   "rokova_propustenih": 0, "rocista_propustenih": 0},
    "rokovi_hitni": [{"id": "r1", "dogadjaj": "Odgovor na tužbu",
                      "datum_iso": "2026-09-10", "predmet_id": "p1"}],
    "rokovi_propusteni": [], "rocista_danas": [], "rocista_propustena": [],
    "generisano_u": "2026-09-06T05:00:00+00:00",
}


def _b(o):
    return _js(f"return B.uBrifing({_j(o)});")


# ── 1. Stanje izvora ─────────────────────────────────────────────────────────
@nodemark
def test_potpun_brifing_je_potpun():
    r = _b(POTPUN)
    assert r["potpun"] is True
    assert r["nedostupni"] == []


@nodemark
def test_pao_izvor_daje_nepotpun_brifing():
    """Model i dalje pise „nema rokova" — zastavica kaze da nisu procitani."""
    r = _b(dict(POTPUN, rokovi_dostupni=False))
    assert r["potpun"] is False
    assert r["nedostupni"] == ["rokovi"], r["nedostupni"]
    # Tekst modela i dalje tvrdi odsustvo — zato se ne sme citati kao nalaz.
    assert "Nema hitnih rokova" in r["tekstBrifinga"]


@nodemark
def test_vise_palih_izvora_se_svi_imenuju():
    r = _b(dict(POTPUN, rokovi_dostupni=False, rocista_dostupna=False))
    assert set(r["nedostupni"]) == {"rokovi", "ročišta"}, r["nedostupni"]


# ── 2. Izricito `true` ───────────────────────────────────────────────────────
@nodemark
def test_odsutna_zastavica_je_nedostupno():
    o = dict(POTPUN)
    o.pop("rokovi_dostupni")
    r = _b(o)
    assert r["potpun"] is False
    assert "rokovi" in r["nedostupni"]


@nodemark
def test_string_true_nije_true():
    """`"true"` i `1` nisu dokaz da je izvor procitan — fail-closed."""
    for v in ['"true"', "1", "null"]:
        r = _js("return B.uBrifing({ rokovi_dostupni: " + v
                + ", rocista_dostupna: true, predmeti_dostupni: true,"
                " akcije_dostupne: true }).nedostupni;")
        assert "rokovi" in r, v


@nodemark
def test_prazan_odgovor_je_nepotpun():
    r = _js("return B.uBrifing(null);")
    assert r["potpun"] is False
    assert len(r["nedostupni"]) == 4


# ── 3. Broj iz nedostupnog izvora ────────────────────────────────────────────
@nodemark
def test_broj_iz_nedostupnog_izvora_je_null():
    assert _js("return B.brojIzvora(0, false);") is None
    assert _js("return B.brojIzvora(5, false);") is None
    assert _js("return B.brojIzvora(0, true);") == 0
    assert _js('return B.brojIzvora(3, "true");') is None


@nodemark
def test_odsutna_statistika_je_null_a_ne_nula():
    r = _b(dict(POTPUN, statistike={}))
    assert r["statistike"]["rokovaHitnih"] is None
    assert r["statistike"]["aktivnihPredmeta"] is None


@nodemark
def test_nula_iz_dostupnog_izvora_ostaje_nula():
    """Nula je merenje kad je izvor procitan — ne sme postati „nepoznato"."""
    r = _b(POTPUN)
    assert r["statistike"]["rocistaDanas"] == 0


# ── 4. Tekst modela ──────────────────────────────────────────────────────────
@nodemark
def test_delovi_dele_podebljano():
    r = _js('return B.delovi("**Dobro jutro.** Danas je mirno.");')
    assert r == [{"jak": True, "t": "Dobro jutro."},
                 {"jak": False, "t": " Danas je mirno."}], r


@nodemark
def test_delovi_ne_prave_oznake():
    """Nema `innerHTML`: oznake iz teksta modela ostaju obican tekst."""
    r = _js('return B.delovi("<img src=x onerror=alert(1)>");')
    assert r == [{"jak": False, "t": "<img src=x onerror=alert(1)>"}], r


@nodemark
def test_delovi_bez_podebljanog():
    assert _js('return B.delovi("obican tekst");') == [
        {"jak": False, "t": "obican tekst"}]
    assert _js("return B.delovi(null);") == []
    assert _js('return B.delovi("");') == []


@nodemark
def test_nezatvoreno_podebljano_ostaje_tekst():
    r = _js('return B.delovi("**bez kraja");')
    assert r == [{"jak": False, "t": "**bez kraja"}], r


# ── 5. Imena izvora ──────────────────────────────────────────────────────────
@nodemark
def test_imena_izvora():
    r = _js("return B.IZVORI.map(x => x.naziv);")
    assert r == ["rokovi", "ročišta", "predmeti", "predložene radnje"], r


# ── 6. Stavke ────────────────────────────────────────────────────────────────
@nodemark
def test_hitni_rokovi_nose_predmet():
    r = _b(POTPUN)
    assert len(r["hitniRokovi"]) == 1
    assert r["hitniRokovi"][0]["predmetId"] == "p1"
    assert r["hitniRokovi"][0]["opis"] == "Odgovor na tužbu"


@nodemark
def test_prazna_stavka_se_izostavlja():
    r = _b(dict(POTPUN, rokovi_hitni=[{}, {"dogadjaj": "Pravi rok"}]))
    assert len(r["hitniRokovi"]) == 1
