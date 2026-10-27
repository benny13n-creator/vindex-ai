# -*- coding: utf-8 -*-
"""V3 — identitet podsetnika: različiti događaji se ne gase međusobno, isti se ne šalje dvaput, i samo potvrđen
rok ulazi u podsetnik (stvaran lanac odluka). NIJEDAN test ne šalje pravi email (`_smtp_send` je uvek zamenjen).

Ključ rezervacije je postojeći UNIQUE(user_id, predmet_id, datum_roka, dana_pre) iz migracije 021: jedan podsetnik
po PREDMETU, datumu i pragu (1/3/7 dana), sa svim događajima tog predmeta i datuma u istom emailu."""
import asyncio
import html as _html
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from tests import test_b10_reminder_claim as b10
from tests.test_n4_podsetnici import P2, PID, UID, _pokreni, _roc, _rok, _sutra
from tests.test_n4_ispravka_roka import _predlog, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, solo  # noqa: F401


def _za_3_dana():
    return (date.today() + timedelta(days=3)).isoformat()


def _baza(rokovi=(), rocista=(), drugi_predmet=False):
    b = b10.FakeBaza(list(rokovi))
    b.tabele["rocista"] = list(rocista)
    if drugi_predmet:
        b.tabele["predmeti"].append({"id": P2, "user_id": UID, "status": "aktivan"})
    return b


def _telo(poslati):
    return _html.unescape(poslati[0][2])


def test_rociste_i_rok_istog_predmeta_istog_dana_idu_u_isti_podsetnik():
    b = _baza([_rok("r1", _sutra())], [_roc("h1", _sutra())])
    rez, poslati = _pokreni(b, potvrdjeni=("r1",))
    assert rez["poslato"] == 1 and len(poslati) == 1
    assert poslati[0][1] == "Vindex AI — Sutra: rok i ročište"
    assert "Rok za žalbu" in _telo(poslati) and "Ročište — Osnovni sud u Beogradu" in _telo(poslati)
    assert [r["predmet_id"] for r in b.log] == [PID]


def test_dva_rocista_istog_predmeta_istog_dana_oba_u_podsetniku():
    b = _baza(rocista=[_roc("h1", _sutra()), dict(_roc("h2", _sutra()), sud="Viši sud u Beogradu", vreme="13:00:00")])
    _, poslati = _pokreni(b)
    assert len(poslati) == 1 and "Osnovni sud u Beogradu" in _telo(poslati) and "Viši sud u Beogradu" in _telo(poslati)


def test_dva_roka_istog_predmeta_istog_dana_oba_u_podsetniku():
    b = _baza([_rok("r1", _sutra()), _rok("r2", _sutra(), dogadjaj="Rok za predlog za izvršenje")])
    _, poslati = _pokreni(b, potvrdjeni=("r1", "r2"))
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati) and "Rok za predlog za izvršenje" in _telo(poslati)


def test_dva_predmeta_istog_dana_oba_rezervisana_i_poslata():
    b = _baza([_rok("r1", _sutra())], [_roc("h2", _sutra(), predmet=P2)], drugi_predmet=True)
    _, poslati = _pokreni(b, potvrdjeni=("r1",))
    assert len(poslati) == 1 and "Rok za žalbu" in _telo(poslati) and "Ročište — Osnovni sud" in _telo(poslati)
    assert sorted(r["predmet_id"] for r in b.log) == [PID, P2]


def test_vise_korisnika_ne_gase_jedan_drugog():
    b = _baza([_rok("r1", _sutra())])
    b.tabele["korisnik_email_notif"].append({"user_id": "u-2", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
    b.tabele["profiles"].append({"id": "u-2", "email": "drugi@example.invalid"})
    b.tabele["predmeti"].append({"id": PID, "user_id": "u-2", "status": "aktivan"})      # isti tekst ključa predmeta
    b.tabele["predmet_hronologija"].append(dict(_rok("r9", _sutra()), user_id="u-2"))
    b.tabele["rocista"] = [dict(_roc("h9", _sutra()), user_id="u-2", sud="TUDJI sud")]
    _, poslati = _pokreni(b, potvrdjeni=("r1", "r9"))
    assert sorted(p[0] for p in poslati) == ["drugi@example.invalid", b10.MAIL]
    prvi = next(p for p in poslati if p[0] == b10.MAIL)
    assert "TUDJI sud" not in prvi[2]                                   # ročište drugog korisnika ne ulazi
    assert sorted(r["user_id"] for r in b.log) == sorted([UID, "u-2"])


def test_isti_dogadjaj_ponovljen_ne_salje_dvaput():
    b = _baza(rocista=[_roc("h1", _sutra())])
    assert len(_pokreni(b)[1]) == 1
    rez, poslati = _pokreni(b)
    assert poslati == [] and rez["poslato"] == 0 and len(b.log) == 1


def test_odlozeno_rociste_sa_novim_datumom_dobija_svoj_podsetnik():
    """Pomeren datum je nov ključ (nov se šalje u svom pragu), a odloženo ročište na starom datumu se ne šalje —
    i kad za stari datum još NIŠTA nije rezervisano (meri filter statusa, ne rezervaciju)."""
    b = _baza(rocista=[_roc("h1", _sutra())])
    b.tabele["korisnik_email_notif"][0]["dan_3"] = True
    assert len(_pokreni(b)[1]) == 1                                      # sutra: poslato
    b.tabele["rocista"] = [_roc("h1", _sutra(), status="odlozeno"), _roc("h1b", _za_3_dana())]
    rez, poslati = _pokreni(b)
    assert len(poslati) == 1 and "Za 3 dana" in poslati[0][1], rez
    assert sorted((r["datum_roka"], r["dana_pre"]) for r in b.log) == sorted([(_sutra(), 1), (_za_3_dana(), 3)])
    sveza = _baza(rocista=[_roc("h1", _sutra(), status="odlozeno"), _roc("h1b", _za_3_dana())])
    sveza.tabele["korisnik_email_notif"][0]["dan_3"] = True
    _, poslati = _pokreni(sveza)
    assert len(poslati) == 1 and "Za 3 dana" in poslati[0][1]
    assert [(r["datum_roka"], r["dana_pre"]) for r in sveza.log] == [(_za_3_dana(), 3)]   # odloženo: bez rezervacije


# V3-L1 (drugo slanje istog dana ne dopunjuje već podsetnut predmet/datum/prag) je POZNATO OGRANIČENJE — odluka
# osnivača (ispravka traži migraciju); ponašanje je izmereno u tests/test_g2_podsetnici_raspored.py::test_DE_* (G2).


# ── stvaran lanac odluka (shared/rok_potvrda + audit_immutable u bazi u memoriji) ───────────────────────────────

def _cron(b):
    import routers.email_notif as en
    poslati = []
    b.tabele.setdefault("korisnik_email_notif", [])
    if not b.tabele["korisnik_email_notif"]:
        b.tabele["korisnik_email_notif"].append({"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
        b.tabele.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat@example.invalid"})
        b.tabele.setdefault("email_notif_log", [])
        b.tabele.setdefault("rocista", [])
    with patch.object(en, "_SMTP_HOST", "smtp.test.invalid"), patch.object(en, "_get_supa", return_value=b), \
         patch.object(en, "_smtp_send", lambda to, subj, html: poslati.append((to, subj, html))):
        rez = asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))
    return rez, poslati


def test_lanac_nepotvrdjen_ne_salje_potvrdjen_salje(lanac):
    k, b = lanac
    _predlog(b, dana=1)
    assert _cron(b)[1] == []                                                       # predlog: ništa
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    _, poslati = _cron(b)
    assert len(poslati) == 1 and "Rok za tužbu" in _html.unescape(poslati[0][2])


def test_lanac_odbijen_ne_salje(lanac):
    k, b = lanac
    _predlog(b, dana=1)
    assert k.post("/api/rokovi/rok-ai/odbij", json={}, headers=A).status_code == 200
    assert _cron(b)[1] == []


def test_lanac_dvostruka_potvrda_ne_salje_dvaput(lanac):
    """Meri ISHOD: druga potvrda ne obara rutu, a podsetnik ostaje jedan. (Podsetnik je jedan email po predmetu,
    datumu i pragu, pa duplu potvrdu sama po sebi ovde ne može da otkrije — nju meri test_faza65 `odluke`.)"""
    k, b = lanac
    _predlog(b, dana=1)
    prva = k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A)
    druga = k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A)
    assert prva.status_code == 200 and druga.status_code in (200, 409), druga.text
    assert len(_cron(b)[1]) == 1 and _cron(b)[1] == []


def test_lanac_ispravka_salje_ispravljen_datum_a_ne_predlog(lanac):
    k, b = lanac
    _predlog(b, dana=3)                                                            # AI pročitao pogrešan datum
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": (date.today() + timedelta(days=1)).isoformat()}, headers=A)
    assert r.status_code == 200, r.text
    b.tabele["korisnik_email_notif"] = [{"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": True, "dan_7": False}]
    b.tabele.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat@example.invalid"})
    b.tabele.setdefault("email_notif_log", [])
    b.tabele.setdefault("rocista", [])
    _, poslati = _cron(b)
    assert len(poslati) == 1 and "Sutra" in poslati[0][1]                          # samo ispravljen (sutra)
    assert [(x["datum_roka"], x["dana_pre"]) for x in b.tabele["email_notif_log"]] == [
        ((date.today() + timedelta(days=1)).isoformat(), 1)]                       # odbijen predlog (za 3 dana): ništa
