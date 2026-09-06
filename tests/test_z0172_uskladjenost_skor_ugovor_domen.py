# -*- coding: utf-8 -*-
"""
Z017.2 -- G3/G4/G5/G6/G9 popravka i klasifikacija, domen.

DVA STVARNA, PRETHODNO NEOTKRIVENA KVARA U VEC DEPLOYOVANOM V2 KODU
(dokazano citanjem routers/web3.py, ne pretpostavljeno):

  1. "aml" (G4, /web3/aml-audit) -- backend vraca {audit_data, objasnjenje},
     NIKAD {rezultat}. Generican uNalaz() je za SVAKI poziv prikazivao
     "odgovor nije stigao u ocekivanom obliku". `test_aml_koristi_skor_oblik`.

  2. "ugovor" (G5, /web3/analiziraj-ugovor) -- backend (SmartContractReq)
     ocekuje {solidity_source}, generican obrazac je slao {tekst} za SVIH
     pet analiza bez izuzetka -- 422 pre nego sto bi handler bio pozvan.
     `test_ugovor_ima_poseban_poljetela`.

KLASIFIKACIJA G3/G4/G5 (ne "correctly fenced" kao jedini odgovor):
  G3 (whitepaper) -- Kategorija A, advisory-only, NEMA RAG. Fenca vec
     jasno kaze "nije potkrepljen izvorima" -- IMPLEMENTED kao advisory.
  G4 (aml) -- Kategorija A, advisory-only (strukturiran GPT skor protiv
     ugradjenog rubrika, NEMA RAG) + BIO STVARNO POKVAREN (v. gore).
     IMPLEMENTED kao advisory, SADA i funkcionalan.
  G5 (ugovor) -- Kategorija A, advisory + deterministicki staticki
     pregled izvornog koda (_sc_detect_proxy i sl., v. web3_compliance.py)
     + BIO STVARNO POKVAREN (v. gore). IMPLEMENTED kao advisory, SADA i
     funkcionalan.
  Nijedna od tri NIJE Kategorija C ("currently impossible to ground") --
  fence je bezbednosno ponasanje (safety behavior), ne razlog da se
  capability oznaci BLOCKED kad backend/UI stvarno rade.
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


def _js(imports: str, telo: str):
    skripta = textwrap.dedent(f"""
        {imports}
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _u(telo):
    return _js(f'import {{ ANALIZE, analizaPoKljucu }} from "file:///{V2}/domain/uskladjenost.js";', telo)


def _sk(telo):
    return _js(f'import {{ uSkorIzvestaj, uLicencu }} from "file:///{V2}/domain/skorIzvestaj.js";', telo)


def _ug(telo):
    return _js(f'import {{ uUgovorAnalizu }} from "file:///{V2}/domain/ugovorAnaliza.js";', telo)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# Katalog -- 7 analiza, ispravni oblik/poljeTela per analizu
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_katalog_ima_sedam_analiza_posle_g6_g9_dodavanja():
    n = _u("return ANALIZE.length;")
    assert n == 7


@nodemark
def test_ugovor_ima_poseban_poljetela():
    a = _u('return analizaPoKljucu("ugovor");')
    assert a["poljeTela"] == "solidity_source"
    assert a["oblik"] == "ugovor"


@nodemark
def test_aml_koristi_skor_oblik():
    a = _u('return analizaPoKljucu("aml");')
    assert a["oblik"] == "skor"
    assert a["kljucPodataka"] == "audit_data"
    assert a["ukupniKljuc"] == "ukupna_uskladenost"


@nodemark
def test_ostale_analize_zadrzavaju_tekst_oblik_bez_poljetela():
    for kljuc in ("regulativa", "pretraga", "whitepaper", "reporting-simulator"):
        a = _u(f'return analizaPoKljucu({_j(kljuc)});')
        assert a["oblik"] == "tekst", kljuc
        assert "poljeTela" not in a or a.get("poljeTela") is None, kljuc


@nodemark
def test_due_diligence_g6_dodat_kao_skor():
    a = _u('return analizaPoKljucu("due-diligence");')
    assert a is not None and a["oblik"] == "skor"
    assert a["kljucPodataka"] == "health_data"


# ═══════════════════════════════════════════════════════════════════════════
# uSkorIzvestaj -- stvarni sadrzaj audit_data/health_data, ne prazan fallback
# ═══════════════════════════════════════════════════════════════════════════

AUDIT_DATA = {
    "audit_data": {
        "ukupna_uskladenost": 62,
        "uskladenost_nivo": "SREDNJI",
        "kategorije": {
            "kyc_procedure": {"skor": 10, "max": 15, "status": "warning", "komentar": "Delimicno pokriveno."},
        },
        "kriticni_nedostaci": ["Nema Travel Rule procedure."],
        "preporuke": ["Uvesti pisanu AML politiku."],
    },
    "objasnjenje": "AML/KYC uskladjenost: 62/100 - SREDNJI",
}


@nodemark
def test_uskoraizvestaj_cita_stvaran_sadrzaj_ne_prazno():
    r = _sk(f'return uSkorIzvestaj({_j(AUDIT_DATA)}, '
            '{ ukupniKljuc:"ukupna_uskladenost", nivoKljuc:"uskladenost_nivo", kljucPodataka:"audit_data" });')
    assert r["ukupno"] == 62
    assert r["nivo"] == "SREDNJI"
    assert len(r["kategorije"]) == 1
    assert r["kategorije"][0]["naziv"] == "Kyc procedure"
    assert r["kategorije"][0]["komentar"] == "Delimicno pokriveno."
    assert r["kriticniNedostaci"] == ["Nema Travel Rule procedure."]
    assert r["preporuke"] == ["Uvesti pisanu AML politiku."]


@nodemark
def test_uskoraizvestaj_odsutan_podatak_ostaje_null_ne_nula():
    r = _sk('return uSkorIzvestaj({}, { ukupniKljuc:"ukupna_uskladenost", nivoKljuc:"uskladenost_nivo", kljucPodataka:"audit_data" });')
    assert r["ukupno"] is None
    assert r["kategorije"] == []


@nodemark
def test_licencu_odvojena_funkcija_drugaciji_oblik():
    r = _sk('return uLicencu({ license_data: { dozvola_potrebna: true, nadlezni_organ: "NBS", rizik_nivo: "VISOK" }, objasnjenje: "x" });')
    assert r["dozvolaPotrebna"] is True
    assert r["nadlezniOrgan"] == "NBS"
    assert r["rizikNivo"] == "VISOK"


# ═══════════════════════════════════════════════════════════════════════════
# uUgovorAnalizu -- G5 realni odgovor
# ═══════════════════════════════════════════════════════════════════════════

UGOVOR_ODGOVOR = {
    "contract_name": "TestToken",
    "solidity_version": "0.8.19",
    "is_proxy_detected": True,
    "analysis_result": {
        "aml_kyc": {"nivo_rizika": "SREDNJI", "obrazlozenje": "Platforma posreduje."},
        "pravni_rizici": [
            {"rizik": "Neograničena emisija tokena.", "ozbiljnost": "VISOK", "obrazlozenje": "Nema cap()."},
        ],
        "klasifikacija_tokena": [
            {"kategorija": "utility_token", "status": "MOGUĆE", "faktori_za": ["x"], "faktori_protiv": []},
        ],
    },
}


@nodemark
def test_ugovoranalizu_cita_stvaran_sadrzaj():
    r = _ug(f'return uUgovorAnalizu({_j(UGOVOR_ODGOVOR)});')
    assert r["nazivUgovora"] == "TestToken"
    assert r["jeProxy"] is True
    assert len(r["rizici"]) == 1
    assert r["rizici"][0]["ozbiljnost"] == "VISOK"
    assert r["amlNivoRizika"] == "SREDNJI"
    assert len(r["klasifikacijaTokena"]) == 1


@nodemark
def test_ugovoranalizu_rizik_bez_teksta_ispada():
    r = _ug('return uUgovorAnalizu({ analysis_result: { pravni_rizici: [{ ozbiljnost:"VISOK" }, { rizik:"Stvaran rizik." }] } });')
    assert len(r["rizici"]) == 1
    assert r["rizici"][0]["rizik"] == "Stvaran rizik."
