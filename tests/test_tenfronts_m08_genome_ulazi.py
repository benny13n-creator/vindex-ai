# -*- coding: utf-8 -*-
"""TENFRONTS-M08 (KEYSTONE-005) — izmena polja predmeta ne čini Genome analizu zastarelom.

Dokaz POSTOJEĆEG ponašanja (bez izmene koda): Genome je funkcija dokumenata (`predmet_dokumenti`) i tvrdnji
(`predmet_dokazi`) — ne metapodataka predmeta. V2 forma (`frontend-v2-ng/src/rad-predmeta.js::POLJA`) menja
samo naziv, tip, tužioca, tuženog, vrednost spora i opis; nijedno od toga ne ulazi u `_extract_genome`, pa
izmena ne može da učini prikazanu analizu zastarelom u odnosu na njen ulaz."""
import asyncio
import os
import re
from unittest.mock import AsyncMock, patch

import routers.case_dna as cd
from tests.test_tenfronts_m07_genome_vlasnistvo import P, VLASNIK, _Baza

KOREN = os.path.join(os.path.dirname(__file__), "..")


def _ulaz_ekstrakcije(**predmet):
    baza = _Baza()
    baza.tabele["predmeti"][0].update(predmet)
    gpt = AsyncMock(return_value={"verzija": 2})
    with patch.object(cd, "_get_supa", return_value=baza), patch.object(cd, "_extract_genome", gpt), \
         patch("services.event_bus.emit", AsyncMock(), create=True), \
         patch("services.event_bus.emit_durable", AsyncMock(), create=True), \
         patch("shared.audit_immutable.log_action", AsyncMock()):
        asyncio.run(cd._do_genome_refresh(P, VLASNIK))
    assert gpt.await_count == 1
    return gpt.await_args


def test_polja_predmeta_ne_ulaze_u_genome():
    a = _ulaz_ekstrakcije(naziv="Parnica A", tip="parnicno", tuzilac="Marko", tuzeni="Jovan",
                          vrednost_spora=100000, opis="naknada štete")
    b = _ulaz_ekstrakcije(naziv="Sasvim drugi naziv", tip="krivicno", tuzilac="Ana", tuzeni="Petar",
                          vrednost_spora=999, opis="drugi opis")
    assert a == b, "Genome ulaz zavisi od metapodataka predmeta — izmena bi ga učinila zastarelim"


def test_v2_forma_menja_samo_polja_van_genome_ulaza():
    src = open(os.path.join(KOREN, "frontend-v2-ng", "src", "rad-predmeta.js"), encoding="utf-8").read()
    polja = set(re.findall(r'\{ kljuc: "(\w+)"', src.split("var POLJA = [", 1)[1].split("];", 1)[0]))
    assert polja == {"naziv", "tip", "tuzilac", "tuzeni", "vrednost_spora", "opis"}


def test_genome_cita_samo_dokumente_i_tvrdnje():
    import inspect
    src = inspect.getsource(cd._do_genome_refresh)
    pre_ekstrakcije = src.split("_extract_genome(", 1)[0]
    tabele = set(re.findall(r'table\("(\w+)"\)', pre_ekstrakcije))
    assert tabele == {"predmeti", "predmet_dokumenti"}        # predmeti: samo `case_dna` (stara verzija)
    assert '.select("case_dna")' in pre_ekstrakcije
    dokazi = inspect.getsource(cd._fetch_dokazi_kontekst)
    assert set(re.findall(r'table\("(\w+)"\)', dokazi)) == {"predmet_dokazi"}


def test_v2_analiza_odbacuje_odgovor_prethodnog_predmeta():
    src = open(os.path.join(KOREN, "frontend-v2-ng", "src", "analiza-predmeta.js"), encoding="utf-8").read()
    assert "kontroler.abort()" in src and "trenutni.id !== id" in src
