# -*- coding: utf-8 -*-
"""G2 — raspored i identitet podsetnika nad stvarnom `posalji_podsetnike` (lažna baza, lažan SMTP, simulirani dani).

Utvrđen ugovor (migracija 021 UNIQUE(user_id, predmet_id, datum_roka, dana_pre); B10 „at-most-once pokušaj slanja“;
N4 „već poslato“ po predmetu): JEDAN grupisan podsetnik po predmetu, datumu događaja i pragu (1/3/7 dana), sa svim
tada izvršivim događajima tog predmeta i datuma. Raspored u produkciji: jedno zakazano slanje dnevno
(`.github/workflows/email-cron.yml`, 08:00 UTC); `/api/cron/daily` nije zakazan (cron_runs: 5 ručnih pokretanja,
sva 2026-07-24). NIJEDAN test ne šalje pravi email."""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10
from tests.test_n4_podsetnici import PID, _pokreni, _roc, _rok

DAN0 = date(2026, 11, 2)          # ponedeljak — fiksiran, nezavisan od stvarnog datuma


def _dan(n):
    return (DAN0 + timedelta(days=n)).isoformat()


class _Dan(date):
    pomak = 0

    @classmethod
    def today(cls):
        return DAN0 + timedelta(days=cls.pomak)


def _na_dan(n, b, potvrdjeni=()):
    import routers.email_notif as en
    from shared.rate import limiter
    limiter.reset()                                                        # ruta: 10/min; test simulira dane, ne minute
    _Dan.pomak = n
    with patch.object(en, "date", _Dan):
        return _pokreni(b, potvrdjeni=potvrdjeni)


def _baza(rokovi=(), rocista=(), pragovi=(1,)):
    b = b10.FakeBaza(list(rokovi))
    b.tabele["rocista"] = list(rocista)
    for p in (1, 3, 7):
        b.tabele["korisnik_email_notif"][0][f"dan_{p}"] = p in pragovi
    return b


def test_C_oba_dogadjaja_izvrsiva_pre_slanja_jedan_grupisan_podsetnik():
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))
    assert rez["poslato"] == 1 and len(poslati) == 1
    assert "Rok za žalbu" in poslati[0][2] and "Osnovni sud u Beogradu" in poslati[0][2]


def test_DE_drugo_slanje_istog_dana_ne_dopunjuje_vec_podsetnut_predmet():
    """POZNATO OGRANIČENJE — odluka osnivača (V3-L1; ledger docs/v2-execution/BOJAN_N2_N9_STATE.md, G2. Runbook
    docs/release/VINDEX_NS3_N04_EMAIL_PODSETNICI_RUNBOOK.md:55 opisuje raniju varijantu po KORISNIKU, ispravljenu u N4): posle podsetnika za predmet/datum/prag, drugo slanje ISTOG dana ništa ne šalje za taj predmet —
    ni ponovo (at-most-once, B10), ni dopunu sa događajem potvrđenim u međuvremenu (ključ nema identitet događaja; ispravka
    traži migraciju). Pri jednom zakazanom slanju dnevno ne događa se; događa se pri ručnom ponovnom pokretanju istog dana
    ili ako se uključi i `/api/cron/daily`. Test drži sadašnje ponašanje vidljivim — promena ključa ga mora svesno menjati."""
    b = _baza([_rok("r1", _dan(1))], [_roc("h1", _dan(1))])
    assert len(_na_dan(0, b, potvrdjeni=())[1]) == 1                      # 1. slanje: samo ročište
    rez, poslati = _na_dan(0, b, potvrdjeni=("r1",))                      # rok potvrđen posle → 2. slanje istog dana
    assert poslati == [] and rez["poslato"] == 0
    assert [(r["predmet_id"], r["datum_roka"], r["dana_pre"]) for r in b.log] == [(PID, _dan(1), 1)]


def test_F_sledeci_prag_obuhvata_dogadjaj_potvrdjen_posle_ranijeg_praga():
    """Ročište za 3 dana podsetnuto na pragu 3; rok istog predmeta i datuma potvrđen posle toga ulazi u podsetnik na
    pragu 1 (nov ključ) — zajedno sa ročištem."""
    b = _baza(rocista=[_roc("h1", _dan(3))], pragovi=(1, 3))
    assert len(_na_dan(0, b)[1]) == 1                                      # prag 3
    b.tabele["predmet_hronologija"].append(_rok("r1", _dan(3)))
    assert _na_dan(1, b, potvrdjeni=("r1",))[1] == []                     # dan 1: 2 dana pre — nije prag
    _, poslati = _na_dan(2, b, potvrdjeni=("r1",))                         # dan 2: prag 1
    assert len(poslati) == 1 and "Rok za žalbu" in poslati[0][2] and "Osnovni sud u Beogradu" in poslati[0][2]


def test_G_dogadjaj_izvrsiv_tek_posle_poslednjeg_praga_ne_dobija_email():
    """RASPORED (ne ključ): rok za sutra potvrđen POSLE današnjeg slanja nema više nijedan prag — sutrašnje slanje
    gleda sutra+1/3/7. Isto važi i bez ikakvog ranijeg podsetnika. Advokat ga vidi na „Danas“, ali email ne dobija."""
    b = _baza()
    assert _na_dan(0, b)[1] == []                                          # ništa dospelo u trenutku slanja
    b.tabele["predmet_hronologija"].append(_rok("r1", _dan(1)))           # potvrđen posle 08:00
    assert _na_dan(1, b, potvrdjeni=("r1",))[1] == []
    assert b.log == []


def test_H_otkazano_rociste_pre_praga_ne_salje():
    b = _baza(rocista=[_roc("h1", _dan(1), status="otkazano")])
    assert _na_dan(0, b)[1] == [] and b.log == []


@pytest.mark.parametrize("pragovi,ocekivano", [((1,), [1]), ((1, 3, 7), [7, 3, 1])])
def test_svaki_ukljucen_prag_tacno_jednom(pragovi, ocekivano):
    b = _baza(rocista=[_roc("h1", _dan(7))], pragovi=pragovi)
    emailovi = 0
    for n in range(8):
        emailovi += len(_na_dan(n, b)[1])
        emailovi += len(_na_dan(n, b)[1])                                  # i ručno ponovljeno slanje istog dana
    assert [r["dana_pre"] for r in b.log] == [p for p in ocekivano if p in pragovi]
    assert emailovi == len(ocekivano)                                      # i poslatih emailova tačno toliko
