# -*- coding: utf-8 -*-
"""
Z017.2 -- F10 FIRM HEALTH INDEX, domen.

F10 je bio DEFERRED("nema backend rute") -- neistina, potpuno pogresno
zakljuceno. Backend (routers/health_index.py::get_health_index) postoji,
racuna 6 komponenti (rokovi, snaga predmeta, naplata, angazovanost, rizik
portfolija, opterecenost), ima sopstvenu disciplinu oko cache staleness-a
(`iz_kesa`) upravo zato sto je Red Team dokazao da bez tog signala stara
"88/A/Sve je u redu" ocena moze pobediti svezu "34/C/HITNO". 0 V2 povrsine
je bio jedini stvaran razlog.

  1. IZ_KESA (STALENESS) SE NIKAD NE GUBI. `test_iz_kesa_se_prenosi`.
  2. VODECI EMOJI SE SKIDA, OSTATAK TEKSTA NE. `test_emoji_prefiks_skinut_tekst_ocuvan`.
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
        import * as H from "file:///{V2}/domain/firmHealthIndex.js";
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
def test_iz_kesa_se_prenosi():
    svez = _js('return H.uHealthIndex({ score: 88, grade: "A", iz_kesa: false });')
    star = _js('return H.uHealthIndex({ score: 88, grade: "A", iz_kesa: true });')
    assert svez["izKesa"] is False
    assert star["izKesa"] is True


@nodemark
def test_emoji_prefiks_skinut_tekst_ocuvan():
    r = _js('return H.uHealthIndex({ alerts: ["\\u26a0\\ufe0f 5 predmeta visokog rizika (30% portfolija)"] }).upozorenja;')
    assert len(r) == 1
    assert r[0] == "5 predmeta visokog rizika (30% portfolija)"
    assert "predmeta visokog rizika" in r[0]


@nodemark
def test_komponente_citaju_stvaran_sadrzaj():
    r = _js(
        'return H.uHealthIndex({ components: ['
        '{ label:"Rokovi i ročišta", score:18, max:20 }'
        '] }).komponente;'
    )
    assert len(r) == 1
    assert r[0]["naziv"] == "Rokovi i ročišta"
    assert r[0]["skor"] == 18 and r[0]["max"] == 20


@nodemark
def test_skor_odsutan_ostaje_null():
    r = _js("return H.uHealthIndex({});")
    assert r["skor"] is None
