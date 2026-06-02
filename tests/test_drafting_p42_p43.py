# -*- coding: utf-8 -*-
"""Tests for P4.2+P4.3 — zalba and tuzba templates in drafting module."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from drafting.templates import TEMPLATES, get_types_list

_NEW_TYPES = ["zalba_na_presudu", "zalba_na_resenje", "tuzba_naknada_stete", "tuzba_radni_spor"]
_ALL_EXPECTED = [
    "ugovor_neodredjeno", "ugovor_odredjeno", "aneks",
    "sporazumni_raskid", "punomocje",
] + _NEW_TYPES


# ─── T1: Sva 4 nova tipa postoje u TEMPLATES ─────────────────────────────────

@pytest.mark.parametrize("vrsta", _NEW_TYPES)
def test_novi_tip_postoji_u_templates(vrsta):
    """Svaki novi tip mora biti prisutan u TEMPLATES registru."""
    assert vrsta in TEMPLATES, f"'{vrsta}' not found in TEMPLATES"


# ─── T2: Svaki novi tip ima label, ekstrakcioni_prompt, sablon ───────────────

@pytest.mark.parametrize("vrsta", _NEW_TYPES)
def test_novi_tip_ima_obavezna_polja(vrsta):
    """Svaki novi template mora imati label, ekstrakcioni_prompt i sablon."""
    entry = TEMPLATES[vrsta]
    assert entry.get("label"), f"{vrsta}: label missing or empty"
    assert entry.get("ekstrakcioni_prompt"), f"{vrsta}: ekstrakcioni_prompt missing or empty"
    assert entry.get("sablon"), f"{vrsta}: sablon missing or empty"


@pytest.mark.parametrize("vrsta", _NEW_TYPES)
def test_novi_tip_ima_opis_hint(vrsta):
    """Svaki novi template mora imati opis_hint za UI."""
    entry = TEMPLATES[vrsta]
    assert entry.get("opis_hint"), f"{vrsta}: opis_hint missing"


# ─── T3: Labels su srpski tekst ───────────────────────────────────────────────

def test_zalba_na_presudu_label():
    assert "Žalba" in TEMPLATES["zalba_na_presudu"]["label"]
    assert "presudu" in TEMPLATES["zalba_na_presudu"]["label"].lower()


def test_zalba_na_resenje_label():
    assert "Žalba" in TEMPLATES["zalba_na_resenje"]["label"]
    assert "rešenje" in TEMPLATES["zalba_na_resenje"]["label"].lower()


def test_tuzba_naknada_stete_label():
    assert "Tužba" in TEMPLATES["tuzba_naknada_stete"]["label"]


def test_tuzba_radni_spor_label():
    assert "Tužba" in TEMPLATES["tuzba_radni_spor"]["label"]
    assert "radni" in TEMPLATES["tuzba_radni_spor"]["label"].lower()


# ─── T4: Šabloni sadrže ključne pravne reference ─────────────────────────────

def test_zalba_na_presudu_sablon_sadrzi_zpp():
    sablon = TEMPLATES["zalba_na_presudu"]["sablon"]
    assert "ZPP" in sablon or "parničnom postupku" in sablon.lower()
    assert "{RAZLOZI_ZALBE}" in sablon
    assert "{PREDLOG}" in sablon


def test_zalba_na_resenje_sablon_sadrzi_zup():
    sablon = TEMPLATES["zalba_na_resenje"]["sablon"]
    assert "ZUP" in sablon or "upravnom postupku" in sablon.lower()
    assert "{RAZLOZI_ZALBE}" in sablon
    assert "15 dana" in sablon


def test_tuzba_naknada_stete_sablon_sadrzi_zoo():
    sablon = TEMPLATES["tuzba_naknada_stete"]["sablon"]
    assert "ZOO" in sablon or "obligacionim" in sablon.lower()
    assert "154" in sablon
    assert "{IZNOS_STETE}" in sablon


def test_tuzba_radni_spor_sablon_sadrzi_zr():
    sablon = TEMPLATES["tuzba_radni_spor"]["sablon"]
    assert "radu" in sablon.lower()
    assert "195" in sablon
    assert "{ZAHTEV}" in sablon


# ─── T5: get_types_list vraća svih 9 tipova ──────────────────────────────────

def test_get_types_list_vraca_9_tipova():
    """get_types_list() mora sadržati barem 9 tipova (P4.6 dodao još 3)."""
    types = get_types_list()
    assert len(types) >= 9, f"Expected at least 9 types, got {len(types)}"


def test_get_types_list_sadrzi_sve_expected_tipove():
    """get_types_list() mora sadržati sve očekivane vrste."""
    kinds = {t["vrsta"] for t in get_types_list()}
    for expected in _ALL_EXPECTED:
        assert expected in kinds, f"'{expected}' missing from get_types_list()"


def test_get_types_list_svaki_ima_label_i_opis_hint():
    """Svaki element iz get_types_list mora imati vrsta, label i opis_hint."""
    for t in get_types_list():
        assert t.get("vrsta"), f"Missing 'vrsta' in {t}"
        assert t.get("label"), f"Missing 'label' in {t}"
        assert t.get("opis_hint"), f"Missing 'opis_hint' in {t}"
