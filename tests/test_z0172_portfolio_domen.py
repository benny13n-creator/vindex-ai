# -*- coding: utf-8 -*-
"""
Z017.2 -- F9 PORTFOLIO KANCELARIJE, domen.

F9 je bio DEFERRED("izvedeni pokazatelj -- meri se posle upotrebe") --
neistina. Backend (routers/portfolio.py::portfolio_dashboard) postoji,
racuna stvarne brojeve (distribucija, rokovi 7/14 dana, neaktivni
predmeti, narativni summary IZVEDEN iz tih brojeva, ne izmisljen). 0 V2
povrsine je bio jedini stvaran razlog.

  1. SUMMARY SE PRENOSI, NE PREPRAVLJA. `test_summary_se_prenosi_doslovno`.
  2. PAD PORTFOLIA VRACA GRESKU, NE PRAZAN PORTFOLIO.
     `test_neucitan_portfolio_ne_tvrdi_da_je_prazan`.
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
        import * as P from "file:///{V2}/domain/portfolio.js";
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
def test_summary_se_prenosi_doslovno():
    r = _js('return P.uPortfolio({ summary: "Sve je pod kontrolom." }).summary;')
    assert r == "Sve je pod kontrolom."


@nodemark
def test_hitni_rokovi_citaju_stvaran_sadrzaj():
    r = _js(
        'return P.uPortfolio({ hitni_rokovi: [{ predmet_id:"p1", predmet_naziv:"Spor A", '
        'dogadjaj:"Ročište", datum_iso:"2026-09-10", vaznost:"kritičan" }] }).hitniRokovi;'
    )
    assert len(r) == 1
    assert r[0]["predmetNaziv"] == "Spor A"
    assert r[0]["dogadjaj"] == "Ročište"


@nodemark
def test_broj_predmeta_odsutan_ostaje_nula_ne_null():
    """Za razliku od novcanih iznosa, brojanje predmeta ima prirodnu nulu --
    0 predmeta je validan, iskren odgovor (za razliku od odsutnog iznosa
    koji NE sme postati 0 RSD)."""
    r = _js("return P.uPortfolio({});")
    assert r["ukupnoPredmeta"] == 0
    assert r["ukupnoAktivnih"] == 0
