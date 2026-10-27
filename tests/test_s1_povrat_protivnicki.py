# -*- coding: utf-8 -*-
"""S1-C5 — KZ čl. 55a: protivnički ulazi iz nezavisne revizije Sektora 1. Načelo modula: činjenica koja nije
jednoznačna daje NEPOZNATO — nikad DA ni NE."""
import pytest

from shared import visestruki_povrat as V

NOVO = "Sada je sa umišljajem izvršio krađu, propisan je zatvor od jedne do osam godina. 55a?"


def _ishod(q):
    return V.izracunaj(**V.iz_pitanja(q)).primenjuje_se


def _uslov(q, i):
    return V.izracunaj(**V.iz_pitanja(q)).uslovi[i].stanje


@pytest.mark.parametrize("q", [
    # H1: „otpušten pre N“ se meri od danas, a novo delo ima SVOJE vreme — razlika nije navedena
    "Okrivljeni je dva puta osuđen za umišljajna krivična dela na zatvor od po dve godine. Otpušten je sa izdržavanja "
    "kazne pre šest godina. Novo delo je sa umišljajem izvršio pre dve godine; propisan je zatvor od jedne do osam godina. "
    "Kakav je raspon po 55a?",
    # H2: datum suđenja nije datum dela; delo je navedeno samo godinom
    "Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine. Otpušten je 01.01.2019. Sada mu se sudi "
    "na ročištu 15.03.2025 za krađu sa umišljajem koju je izvršio 2021, propisan je zatvor od jedne do osam godina. 55a?",
    # delo izvršeno pre otpusta (tokom bekstva)
    "Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine. Otpušten je pre dve godine. Ponovo je sa "
    "umišljajem izvršio krađu, ali delo je izvršio pre otpusta, tokom bekstva. Propisan je zatvor od jedne do osam godina. 55a?",
])
def test_vreme_od_otpusta_do_novog_dela_nije_jednoznacno(q):
    assert _uslov(q, 3) == V.NEPOZNATO and _ishod(q) == V.NEPOZNATO


@pytest.mark.parametrize("q", [
    # H3a: zagrada menja krivicu jedne od ranijih osuda
    "Okrivljeni je dva puta osuđen za umišljajna dela (drugo delo je bilo iz nehata) na zatvor od po dve godine. "
    "Otpušten je pre dve godine. " + NOVO,
    # H3b: umišljaj iz rečenice o NOVOM delu ne pripada ranijim osudama
    "Okrivljeni je umišljajno izvršio tešku krađu. Dva puta je ranije osuđen na zatvor od po dve godine. Otpušten je pre "
    "dve godine. Novo delo je učinio sa umišljajem, propisan je zatvor od jedne do osam godina. Da li se primenjuje 55a?",
    # osuda brisana / maloletnički zatvor / kazna zamenjena radom u javnom interesu
    "Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine, ali je jedna osuda brisana iz kaznene "
    "evidencije. Otpušten je pre dve godine. " + NOVO,
    "Okrivljeni je dva puta osuđen kao maloletnik za umišljajna dela na maloletnički zatvor od po dve godine. Otpušten je "
    "pre dve godine. " + NOVO,
    "Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine, ali mu je kazna zamenjena radom u javnom "
    "interesu. Otpušten je pre dve godine. " + NOVO,
])
def test_ranije_osude_nisu_jednoznacne(q):
    assert _uslov(q, 2) == V.NEPOZNATO and _ishod(q) == V.NEPOZNATO


def test_jednoznacan_slucaj_i_dalje_DA():
    q = ("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, sa izdržavanja "
         "kazne je otpušten pre tri godine, a sada je sa umišljajem izvršio tešku krađu za koju je propisan zatvor od jedne "
         "do osam godina. U kom rasponu sud mora da izrekne kaznu?")
    assert _ishod(q) == V.DA


def test_datum_dela_uz_glagol_izvrsenja_i_dalje_racuna():
    q = ("Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem. Otpušten je sa "
         "izdržavanja kazne 01.03.2020. Novo delo, tešku krađu, izvršio je sa umišljajem 15.01.2024, a propisan je zatvor "
         "od jedne do osam godina. U kom rasponu?")
    assert _uslov(q, 3) == V.DA


# ── revizija S1 ispravki: ni DA za dvosmisleno, ni NEPOZNATO za jednoznačno ──

OSUDE = "Okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine."


@pytest.mark.parametrize("q", [
    OSUDE + " Jedno od tih dela je ipak bilo iz nehata. Otpušten je pre dve godine. " + NOVO,
    "Okrivljeni je dva puta osuđen na zatvor od po dve godine, jednom za umišljajnu krađu. Drugo delo je izvršio iz "
    "nehata. Otpušten je pre dve godine. " + NOVO,
])
def test_protivrecna_krivica_posle_recenice_osude_nije_DA(q):
    assert _uslov(q, 2) == V.NEPOZNATO and _ishod(q) == V.NEPOZNATO


@pytest.mark.parametrize("q", [
    "Prema izvodu iz kaznene evidencije, okrivljeni je dva puta osuđen za umišljajna dela na zatvor od po dve godine. "
    "Otpušten je pre dve godine. " + NOVO,
    OSUDE + " Otpušten je pre dve godine. Sada je sa umišljajem izvršio krađu na štetu maloletnog lica, propisan je "
    "zatvor od jedne do osam godina. 55a?",
    "Okrivljeni je dva puta osuđen na zatvor od po dve godine. Oba dela su učinjena sa umišljajem. Otpušten je pre dve "
    "godine. " + NOVO,
    OSUDE + " Otpušten je pre dve godine. Sada je sa umišljajem izvršio krađu iz člana 204 KZ (Sl. glasnik RS 94/2016), "
    "propisan je zatvor od jedne do osam godina. 55a?",
    "Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, sa izdržavanja "
    "kazne je otpušten pre tri godine, a sada je sa umišljajem izvršio tešku krađu za koju je propisan zatvor od jedne "
    "do osam godina. U kom rasponu sud mora da izrekne kaznu?",
])
def test_jednoznacan_slucaj_ostaje_DA(q):
    assert _ishod(q) == V.DA


@pytest.mark.parametrize("q", [
    OSUDE + " Otpušten je pre dve godine. Prošle godine je sa umišljajem izvršio krađu, propisan je zatvor od jedne do "
    "osam godina. 55a?",
    OSUDE + " Otpušten je pre dve godine. Sada je utvrđeno da je sa umišljajem izvršio krađu dok je još bio na "
    "izdržavanju kazne, propisan je zatvor od jedne do osam godina. 55a?",
])
def test_vreme_novog_dela_nije_jednoznacno(q):
    assert _uslov(q, 3) == V.NEPOZNATO
