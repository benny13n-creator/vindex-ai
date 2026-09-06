# -*- coding: utf-8 -*-
"""
Z017.2 -- E10 UVOZ KLIJENATA, domen.

Prethodna sesija je pogresno zakljucila da E10 nema backend, jer je
trazila u routers/csv_import.py (kripto-transakciona CARF/DAC8
klasifikacija -- DRUGI capability pod slicnim imenom). Stvaran backend
je klijenti/router.py::import_klijenti_csv -- postoji, radi, tenant-
izolovan (user_id na svakom redu), 500-red limit, malformed red se
preskace po redu bez rusenja celog uvoza. Ispravka: 0 V2 povrsine je
bio jedini stvaran razlog, kao i F3/B18/C7/G6-G9.

  1. GRESKE PO REDU SE NE GUBE. `test_greske_se_prenose`.
  2. USPESAN UVOZ SA NEKIM GRESKAMA NIJE "SVE NEUSPESNO".
     `test_delimican_uspeh_nije_potpun_neuspeh`.
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
        import * as U from "file:///{V2}/domain/uvozKlijenata.js";
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
def test_greske_se_prenose():
    r = _js('return U.uRezultatUvoza({ kreiran: 3, ukupno_pokusano: 5, greske: ["Red 2: ime je obavezno."] });')
    assert r["kreiran"] == 3
    assert r["ukupnoPokusano"] == 5
    assert r["greske"] == ["Red 2: ime je obavezno."]


@nodemark
def test_delimican_uspeh_nije_potpun_neuspeh():
    r = _js('return U.uRezultatUvoza({ kreiran: 4, ukupno_pokusano: 5, greske: ["Red 3: x"] });')
    assert r["kreiran"] > 0  # UI mora prikazati uspeh za redove koji JESU uvezeni


@nodemark
def test_je_csv_fajl():
    assert _js('return U.jeCsvFajl({ name: "klijenti.csv" });') is True
    assert _js('return U.jeCsvFajl({ name: "klijenti.CSV" });') is True
    assert _js('return U.jeCsvFajl({ name: "klijenti.xlsx" });') is False
    assert _js('return U.jeCsvFajl(null);') is False
