# -*- coding: utf-8 -*-
"""Email podsetnici — oblik odgovora `send-reminders` (night/deadlines-alerts-vcr002, T05/T06).

Poziva stvarni `routers.email_notif.posalji_podsetnike` nad `test_b10_reminder_claim.FakeBaza`;
SMTP je uvek zamenjen. Svaki odgovor ima ista 4 nenegativna cela brojača koje cron proverava."""
import pytest

from tests import test_b10_reminder_claim as b10

POLJA = ("poslato", "greske", "preskoceno", "neisporuceno")


def _oblik(rez):
    assert isinstance(rez, dict)
    for p in POLJA:
        assert type(rez.get(p)) is int and rez[p] >= 0, (p, rez)
    return {p: rez[p] for p in POLJA}


@pytest.fixture(autouse=True)
def _potvrdjeno(monkeypatch):
    import routers.email_notif as en
    monkeypatch.setattr(en, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})


def test_nema_aktivnih_profila_ima_sva_cetiri_brojaca_i_napomenu():
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    baza.tabele["korisnik_email_notif"] = []
    rez, poslati = b10._pokreni(baza)
    assert _oblik(rez) == dict.fromkeys(POLJA, 0)
    assert rez["napomena"] == "Nema aktivnih profila"
    assert poslati == [] and baza.log == []


def test_uobicajen_uspeh_ima_isti_oblik():
    rez, poslati = b10._pokreni(b10.FakeBaza([b10._rok(b10._sutra())]))
    assert _oblik(rez) == {"poslato": 1, "greske": 0, "preskoceno": 0, "neisporuceno": 0}
    assert "napomena" not in rez and len(poslati) == 1


def test_smtp_pad_ostaje_nepotvrden_ne_uspeh():
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    rez, poslati = b10._pokreni(baza, smtp_puca=True)
    assert _oblik(rez) == {"poslato": 0, "greske": 0, "preskoceno": 0, "neisporuceno": 1}
    assert poslati == [] and len(baza.log) == 1          # rezervacija ostaje, bez automatskog ponavljanja


def test_pad_rezervacije_je_greska_bez_slanja():
    baza = b10.FakeBaza([b10._rok(b10._sutra())])
    baza.insert_puca = True
    rez, poslati = b10._pokreni(baza)
    assert _oblik(rez) == {"poslato": 0, "greske": 1, "preskoceno": 0, "neisporuceno": 0}
    assert poslati == []
