# -*- coding: utf-8 -*-
"""
Z017.2 -- B20 (profitabilnost predmeta) + F11 (profitabilnost kancelarije), domen.

Oba su bila DEFERRED("izvedeni pokazatelj -- meri se posle upotrebe").
Backend (routers/profitabilnost.py) postoji za oba, potpuno radi (case_
profitability VIEW, stvarna naplata iz B16/F6 koja je vec u V2). 0 V2
povrsine je bio jedini stvaran razlog.

  1. OCENA (zelena/zuta/crvena) DOBIJA TEKSTUALNI NAZIV, NE SAMO BOJU.
     SS42 -- no hue-only semantics. `test_nazivocene_ne_zavisi_od_boje`.
  2. ODSUTAN NOVCANI IZNOS OSTAJE null, NE 0 RSD (isti zakon kao B2/B16).
     `test_odsutan_iznos_ostaje_null`.
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
        import * as P from "file:///{V2}/domain/profitabilnost.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


@nodemark
def test_nazivocene_ne_zavisi_od_boje():
    assert _js('return P.nazivOcene("zelena");') == "Profitabilan"
    assert _js('return P.nazivOcene("zuta");') == "Granično"
    assert _js('return P.nazivOcene("crvena");') == "Neprofitabilan"
    assert _js('return P.nazivOcene("nepoznato");') == "—"


@nodemark
def test_odsutan_iznos_ostaje_null():
    r = _js("return P.uProfitabilnostPredmeta({ finansije: {} }).finansije;")
    assert r["naplaceno"] is None
    assert r["nefakturisano"] is None


@nodemark
def test_profitabilnost_predmeta_cita_stvaran_sadrzaj():
    r = _js(
        'return P.uProfitabilnostPredmeta({ predmet_naziv:"Spor A", ocena:"zelena", '
        'finansije: { ukupno_naplaceno_rsd: 500000, naplativost_procenat: 80 }, '
        'ai_preporuka: "Razmotriti povecanje satnice." });'
    )
    assert r["naziv"] == "Spor A"
    assert r["ocenaNaziv"] == "Profitabilan"
    assert r["finansije"]["naplaceno"] is not None and "500.000" in r["finansije"]["naplaceno"]
    assert r["aiPreporuka"] == "Razmotriti povecanje satnice."


@nodemark
def test_pregled_statistika_i_predmeti_citaju_stvaran_sadrzaj():
    r = _js(
        'return P.uProfitabilnostPregled({ predmeti: [ { predmet_id:"p1", predmet_naziv:"Spor A", '
        'ocena:"crvena", ukupno_naplaceno_rsd: 0, nefakturisano_rsd: 200000 } ], '
        'ukupno_predmeta: 1, statistika: { zelenih: 0, zutih: 0, crvenih: 1 } });'
    )
    assert r["ukupnoPredmeta"] == 1
    assert r["statistika"]["crvenih"] == 1
    assert r["predmeti"][0]["ocenaNaziv"] == "Neprofitabilan"
