# -*- coding: utf-8 -*-
"""NS3-N13 — nepoznata činjenica u nacrtu podneska mora ostati VIDLJIVA (`[… — POPUNITI]`), ne prazna.

Ugovor `templates/podnesci.py::popuni_sablon`: „Sve nepoznate {PLACEHOLDER} vrednosti ostaju vidljive kao
[POPUNITI]“. Ekstrakcioni promptovi (`EKSTRAKCIONI_PROMPTOVI`) modelu kažu „ako nije naveden, ostavi prazno“, pa
model za nepoznato polje vraća `""` (ili `null`). `entiteti.get(k, "[… — POPUNITI]")` tada vraća prazno: nacrt je
glasio „Tužilac: ,“ i bez suda — praznina koju advokat lako ne primeti, umesto oznake koju mora popuniti.

Stvarna `popuni_sablon` za svaki tip podneska; ništa od modela."""
import inspect
import re

import pytest

from templates.podnesci import EKSTRAKCIONI_PROMPTOVI, SABLONI, popuni_sablon

KLJUCEVI = sorted(set(re.findall(r'entiteti\.get\("(\w+)"', inspect.getsource(popuni_sablon))))


@pytest.mark.parametrize("tip", sorted(SABLONI))
@pytest.mark.parametrize("prazno", ["", None, "   "], ids=["prazan_string", "null", "razmaci"])
def test_prazna_vrednost_modela_je_isto_sto_i_nepoznata(tip, prazno):
    ocekivano = popuni_sablon(tip, {}, {})
    dobijeno = popuni_sablon(tip, {k: prazno for k in KLJUCEVI}, {})
    assert dobijeno == ocekivano, "prazna vrednost iz modela briše oznaku [POPUNITI]"


@pytest.mark.parametrize("tip", sorted(SABLONI))
def test_poznata_vrednost_i_dalje_upisana(tip):
    ent = {k: f"VREDNOST_{k.upper()}" for k in KLJUCEVI}
    out = popuni_sablon(tip, ent, {})
    upisano = [k for k in KLJUCEVI if f"VREDNOST_{k.upper()}" in out]
    assert upisano, "nijedna poznata vrednost nije upisana"
    assert out.count("POPUNITI") < popuni_sablon(tip, {}, {}).count("POPUNITI")


def test_nula_i_srpska_slova_nisu_prazno():
    out = popuni_sablon("tuzba_naknada_stete", {"tuzilac_ime": "Đorđe Šćekić", "vrednost_spora": 0}, {})
    assert "Đorđe Šćekić" in out


def test_promptovi_zaista_traze_prazno_za_nepoznato():
    """Razlog zašto je ovo bitno u stvarnom toku: model je upućen da vrati prazno."""
    assert any("ostavi prazno" in p for p in EKSTRAKCIONI_PROMPTOVI.values())
