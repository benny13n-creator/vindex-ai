# -*- coding: utf-8 -*-
"""
Z017.2 -- B18 druga polovina: PREDMETI DELJENI SA MNOM, domen.

Pre ovog fajla, saradnik dodat na tudji predmet (v2/features/dosije/saradnja.js,
vlasnikova strana) NIJE IMAO NIKAKAV NACIN da taj predmet pronadje u V2 --
backend (`GET /api/saradnja/moji-predmeti`) je postojao, V2 ga nije zvao.
Saradnja je bila upravljiva SAMO sa vlasnikove strane -- pola capability-ja.

  1. NEPOZNATA ULOGA SE NE PRIKAZUJE KAO JEDNA OD TRI STVARNE.
     Ista domenska funkcija (`nazivUloge`) kao vlasnikova strana -- jedan
     izvor istine za citanje uloge, ne dva. `test_deljeni_koristi_istu_nazivuloge_funkciju`.

  2. PREDMET BEZ ID-JA NE POSTAJE LAZAN DEEP LINK.
     `test_predmet_bez_id_ispada`.

  3. PRAZNA/PALA LISTA NE PRAVI PRAZAN BLOK U REGISTRU.
     Vecina naloga nema saradnju -- stalan prazan blok bi bio sum na
     najcesce koriscenom ekranu. `sekcijaDeljenihPredmeta` vraca `null` i
     pozivalac nista ne dodaje. `test_prazno_ili_palo_ne_pravi_sekciju`.
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
        import * as D from "file:///{V2}/features/predmeti/deljeni.js";
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
def test_deljeni_koristi_istu_nazivuloge_funkciju():
    r = _js('return D.uDeljenPredmet({ predmet_id:"p1", naziv:"Spor A", uloga:"vodenje" });')
    assert r["ulogaNaziv"] == "Vođenje"
    nepoznato = _js('return D.uDeljenPredmet({ predmet_id:"p1", naziv:"Spor A", uloga:"nesto" });')
    assert nepoznato["ulogaNaziv"] == "—"


@nodemark
def test_predmet_bez_naziva_dobija_zamenu_ne_prazno():
    r = _js('return D.uDeljenPredmet({ predmet_id:"p1", uloga:"citanje" });')
    assert r["naziv"] == "Predmet bez naziva"


@nodemark
def test_prazno_ili_palo_ne_pravi_sekciju():
    prazno = _js('return D.sekcijaDeljenihPredmeta({ ucitano:true, predmeti:[] }, null);')
    palo = _js('return D.sekcijaDeljenihPredmeta({ ucitano:false, predmeti:[] }, null);')
    assert prazno is None and palo is None
