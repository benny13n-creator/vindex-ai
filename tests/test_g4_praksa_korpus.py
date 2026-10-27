# -*- coding: utf-8 -*-
"""G4 — ograničen adversarijalni korpus (sažetak odluke ↔ stav koji mu model pripisuje).

Oznaka svakog para je određena KONSTRUKCIJOM (stav je ili preformulacija ili inverzija/proširenje ISTOG sažetka), ne
tumačenjem modela. Dva nivoa ugovora:
  1. Provera (`_proveri_stavove_prakse`) je heuristika (preklop reči + smer klauzule). Meri se: koliko podržanih ostaje,
     koliko nepodržanih se uklanja; parovi koje heuristika NE razlikuje su popisani kao poznata granica.
  2. Invarijanta prikaza (G4): ZADRŽANA odluka se nikad ne prikazuje samo AI parafrazom — uz nju ide DOSLOVAN sažetak
     iz baze, a parafraza je izričito označena kao „AI sažetak — nije potvrđen kao stav suda“. Tako ni par koji provera
     propusti ne dobija status potvrđenog stava suda: advokat vidi izvorni tekst."""
import pytest

import main

S_TRUDNOCA = "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće i porodiljskog odsustva."
S_ZASTARELOST = "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu, a ne od dana nastanka štete."
S_REVIZIJA = "Revizija je nedopuštena kada vrednost predmeta spora ne prelazi propisani iznos."
S_IZUZETAK = "Zakupodavac može otkazati ugovor o zakupu pre isteka roka samo ako zakupac ne plati zakupninu ni posle opomene."
S_OBJEKTIVNA = "Poslodavac odgovara za štetu koju zaposleni pretrpi na radu ne samo kada je kriv, već i po principu objektivne odgovornosti."
S_SVEDOK = "Sud ne može odbiti da sasluša svedoka kojeg je stranka blagovremeno predložila."
S_USKO = "Ugovor o zajmu između fizičkih lica zaključen usmeno je punovažan."
S_UPRAVNI = "U upravnom sporu tužba ne odlaže izvršenje osporenog rešenja."
S_CIR = "Послодавац не може да откаже уговор о раду запосленој за време трудноће."
S_IZDVOJENO = "Veće je odbilo žalbu; u izdvojenom mišljenju jedan sudija navodi da je tužba trebalo da bude usvojena."

# (sažetak, pripisan stav, treba_da_ostane, kategorija)
KORPUS = [
    (S_TRUDNOCA, "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", True, "podrška"),
    (S_TRUDNOCA, "Poslodavac može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", False, "izričita negacija"),
    (S_CIR, "Poslodavac može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", False, "ćirilica, negacija"),
    (S_CIR, "Poslodavac ne može da otkaže ugovor o radu zaposlenoj za vreme trudnoće.", True, "ćirilica, podrška"),
    (S_ZASTARELOST, "Rok zastarelosti potraživanja naknade štete teče od dana saznanja za štetu.", True, "kontrast — podržana grana"),
    (S_ZASTARELOST, "Rok zastarelosti potraživanja naknade štete teče od dana nastanka štete.", False, "kontrast — isključena grana"),
    (S_REVIZIJA, "Revizija je dopuštena kada vrednost predmeta spora ne prelazi propisani iznos.", False, "prefiks ne-"),
    (S_REVIZIJA, "Revizija je nedopuštena kada vrednost predmeta spora ne prelazi propisani iznos.", True, "prefiks ne-, podrška"),
    (S_OBJEKTIVNA, "Poslodavac odgovara za štetu koju zaposleni pretrpi na radu po principu objektivne odgovornosti.", True, "ne samo … već"),
    (S_USKO, "Ugovor o zajmu zaključen usmeno je punovažan.", True, "uži stav, preformulisan"),
    (S_UPRAVNI, "Tužba u upravnom sporu odlaže izvršenje osporenog rešenja.", False, "negacija, drugi red reči"),
    (S_UPRAVNI, "Ugovor o zakupu stana mora biti overen kod javnog beležnika.", False, "nepovezan stav"),
    (S_ZASTARELOST, "Rok zastarelosti potraživanja naknade štete ne teče od dana saznanja za štetu.", False, "negacija podržane grane"),
    (S_IZUZETAK, "Zakupodavac može otkazati ugovor o zakupu pre isteka roka.", False, "izuzetak izostavljen (preširoko)"),
]

# Parovi koje heuristika NE razlikuje (poznata granica, merena — ne skrivena). Invarijanta prikaza ih pokriva.
GRANICA = [
    (S_SVEDOK, "Sud mora da sasluša svedoka kojeg je stranka blagovremeno predložila.", "dvostruka negacija = podrška, a uklanja se"),
    (S_USKO, "Svaki ugovor zaključen usmeno je punovažan.", "preopšte proširenje"),
    (S_IZDVOJENO, "Tužba je trebalo da bude usvojena.", "izdvojeno mišljenje, ne stav veća"),
]


def _kontekst(sazetak):
    return f"SUDSKA PRAKSA:\n1. Vrhovni sud, Rev 77/2021, 01.01.2021\n   Sažetak: {sazetak}\n"


def _proveri(sazetak, stav):
    data = {"pravni_zakljucak": "x", "sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Rev 77/2021",
                                                          "pravni_princip": stav}]}
    return main._proveri_stavove_prakse(data, _kontekst(sazetak))


@pytest.mark.parametrize("sazetak,stav,ostaje,kategorija", KORPUS, ids=[k[3] for k in KORPUS])
def test_korpus_provera(sazetak, stav, ostaje, kategorija):
    assert bool(_proveri(sazetak, stav)["sudska_praksa"]) is ostaje


def test_granica_heuristike_je_izmerena():
    """Ako se heuristika promeni, ovaj popis se mora svesno ažurirati (test pada na svaku promenu ishoda)."""
    ishod = {opis: bool(_proveri(s, st)["sudska_praksa"]) for s, st, opis in GRANICA}
    assert ishod == {"dvostruka negacija = podrška, a uklanja se": False,
                     "preopšte proširenje": True, "izdvojeno mišljenje, ne stav veća": True}


@pytest.mark.parametrize("sazetak,stav", [(s, st) for s, st, o, _ in KORPUS if o] + [(s, st) for s, st, _ in GRANICA])
def test_zadrzan_stav_nikad_bez_doslovnog_sazetka_i_oznake(sazetak, stav):
    data = _proveri(sazetak, stav)
    if data["sudska_praksa"]:
        data["sudska_praksa"][0].update(primena_na_predmet="Odluka potvrđuje stav.", sazetak_relevantnosti="Relevantno.")
    if not data["sudska_praksa"]:
        return                                                   # uklonjen — ništa se ne prikazuje kao stav suda
    tekst = main._json_ka_tekst(data, "PARNICA")
    deo = tekst[tekst.index("--- SUDSKA PRAKSA"):]
    assert f"Iz sažetka odluke (doslovno, baza Vindex): „{sazetak}“" in deo
    assert "AI sažetak — nije potvrđen kao stav suda" in deo
    assert "   Pravni princip: " not in deo                     # neoznačena AI formulacija se ne prikazuje
    assert "   Primena (AI): Odluka potvrđuje stav." in deo and "   AI: Relevantno." in deo


def test_odluka_van_konteksta_se_ne_prikazuje():
    data = {"sudska_praksa": [{"sud": "Vrhovni sud", "broj_odluke": "Rev 9999/2022", "pravni_princip": S_USKO}]}
    assert main._proveri_stavove_prakse(data, _kontekst(S_USKO))["sudska_praksa"] == []


def test_mera_korpusa():
    podrzani = [(s, st) for s, st, o, _ in KORPUS if o]
    nepodrzani = [(s, st) for s, st, o, _ in KORPUS if not o]
    zadrzano = sum(bool(_proveri(s, st)["sudska_praksa"]) for s, st in podrzani)
    uklonjeno = sum(not _proveri(s, st)["sudska_praksa"] for s, st in nepodrzani)
    assert (zadrzano, len(podrzani), uklonjeno, len(nepodrzani)) == (6, 6, 8, 8)
