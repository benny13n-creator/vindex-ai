# -*- coding: utf-8 -*-
"""V4 — provera stava sudske prakse (`main._proveri_stavove_prakse`): stav pripisan odluci mora biti podržan
sažetkom te odluke iz konteksta koji je model video — uključujući SMER (negaciju), ne samo zajedničke reči.

Izmereno pre ispravke: „nije“ je bio u stop-listi, „ne“ kraće od 4 slova, pa je „poslodavac MOŽE da otkaže … za vreme
trudnoće“ prolazio kao podržan sažetkom „poslodavac NE MOŽE da otkaže … za vreme trudnoće“."""
import pytest

import main

KONTEKST = """SUDSKA PRAKSA:
1. Vrhovni sud, Rev2 1234/2020, 12.03.2021
   Sažetak: Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće i porodiljskog odsustva. Otkaz dat suprotno članu 187 Zakona o radu je nezakonit.
2. Apelacioni sud u Beogradu, Gž1 555/2019, 01.02.2020
   Sažetak: Zastarelost potraživanja naknade štete počinje da teče od dana saznanja za štetu i učinioca, prema članu 376 Zakona o obligacionim odnosima.
"""


def _stav(broj, princip, relevantnost=""):
    return {"broj_odluke": broj, "pravni_princip": princip, "sazetak_relevantnosti": relevantnost}


def _ostaje(*stavovi):
    data = {"pravni_zakljucak": "x", "sudska_praksa": list(stavovi)}
    return [s["broj_odluke"] for s in main._proveri_stavove_prakse(data, KONTEKST)["sudska_praksa"]]


def test_podrzan_stav_ostaje():
    assert _ostaje(_stav("Rev2 1234/2020", "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.")) == ["Rev2 1234/2020"]


def test_izricito_negiran_stav_se_uklanja():
    assert _ostaje(_stav("Rev2 1234/2020", "Poslodavac može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.")) == []


def test_obrnuta_negacija_se_uklanja():
    assert _ostaje(_stav("Gž1 555/2019", "Zastarelost potraživanja naknade štete ne počinje da teče od dana saznanja za štetu.")) == []


def test_nepovezan_stav_se_uklanja():
    assert _ostaje(_stav("Gž1 555/2019", "Ugovor o zakupu stana mora biti overen kod javnog beležnika.")) == []


def test_odluka_koje_nema_u_kontekstu_se_uklanja():
    assert _ostaje(_stav("Rev 9999/2022", "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.")) == []


def test_negacija_u_obrazlozenju_relevantnosti_ne_obrce_stav():
    """Smer se meri na PRIPISANOM STAVU (pravni_princip), ne na objašnjenju zašto je odluka relevantna."""
    assert _ostaje(_stav("Gž1 555/2019", "Zastarelost potraživanja naknade štete počinje da teče od dana saznanja za štetu i učinioca.",
                         "Klijent nije znao za štetu do prošle godine.")) == ["Gž1 555/2019"]


@pytest.mark.parametrize("princip", [
    "Poslodavac nije ovlašćen da otkaže ugovor o radu zaposlenoj za vreme trudnoće.",
    "Zaposlenoj se ne sme otkazati ugovor o radu za vreme trudnoće.",
])
def test_ista_negacija_drugim_recima_ostaje(princip):
    assert _ostaje(_stav("Rev2 1234/2020", princip)) == ["Rev2 1234/2020"]


def test_polaritet_cirilica():
    k = KONTEKST.replace("Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće",
                         "Послодавац не може да откаже уговор о раду запосленој за време трудноће")
    data = {"sudska_praksa": [_stav("Rev2 1234/2020", "Poslodavac može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.")]}
    assert main._proveri_stavove_prakse(data, k)["sudska_praksa"] == []


# ── revizija V4: smer se meri na KLAUZULI sažetka, ne na celoj rečenici; i negacija u prefiksu („nedopuštena“) ──

def _kontekst(sazetak):
    return f"SUDSKA PRAKSA:\n1. Vrhovni sud, Rev 77/2021, 01.01.2021\n   Sažetak: {sazetak}\n"


def _ostaje_uz(sazetak, princip):
    data = {"sudska_praksa": [_stav("Rev 77/2021", princip)]}
    return bool(main._proveri_stavove_prakse(data, _kontekst(sazetak))["sudska_praksa"])


@pytest.mark.parametrize("sazetak,princip", [
    ("Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu, a ne od dana nastanka štete.",
     "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu."),
    ("Poslodavac odgovara za štetu koju zaposleni pretrpi na radu ne samo kada je kriv, već i po principu objektivne odgovornosti.",
     "Poslodavac odgovara za štetu koju zaposleni pretrpi na radu po principu objektivne odgovornosti."),
])
def test_kontrastna_negacija_ne_uklanja_podrzan_stav(sazetak, princip):
    assert _ostaje_uz(sazetak, princip)


@pytest.mark.parametrize("sazetak,princip", [
    ("Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu, a ne od dana nastanka štete.",
     "Rok zastarelosti potraživanja naknade štete teče od dana nastanka štete."),
    ("Revizija je nedopuštena kada vrednost predmeta spora ne prelazi propisani iznos.",
     "Revizija je dopuštena kada vrednost predmeta spora prelazi propisani iznos."),
    ("Otkaz ugovora o radu dat zaposlenoj za vreme trudnoće je nezakonit.",
     "Otkaz ugovora o radu dat zaposlenoj za vreme trudnoće je zakonit."),
])
def test_obrnut_smer_u_klauzuli_ili_prefiksu_se_uklanja(sazetak, princip):
    assert not _ostaje_uz(sazetak, princip)
