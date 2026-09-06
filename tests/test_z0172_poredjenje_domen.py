# -*- coding: utf-8 -*-
"""
Z017.2 -- C7 POREĐENJE DOKUMENATA, domen.

C7 je bio klasifikovano DEFERRED ("nije u vlasnikovom redu izvrsenja") --
neistina po strogom pravilu SS3 (prioritet odredjuje redosled, ne sudbinu).
Backend (`routers/cross_doc.py::cross_doc_predmet`) postoji, radi, vec
validira citate protiv izvornog teksta -- 0 V2 povrsine je bio jedini
stvarni razlog.

  1. ODSUSTVO UPOZORENJA JE INFORMACIJA, NE PRAZAN STRING.
     `upozorenje_skracenja` je `None` kad NIJEDAN dokument nije skracen --
     razlikuje se od praznog stringa (koji bi mogao doci iz drugog uzroka).
     `test_odsustvo_upozorenja_je_null_ne_prazan_string`.

  2. VALIDACIJA BROJA DOKUMENATA PRATI SERVERSKU GRANICU (2-5).
     `test_validan_broj_dokumenata`.
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
        import * as P from "file:///{V2}/domain/poredjenje.js";
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
def test_odsustvo_upozorenja_je_null_ne_prazan_string():
    bez = _js('return P.uPoredjenje({ pravno_pitanje:"x", upozorenje_skracenja: null });')
    assert bez["upozorenjeSkracenja"] is None

    sa = _js('return P.uPoredjenje({ pravno_pitanje:"x", upozorenje_skracenja: "Dokument A skracen." });')
    assert sa["upozorenjeSkracenja"] == "Dokument A skracen."


@nodemark
def test_validan_broj_dokumenata():
    assert _js("return P.validanBrojDokumenata(1);") is False
    assert _js("return P.validanBrojDokumenata(2);") is True
    assert _js("return P.validanBrojDokumenata(5);") is True
    assert _js("return P.validanBrojDokumenata(6);") is False


@nodemark
def test_konflikt_bez_opisa_ispada_a_konflikt_bez_citata_ostaje():
    """Backend vec garantuje da konflikt ima citat (validacija u
    _validate_konflikti_citati) -- ovaj sloj ne dodaje tu proveru, samo ne
    sme da izmisli citat kad backend ne posalje jedan (npr. stariji
    odgovor bez tog polja)."""
    r = _js(
        'return P.uPoredjenje({ pravno_pitanje:"x", konflikti: ['
        '{ opis:"Rok raskida se razlikuje.", citat:"clan 5" },'
        '{ citat:"clan bez opisa" },'
        '{ opis:"Drugi konflikt bez citata." }'
        '] }).konflikti;'
    )
    assert len(r) == 2  # red bez opisa ispada
    assert r[0]["citat"] == "clan 5"
    assert r[1]["citat"] == ""  # ne izmisljen, prazan string je posten odgovor


@nodemark
def test_preporuke_bez_teksta_ispadaju():
    r = _js(
        'return P.uPoredjenje({ pravno_pitanje:"x", preporuke: ['
        '{ tekst:"Uskladiti rokove.", prioritet: 1 },'
        '{ prioritet: 2 }'
        '] }).preporuke;'
    )
    assert len(r) == 1
    assert r[0]["prioritet"] == 1
