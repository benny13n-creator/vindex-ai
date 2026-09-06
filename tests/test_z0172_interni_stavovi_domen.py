# -*- coding: utf-8 -*-
"""
Z017.2 -- D9 INTERNI PRAVNI STAVOVI, domen (frontend strana).

D9 je bio DEFERRED("nije u vlasnikovom redu izvrsenja") -- ne kvalifikuje
se kao OWNER_DEFERRED po strogom pravilu §3. routers/interni.py postoji,
registrovan je (app.include_router(interni_router)), 3 rute rade. 0 V2
povrsine je bio jedini stvaran razlog. Usput nadjen i popravljen pravi
FAILURE != EMPTY kvar u interni_stavovi.py::search_stavovi (v.
test_z0172_interni_stavovi_failure_semantics.py za backend stranu).

  1. PRETRAGA_NEUSPESNA SE NIKAD NE GUBI NA FRONTEND STRANI.
     `test_pretraga_neuspesna_se_prenosi`.
  2. VALIDACIJA STAVA PRATI SERVERSKU GRANICU (naslov>=3, tekst>=30).
     `test_nedostaci_stava`.
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
        import * as S from "file:///{V2}/domain/interniStavovi.js";
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
def test_pretraga_neuspesna_se_prenosi():
    palo = _js('return S.uPretragu({ rezultati: [], ukupno: 0, pretraga_neuspesna: true });')
    prazno = _js('return S.uPretragu({ rezultati: [], ukupno: 0, pretraga_neuspesna: false });')
    assert palo["pretragaNeuspesna"] is True
    assert prazno["pretragaNeuspesna"] is False


@nodemark
def test_rezultati_citaju_stvaran_sadrzaj():
    r = _js(
        'return S.uPretragu({ rezultati: [{ naslov:"Raskid ugovora", tekst:"Stav firme...", score:0.81 }], '
        'ukupno: 1, pretraga_neuspesna: false }).rezultati;'
    )
    assert len(r) == 1
    assert r[0]["naslov"] == "Raskid ugovora"
    assert r[0]["tekst"] == "Stav firme..."


@nodemark
def test_nedostaci_stava():
    assert len(_js('return S.nedostaciStava("ab", "x".repeat(40));')) == 1  # kratak naslov
    assert len(_js('return S.nedostaciStava("Naslov", "prekratak");')) == 1  # kratak tekst
    assert _js('return S.nedostaciStava("Naslov ok", "x".repeat(40));') == []
