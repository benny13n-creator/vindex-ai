# -*- coding: utf-8 -*-
"""
Z017.14 — PODNESAK SUDU (`podnesak.js`), D5.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. KATALOZI SE NE PREPISUJU U FRONTEND.
     Tipovi podnesaka su do sada ziveli SAMO u validatoru `PodnesakReq.tip`.
     Spisak prepisan u frontend zastari tiho: nudio bi tip koji server
     odbija, i to bi se videlo tek posle skupog (naplativog) poziva.
     Zato se katalog cisti, ali se NE dopunjava iz koda.
     `test_nepotpun_tip_se_izostavlja`.

  2. GRUPE SUDOVA SE CUVAJU.
     „Osnovni sud u Beogradu" i „Apelacioni sud u Beogradu" nisu zamenljivi.
     Spljosten spisak bi ih prikazao kao ravnopravne stavke iste vrste.
     `test_grupe_sudova_ostaju_odvojene`.

  3. MINIMUM OPISA JE 20, JER TO TRAZI SERVER.
     Provera je na klijentu da bi advokat dobio recenicu koja kaze sta da
     uradi, umesto 422 posle cekanja na naplativ poziv.
     `test_kratak_opis_se_odbija`, `test_granica_je_tacno_20`.

  4. PRAZAN ULAZ NE RUSI EKRAN.
     `test_neispravan_oblik_daje_prazno_a_ne_pad`.
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
        import * as P from "file:///{V2}/domain/podnesak.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


SUDOVI = {"sudovi": {
    "Osnovni sudovi": [
        {"naziv": "Osnovi sud u Beogradu", "adresa": "Ustanička 29", "grad": "Beograd"},
        {"naziv": "Osnovni sud u Nišu", "adresa": "Vojvode Putnika 1", "grad": "Niš"},
    ],
    "Apelacioni sudovi": [
        {"naziv": "Apelacioni sud u Beogradu", "adresa": "Nemanjina 9", "grad": "Beograd"},
    ],
}}


# ── 1. Katalog tipova ────────────────────────────────────────────────────────
@nodemark
def test_tipovi_se_prenose():
    r = _js('return P.uTipovePodneska({ tipovi: ['
            '{ tip: "tuzba_naknada_stete", naziv: "Tužba za naknadu štete" }] });')
    assert r == [{"tip": "tuzba_naknada_stete", "naziv": "Tužba za naknadu štete"}]


@nodemark
def test_nepotpun_tip_se_izostavlja():
    """Tip bez naziva bi u spisku bio prazna stavka koju advokat moze izabrati."""
    r = _js('return P.uTipovePodneska({ tipovi: ['
            '{ tip: "a" }, { naziv: "B" }, { tip: "c", naziv: "C" }] });')
    assert r == [{"tip": "c", "naziv": "C"}], r


@nodemark
def test_neispravan_oblik_kataloga_daje_prazno():
    assert _js("return P.uTipovePodneska(null);") == []
    assert _js('return P.uTipovePodneska({ tipovi: "ne-niz" });') == []


# ── 2. Sudovi ────────────────────────────────────────────────────────────────
@nodemark
def test_grupe_sudova_ostaju_odvojene():
    r = _js(f"return P.uSudove({_j(SUDOVI)});")
    assert [g["grupa"] for g in r] == ["Osnovni sudovi", "Apelacioni sudovi"], r
    assert len(r[0]["sudovi"]) == 2 and len(r[1]["sudovi"]) == 1


@nodemark
def test_adresa_suda_se_prenosi():
    r = _js(f"return P.uSudove({_j(SUDOVI)});")
    assert r[0]["sudovi"][0]["adresa"] == "Ustanička 29"


@nodemark
def test_sud_bez_naziva_se_izostavlja():
    r = _js('return P.uSudove({ sudovi: { "G": [{ adresa: "X" },'
            ' { naziv: "Pravi sud" }] } });')
    assert len(r) == 1 and len(r[0]["sudovi"]) == 1
    assert r[0]["sudovi"][0]["naziv"] == "Pravi sud"


@nodemark
def test_prazna_grupa_se_izostavlja():
    r = _js('return P.uSudove({ sudovi: { "Prazna": [], "Puna": [{ naziv: "S" }] } });')
    assert [g["grupa"] for g in r] == ["Puna"], r


@nodemark
def test_neispravan_oblik_sudova_daje_prazno():
    assert _js("return P.uSudove(null);") == []
    assert _js("return P.uSudove({});") == []
    assert _js('return P.uSudove({ sudovi: "tekst" });') == []


# ── 3. Provera unosa ─────────────────────────────────────────────────────────
@nodemark
def test_kratak_opis_se_odbija():
    g = _js('return P.nedostaciPodneska({ tip: "t", opis: "kratko" });')
    assert g != [], "kratak opis bi otisao na naplativ poziv"
    assert "20" in g[0], g


@nodemark
def test_granica_je_tacno_20():
    """Server trazi `min_length=20`; 19 mora pasti, 20 mora proci."""
    assert _js('return P.nedostaciPodneska({ tip: "t", opis: "x".repeat(19) });') != []
    assert _js('return P.nedostaciPodneska({ tip: "t", opis: "x".repeat(20) });') == []


@nodemark
def test_predugacak_opis_se_odbija():
    g = _js('return P.nedostaciPodneska({ tip: "t", opis: "x".repeat(5001) });')
    assert g != [], "opis preko 5000 bi server odbio sa 422"


@nodemark
def test_bez_tipa_se_odbija():
    g = _js('return P.nedostaciPodneska({ opis: "x".repeat(30) });')
    assert g != []
    assert "vrstu" in g[0].lower(), g


@nodemark
def test_prazan_opis_trazi_opis_a_ne_duzinu():
    """Dve razlicite greske traze dve razlicite radnje od advokata."""
    g = _js('return P.nedostaciPodneska({ tip: "t", opis: "   " });')
    assert g == ["Opišite slučaj."], g


@nodemark
def test_ispravan_unos_nema_zamerki():
    assert _js('return P.nedostaciPodneska({ tip: "tuzba_naknada_stete", '
               'opis: "Klijent je pretrpeo štetu u nezgodi 12.03.2026." });') == []


@nodemark
def test_prazan_poziv_ne_ruši():
    assert _js("return P.nedostaciPodneska();") != []
