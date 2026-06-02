# -*- coding: utf-8 -*-
"""Tests for P4.6 — letter templates: opomena, zahtev, obaveštenje."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from drafting.templates import TEMPLATES

_P46_TYPES = ["opomena_duznik", "zahtev_poslodavcu", "obaveštenje_o_otkazu"]


def test_opomena_duznik_u_templates():
    assert "opomena_duznik" in TEMPLATES


def test_zahtev_poslodavcu_u_templates():
    assert "zahtev_poslodavcu" in TEMPLATES


def test_obavestenje_o_otkazu_u_templates():
    assert "obaveštenje_o_otkazu" in TEMPLATES


def test_sva_p46_polja_prisutna():
    for vrsta in _P46_TYPES:
        entry = TEMPLATES[vrsta]
        assert entry.get("label"), f"{vrsta}: label missing"
        assert entry.get("ekstrakcioni_prompt"), f"{vrsta}: ekstrakcioni_prompt missing"
        assert entry.get("sablon"), f"{vrsta}: sablon missing"
        assert entry.get("opis_hint"), f"{vrsta}: opis_hint missing"


def test_opomena_sablon_sadrzi_kljucne_placeholdere():
    sablon = TEMPLATES["opomena_duznik"]["sablon"]
    assert "{POVERILAC_IME}" in sablon
    assert "{IZNOS_DUGA}" in sablon
    assert "{ROK_PLACANJA}" in sablon


def test_zahtev_sablon_sadrzi_kljucne_placeholdere():
    sablon = TEMPLATES["zahtev_poslodavcu"]["sablon"]
    assert "{ZAPOSLENI_IME}" in sablon
    assert "{PREDMET_ZAHTEVA}" in sablon
    assert "{ROK_ODGOVORA}" in sablon


def test_obavestenje_sablon_sadrzi_kljucne_placeholdere():
    sablon = TEMPLATES["obaveštenje_o_otkazu"]["sablon"]
    assert "{STRANA_KOJA_OTKAZUJE}" in sablon
    assert "{OTKAZNI_ROK}" in sablon
    assert "{RAZLOG}" in sablon


def test_ukupno_12_tipova():
    assert len(TEMPLATES) == 12, f"Expected 12 templates, got {len(TEMPLATES)}"
