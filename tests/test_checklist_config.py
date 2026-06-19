# -*- coding: utf-8 -*-
"""
Tests za nacrti/checklist_config.py — validacija svih 21 tipova.

Pokriva:
  - Svi tipovi imaju obavezna polja (naziv, vrsta_spora, elementi)
  - Svaki element ima naziv, pitanje, kljucne_reci, kriticnost, razlog
  - kriticnost je jedna od: visoka / srednja / niska
  - Svaki tip ima barem 1 element sa kriticnost=visoka
  - get_config(tip) vraća ispravnu strukturu
  - get_config na nepostojećem tipu baca KeyError
  - SVI_TIPOVI sadrži sve tipove
"""
import pytest
from nacrti.checklist_config import CHECKLIST, SVI_TIPOVI, get_config

_VALID_KRITICNOST = {"visoka", "srednja", "niska"}

_OCEKIVANI_TIPOVI = [
    "tuzba_naknada_stete",
    "tuzba_radni_spor",
    "zalba_parnicna",
    "zalba_na_presudu",
    "zalba_na_resenje",
    "predlog_izvrsenje",
    "tuzba_razvod",
    "krivicna_prijava",
    "tuzba_ugovorni_spor",
    "prigovor_platni_nalog",
    "predlog_privremena_mera",
    "opomena_duznik",
    "zahtev_poslodavcu",
    "ugovor_neodredjeno",
    "ugovor_odredjeno",
    "sporazumni_raskid",
    "ugovor_kupoprodaja",
    "ugovor_zakup",
    "punomocje",
    "aneks",
    "obaveštenje_o_otkazu",
]


def test_svi_tipovi_count():
    assert len(SVI_TIPOVI) == 21, f"Očekivano 21 tipova, pronađeno {len(SVI_TIPOVI)}"


def test_svi_ocekivani_tipovi_prisutni():
    missing = [t for t in _OCEKIVANI_TIPOVI if t not in SVI_TIPOVI]
    assert not missing, f"Nedostaju tipovi: {missing}"


@pytest.mark.parametrize("tip", list(CHECKLIST.keys()))
def test_tip_ima_obavezna_polja(tip):
    cfg = CHECKLIST[tip]
    assert "naziv" in cfg and cfg["naziv"], f"{tip}: nema 'naziv'"
    assert "vrsta_spora" in cfg and cfg["vrsta_spora"], f"{tip}: nema 'vrsta_spora'"
    assert "elementi" in cfg and cfg["elementi"], f"{tip}: nema 'elementi' ili je prazan"


@pytest.mark.parametrize("tip", list(CHECKLIST.keys()))
def test_tip_elementi_imaju_obavezna_polja(tip):
    elementi = CHECKLIST[tip]["elementi"]
    for i, e in enumerate(elementi):
        assert "naziv" in e and e["naziv"], f"{tip}[{i}]: nema 'naziv'"
        assert "pitanje" in e, f"{tip}[{i}]: nema 'pitanje'"
        assert "kljucne_reci" in e and isinstance(e["kljucne_reci"], list), f"{tip}[{i}]: nema 'kljucne_reci'"
        assert len(e["kljucne_reci"]) > 0, f"{tip}[{i}]: prazna lista 'kljucne_reci'"
        assert "kriticnost" in e, f"{tip}[{i}]: nema 'kriticnost'"
        assert "razlog" in e and e["razlog"], f"{tip}[{i}]: nema 'razlog'"


@pytest.mark.parametrize("tip", list(CHECKLIST.keys()))
def test_kriticnost_su_validne_vrednosti(tip):
    elementi = CHECKLIST[tip]["elementi"]
    for i, e in enumerate(elementi):
        assert e["kriticnost"] in _VALID_KRITICNOST, (
            f"{tip}[{i}]: kriticnost='{e['kriticnost']}' nije validna ({_VALID_KRITICNOST})"
        )


@pytest.mark.parametrize("tip", list(CHECKLIST.keys()))
def test_tip_ima_barem_jedan_visoki_element(tip):
    elementi = CHECKLIST[tip]["elementi"]
    visoki = [e for e in elementi if e["kriticnost"] == "visoka"]
    assert len(visoki) >= 1, f"{tip}: nema nijednog elementa sa kriticnost='visoka'"


def test_get_config_vraca_ispravan_tip():
    cfg = get_config("tuzba_naknada_stete")
    assert cfg["naziv"] == "Tužba za naknadu štete"
    assert len(cfg["elementi"]) >= 5


def test_get_config_nepostojeci_tip_baca_key_error():
    with pytest.raises(KeyError) as exc:
        get_config("nepostojeci_tip")
    assert "nepostojeci_tip" in str(exc.value)


def test_kljucne_reci_su_lowercase():
    """Ključne reči moraju biti lowercase jer se poredi sa .lower() verzijom teksta."""
    for tip, cfg in CHECKLIST.items():
        for e in cfg["elementi"]:
            for kw in e["kljucne_reci"]:
                assert kw == kw.lower(), (
                    f"{tip} — ključna reč '{kw}' nije lowercase"
                )


def test_svaki_tip_ima_minimum_2_elementa():
    for tip, cfg in CHECKLIST.items():
        assert len(cfg["elementi"]) >= 2, f"{tip}: premalo elemenata (min. 2)"
