# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — deterministička ekstrakcija iz prijema (BA-03, BA-05).

Task 2: sud ne sme da pređe u sledeći red zaglavlja („OSNOVNI SUD U BEOGRADU\\nPosl. br.“ → „… Posl“, 0.90).
"""
import pytest

from shared.intake_extract import extract_court

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
