# -*- coding: utf-8 -*-
"""
Z017.12 — RACUNANJE ROKOVA (`rokovi_racun.js`), B26.

Backend racuna oba roka DETERMINISTICKI i iz zakona: zastarelost po ZOO/ZR,
procesne rokove po ZPP/ZKP/ZR/ZIO/ZUP uz srpske praznike i radne dane. Nije
AI odgovor, pa se zakljucak sme prikazati — ali samo dok osnov postoji.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. ZAKLJUCAK BEZ ZAKONSKOG OSNOVA SE NE PRIKAZUJE.
     Rok bez clana na koji se advokat moze pozvati pred sudom nije
     upotrebljiv. `test_bez_zakonskog_osnova_nije_upotrebljiv`.

  2. „ISTEKLO" NOSI SOPSTVENO STANJE.
     Zastarelo potrazivanje i propusten procesni rok su najteze vesti koje
     ovaj ekran saopstava; ne smeju deliti stanje sa „ostalo je jos 40 dana".
     `test_isteklo_je_svoje_stanje`, `test_negativan_broj_dana_je_isteklo`.

  3. IZRICITA IZJAVA BACKENDA POBEDJUJE RACUNICU.
     `isteklo: true` vazi i kad je `dana_preostalo` pozitivno — server zna za
     pravila koja ovaj modul ne zna. `test_izricito_isteklo_pobedjuje_broj_dana`.

  4. ODSUTAN BROJ DANA NIJE NULA.
     `Number(null)` je 0; „ne znam koliko je ostalo" nije „istice danas".
     `test_odsutan_broj_dana_je_nepoznato`.

  5. JEDAN OBLIK DATUMA NA EKRANU.
     Backend salje zastarelost kao „01.05.2030", a procesni rok kao ISO
     „2026-09-22". Dva oblika na istom ekranu se citaju kao dve vrste
     podatka. `test_iso_datum_se_prikazuje_srpski`.

  6. NEPOZNAT OBLIK SE NE PREPRAVLJA.
     `test_neprepoznat_datum_ostaje_kakav_je`.

  7. ULAZ SE PROVERAVA PRE POZIVA.
     `test_nedostaci_hvataju_prazno_i_pogresan_oblik`.
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
        import * as R from "file:///{V2}/domain/rokovi_racun.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


ZAST = {
    "tip_potrazivanja": "Opšti rok zastarelosti",
    "zakonski_osnov": "ZOO čl. 371",
    "rok_opis": "10 godina",
    "datum_pocetka": "01.05.2020",
    "datum_zastarelosti": "01.05.2030",
    "datum_zastarelosti_iso": "2030-05-01",
    "dana_preostalo": 1334,
    "isteklo": False,
    "napomena": "",
}

PROC = {
    "tip_roka": "zalba_zpp",
    "naziv": "Žalba na prvostepenu presudu (ZPP čl. 368)",
    "datum_pocetka": "2026-09-01",
    "datum_isteka": "2026-09-22",
    "dani_do_isteka": 17,
    "hitno": False,
    "isteklo": False,
    "napomena": "15 radnih dana od dostavljanja presude",
}


def _z(o):
    return _js(f"return R.uZastarelost({_j(o)});")


def _p(o):
    return _js(f"return R.uProcesniRok({_j(o)});")


# ── 1. Bez zakonskog osnova ──────────────────────────────────────────────────
@nodemark
def test_normalan_odgovor_je_upotrebljiv():
    assert _z(ZAST)["upotrebljiv"] is True
    assert _p(PROC)["upotrebljiv"] is True


@nodemark
def test_bez_zakonskog_osnova_nije_upotrebljiv():
    """Rok bez clana nije upotrebljiv pred sudom — ekran ga ne prikazuje."""
    assert _z(dict(ZAST, zakonski_osnov=""))["upotrebljiv"] is False
    r = dict(ZAST)
    r.pop("zakonski_osnov")
    assert _z(r)["upotrebljiv"] is False


@nodemark
def test_bez_datuma_isteka_nije_upotrebljiv():
    assert _z(dict(ZAST, datum_zastarelosti=""))["upotrebljiv"] is False
    assert _p(dict(PROC, datum_isteka=""))["upotrebljiv"] is False


@nodemark
def test_procesni_bez_naziva_nije_upotrebljiv():
    """Naziv procesnog roka NOSI clan zakona — bez njega nema osnova."""
    assert _p(dict(PROC, naziv=""))["upotrebljiv"] is False


@nodemark
def test_prazan_odgovor_nije_upotrebljiv():
    assert _js("return R.uZastarelost(null);")["upotrebljiv"] is False
    assert _js("return R.uProcesniRok(undefined);")["upotrebljiv"] is False


# ── 2. „Isteklo" ─────────────────────────────────────────────────────────────
@nodemark
def test_isteklo_je_svoje_stanje():
    r = _z(dict(ZAST, isteklo=True, dana_preostalo=-500))
    assert r["ishod"] == "isteklo", r


@nodemark
def test_negativan_broj_dana_je_isteklo():
    """Cak i kad backend ne kaze `isteklo`, negativan broj dana to znaci."""
    assert _z(dict(ZAST, isteklo=False, dana_preostalo=-1))["ishod"] == "isteklo"
    assert _p(dict(PROC, isteklo=False, dani_do_isteka=-3))["ishod"] == "isteklo"


@nodemark
def test_izricito_isteklo_pobedjuje_broj_dana():
    """Server zna za pravila koja ovaj modul ne zna; njegova izjava vazi."""
    r = _z(dict(ZAST, isteklo=True, dana_preostalo=900))
    assert r["ishod"] == "isteklo", r


@nodemark
def test_u_toku_i_blizu_su_razdvojeni():
    assert _z(dict(ZAST, dana_preostalo=1334))["ishod"] == "u_toku"
    assert _z(dict(ZAST, dana_preostalo=10))["ishod"] == "blizu"
    assert _p(dict(PROC, dani_do_isteka=90))["ishod"] == "u_toku"
    assert _p(dict(PROC, dani_do_isteka=17))["ishod"] == "blizu"


# ── 3. Odsutan broj dana ─────────────────────────────────────────────────────
@nodemark
def test_odsutan_broj_dana_je_nepoznato():
    """`Number(null)` je 0 — „ne znam koliko je ostalo" nije „istice danas"."""
    r = _z(dict(ZAST, dana_preostalo=None))
    assert r["ishod"] == "nepoznato", r
    assert r["danaPoznato"] is False
    assert r["dana"] is None


@nodemark
def test_nula_dana_nije_nepoznato():
    """Nula je merenje: rok istice danas. Ne sme se pobrkati sa odsustvom."""
    r = _p(dict(PROC, dani_do_isteka=0))
    assert r["danaPoznato"] is True
    assert r["dana"] == 0
    assert r["ishod"] == "blizu"


# ── 4. Oblik datuma ──────────────────────────────────────────────────────────
@nodemark
def test_iso_datum_se_prikazuje_srpski():
    r = _p(PROC)
    assert r["doDatuma"] == "22.09.2026", r["doDatuma"]
    assert r["odDatuma"] == "01.09.2026", r["odDatuma"]


@nodemark
def test_vec_srpski_datum_ostaje_isti():
    r = _z(ZAST)
    assert r["doDatuma"] == "01.05.2030", r["doDatuma"]


@nodemark
def test_neprepoznat_datum_ostaje_kakav_je():
    """Nepoznat oblik se NE prepravlja — prikazuje se kakav je stigao."""
    assert _js('return R.datumSrpski("2026-09");') == "2026-09"
    assert _js('return R.datumSrpski("nepoznato");') == "nepoznato"
    assert _js("return R.datumSrpski(null);") == ""


# ── 5. Ulazna provera ────────────────────────────────────────────────────────
@nodemark
def test_nedostaci_hvataju_prazno_i_pogresan_oblik():
    assert _js("return R.nedostaciRacuna({});") != []
    assert _js('return R.nedostaciRacuna({ tip: "", datum: "2026-01-01" });') != []
    assert _js('return R.nedostaciRacuna({ tip: "opsti", datum: "2026-01-01" });') == []


@nodemark
def test_prazan_datum_trazi_unos_a_ne_ispravku_oblika():
    """Dve razlicite greske trazie dve razlicite radnje od advokata.

    „Datum mora biti u obliku GGGG-MM-DD" na PRAZNOM polju je uputstvo za
    posao koji korisnik nije ni zapoceo — on treba da unese datum, ne da
    ispravi oblik.
    """
    g = _js('return R.nedostaciRacuna({ tip: "opsti", datum: "" });')
    assert g == ["Unesite datum od koga rok teče."], g


@nodemark
def test_pogresan_oblik_trazi_ispravku_oblika():
    g = _js('return R.nedostaciRacuna({ tip: "opsti", datum: "01.01.2026" });')
    assert g == ["Datum mora biti u obliku GGGG-MM-DD."], g


@nodemark
def test_nepostojeci_datum_se_odbija():
    g = _js('return R.nedostaciRacuna({ tip: "opsti", datum: "2026-02-31" });')
    assert g != [], "31. februar je prosao kao ispravan datum"


# ── 6. Spiskovi vrsta ────────────────────────────────────────────────────────
@nodemark
def test_tipovi_zastarelosti_nose_osnov():
    r = _js('return R.uTipoveZastarelosti({ tipovi: [{ kljuc: "opsti", '
            'naziv: "Opšti rok", osnov: "ZOO čl. 371", opis: "x" }] });')
    assert r == [{"kljuc": "opsti", "naziv": "Opšti rok",
                  "osnov": "ZOO čl. 371", "opis": "x"}]


@nodemark
def test_radni_i_kalendarski_dani_se_razlikuju():
    """Razlika menja datum isteka — ne sme se progutati."""
    r = _js('return R.uTipoveProcesnih({ tipovi: ['
            '{ kod: "a", naziv: "A", dani: 15, tip: "radni", napomena: "" },'
            '{ kod: "b", naziv: "B", dani: 30, tip: "kalendarski", napomena: "" }] });')
    assert r[0]["racunanje"] == "radnih dana"
    assert r[1]["racunanje"] == "kalendarskih dana"


@nodemark
def test_napomena_koja_vec_kaze_broj_dana_je_oznacena():
    """Inace ekran ispisuje „15 radnih dana · 15 radnih dana od dostavljanja"."""
    r = _js('return R.uTipoveProcesnih({ tipovi: [{ kod: "a", naziv: "A", '
            'dani: 15, tip: "radni", napomena: "15 radnih dana od dostavljanja" }] });')
    assert r[0]["ponavlja"] is True
    r2 = _js('return R.uTipoveProcesnih({ tipovi: [{ kod: "a", naziv: "A", '
             'dani: 15, tip: "radni", napomena: "od dostavljanja presude" }] });')
    assert r2[0]["ponavlja"] is False


@nodemark
def test_neispravan_oblik_spiska_daje_prazno_a_ne_pad():
    assert _js("return R.uTipoveZastarelosti(null);") == []
    assert _js('return R.uTipoveProcesnih({ tipovi: "ne-niz" });') == []
    assert _js("return R.uTipoveZastarelosti({ tipovi: [{}] });") == []
