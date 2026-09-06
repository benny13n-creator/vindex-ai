# -*- coding: utf-8 -*-
"""
Z017.2 -- E6 ISTORIJA (TIMELINE) KLIJENTA, domen.

Prethodna sesija je pogresno zakljucila da E6 nema backend, jer je
trazila u routers/intelligence_timeline.py (zivot PREDMETA, ne klijenta
-- drugi capability pod slicnim imenom). Stvaran backend:
klijenti/router.py::get_timeline (GET /klijenti/{id}/timeline) --
agregira klijent_komunikacija + predmet otvoren/zatvoren dogadjaje,
tenant-izolovan (_verify_owns_klijent). 0 V2 povrsine je bio jedini
stvaran razlog, kao i E10/F3/B18/C7/G6-G9.

  1. NEPOZNAT TIP DOGADJAJA SE NE GUBI -- ispisuje se sirov tip, ne "Događaj"
     tiho da prekrije da nesto nije prepoznato. `test_nepoznat_tip_ostaje_vidljiv`.
  2. DOGADJAJ BEZ DATUMA ISPADA (ne moze se hronoloski poredati). `test_dogadjaj_bez_datuma_ispada`.
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
        import * as K from "file:///{V2}/domain/klijentIstorija.js";
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
def test_nazivi_tipova_poznati():
    assert _js('return K.nazivTipa("poziv");') == "Poziv"
    assert _js('return K.nazivTipa("predmet_otvoren");') == "Predmet otvoren"


@nodemark
def test_nepoznat_tip_ostaje_vidljiv():
    """Nepoznat tip se NE svodi na generican "Događaj" tiho -- sirova
    vrednost ostaje vidljiva, isti zakon kao nazivStanja/nazivVrste."""
    r = _js('return K.nazivTipa("neki_novi_tip_2027");')
    assert r == "neki_novi_tip_2027"


@nodemark
def test_dogadjaj_bez_datuma_ispada():
    r = _js(
        'return K.uIstorijuKlijenta({ timeline: ['
        '{ tip:"poziv", datum:"2026-01-01T10:00:00Z", opis:"x" },'
        '{ tip:"email", opis:"bez datuma" }'
        '] }).dogadjaji;'
    )
    assert len(r) == 1
    assert r[0]["tip"] == "poziv"


@nodemark
def test_ukupno_odsutno_racuna_se_iz_dogadjaja():
    r = _js('return K.uIstorijuKlijenta({ timeline: [{ tip:"poziv", datum:"2026-01-01" }] });')
    assert r["ukupno"] == 1


@nodemark
def test_godine_sortirane_najnovija_prva():
    r = _js('return K.uIstorijuKlijenta({ by_year: { "2024": [], "2026": [], "2025": [] } }).godine;')
    assert r == ["2026", "2025", "2024"]
