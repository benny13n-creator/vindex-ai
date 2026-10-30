# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — deterministička ekstrakcija iz prijema (BA-03, BA-05).

Task 2: sud ne sme da pređe u sledeći red zaglavlja („OSNOVNI SUD U BEOGRADU\\nPosl. br.“ → „… Posl“, 0.90).
Task 3: iznos „350.000,00 dinara“ mora biti prepoznat, sa tačnim brojem i valutom.
"""
import asyncio
from decimal import Decimal

import pytest

import shared.intake_extract as ex
from shared.intake_extract import extract_amount, extract_court

ZAGLAVLJE = "OSNOVNI SUD U BEOGRADU\nPosl. br. P 7714/2026\nTuzilac: Petar Goldenovic iz Beograda"


@pytest.mark.parametrize("tekst, ocekivano", [
    ("Osnovni sud u Beogradu doneo je presudu.", "Osnovni sud u Beogradu"),
    ("OSNOVNI SUD U BEOGRADU", "OSNOVNI SUD U BEOGRADU"),
    ("Osnovni sud u Novom Sadu\nBroj: P 1/2026", "Osnovni sud u Novom Sadu"),
    ("VIŠI SUD U SREMSKOJ MITROVICI\nPredmet: Kž 12/2026", "VIŠI SUD U SREMSKOJ MITROVICI"),
    ("Prekršajni sud u Novom Pazaru, dana 01.10.2026.", "Prekršajni sud u Novom Pazaru"),
    ("Vrhovni kasacioni sud odbio je reviziju.", "Vrhovni kasacioni sud"),
    ("UPRAVNI SUD\nU 1234/2026", "UPRAVNI SUD"),
])
def test_sud_tacan_naziv(tekst, ocekivano):
    assert extract_court(tekst) == (ocekivano, 0.9)


@pytest.mark.parametrize("sledeci_red", ["Posl. br. P 7714/2026", "Broj: P 7714/2026", "Predmet: P 7714/2026"])
def test_sud_ne_uzima_rec_iz_sledeceg_reda(sledeci_red):
    assert extract_court(f"OSNOVNI SUD U BEOGRADU\n{sledeci_red}") == ("OSNOVNI SUD U BEOGRADU", 0.9)
    assert extract_court(f"Osnovni sud u Beogradu\n{sledeci_red}") == ("Osnovni sud u Beogradu", 0.9)


def test_sud_zlatni_slucaj_zaglavlje():
    assert extract_court(ZAGLAVLJE) == ("OSNOVNI SUD U BEOGRADU", 0.9)


@pytest.mark.parametrize("tekst", [
    "Ugovor o radu zaključen je u Beogradu.",                 # nema suda
    "Osnovni sud u ovom trenutku nije dostupan.",             # grad nije reč sa velikim slovom
    "OSNOVNI SUD U\nPosl. br. P 7714/2026",                   # grad bi bio izmišljen iz sledećeg reda
    "0SNOVNI SUD U BE0GRADU",                                 # OCR šum: nula umesto O
])
def test_sud_bez_pouzdanog_izmisljanja(tekst):
    vrednost, pouzdanost = extract_court(tekst)
    assert vrednost is None and pouzdanost == 0.0, vrednost


def _broj_i_valuta(vrednost):
    """Semantika, ne samo neprazan string: srpski zapis (tačka = hiljade, zarez = decimale) → Decimal + valuta."""
    broj, valuta = vrednost.rsplit(" ", 1)
    return Decimal(broj.replace(".", "").replace(",", ".")), valuta


@pytest.mark.parametrize("tekst, broj, valuta", [
    ("Obavezuje se tuzeni da isplati 350.000,00 dinara.", Decimal("350000.00"), "dinara"),
    ("isplati iznos od 350.000 dinara", Decimal("350000"), "dinara"),
    ("na ime troskova 350.000,00 din. sa kamatom", Decimal("350000.00"), "din"),
    ("ukupno 350.000 RSD", Decimal("350000"), "RSD"),
    ("Tužilac potražuje iznos od 48.200,00 РСД.", Decimal("48200.00"), "РСД"),
    ("Тужени да исплати 12.500,00 динара.", Decimal("12500.00"), "динара"),
    ("cena 1.200,00 EUR po komadu", Decimal("1200.00"), "EUR"),
])
def test_iznos_broj_i_valuta(tekst, broj, valuta):
    vrednost, pouzdanost = extract_amount(tekst)
    assert pouzdanost == 0.92 and _broj_i_valuta(vrednost) == (broj, valuta), vrednost


@pytest.mark.parametrize("tekst", [
    "Posl. br. P 7714/2026",                       # broj predmeta
    "Presuda je doneta 20.10.2026. godine.",        # datum
    "Vidi tačku 48.200 pravilnika.",                 # broj bez valute
    "prema dokumentu br. 12.345/26",                 # oznaka dokumenta
    "isplati 350.00,00 dinara",                      # pogrešno zapisan iznos — ni rep „00,00 dinara“
])
def test_iznos_nije_izmisljen(tekst):
    assert extract_amount(tekst) == (None, 0.0)


def test_iznos_pripada_samo_svom_dokumentu(monkeypatch):
    async def _bez_llm(_t):
        return {}
    monkeypatch.setattr(ex, "extract_free_text_entities", _bez_llm)
    sa = asyncio.run(ex.extract_all_entities("Obavezuje se tuzeni da isplati 350.000,00 dinara."))
    bez = asyncio.run(ex.extract_all_entities("DOSTAVNICA\nUruceno dana 24.10.2026. godine."))
    iznos = {e["entity_type"]: e["value"] for e in sa}["amount"]
    assert _broj_i_valuta(iznos) == (Decimal("350000.00"), "dinara")
    assert {e["entity_type"]: e["value"] for e in bez}["amount"] is None
