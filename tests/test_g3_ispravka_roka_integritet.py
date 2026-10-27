# -*- coding: utf-8 -*-
"""G3 — ispravka AI predloga roka (POST /api/rokovi/{id}/ispravi): posle ispravke postoji TAČNO JEDNA operativna
(potvrđena) obaveza — advokatov rok — a AI predlog ostaje vidljiv u istoriji kao ODBIJEN, sa vezom na ispravku.
Stvarne rute i stvaran lanac odluka (shared/rok_potvrda + audit_immutable u bazi u memoriji)."""
from datetime import date, timedelta

from tests.test_n4_ispravka_roka import _predlog, _stanje, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401


def _d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _kandidati(k, glava=A):
    r = k.get(f"/api/rokovi/kandidati?od={_d(-1)}&do={_d(60)}", headers=glava)
    assert r.status_code == 200, r.text
    j = r.json()
    return {x["id"]: x for x in (j.get("rokovi") or j.get("kandidati") or j.get("stavke") or [])}


def test_posle_ispravke_jedna_operativna_obaveza_a_predlog_vidljiv_kao_odbijen(lanac):
    k, b = lanac
    _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 200, r.text
    nov = r.json()["rok_id"]
    vidi = _kandidati(k)                                           # osvežen prikaz posle ispravke
    assert set(vidi) >= {nov, "rok-ai"}
    assert vidi[nov]["stanje_odluke"] == "CONFIRMED" and vidi["rok-ai"]["stanje_odluke"] == "REJECTED"
    potvrdjeni = [i for i, x in vidi.items() if x["stanje_odluke"] == "CONFIRMED"]
    assert potvrdjeni == [nov]                                     # nema protivrečnog potvrđenog stanja
    ai = next(x for x in b.tabele["predmet_hronologija"] if x["id"] == "rok-ai")
    assert ai["datum_iso"] == _d(10) and ai["izvor"] == "AI_AUTONOMOUS"     # predlog nije prepisan


def test_ispravka_opisa_i_datuma_zadrzava_izvorni_dokument(lanac):
    k, b = lanac
    _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(11), "dogadjaj": "Rok za odgovor na tužbu"}, headers=A)
    assert r.status_code == 200, r.text
    nov = next(x for x in b.tabele["predmet_hronologija"] if x["id"] == r.json()["rok_id"])
    assert nov["dogadjaj"] == "Rok za odgovor na tužbu" and nov["dokument_id"] == "dok-1" and nov["izvor"] == "HUMAN_DIRECT"


def test_ponovljena_ispravka_posle_uspeha_409_bez_novog_reda(lanac):
    k, b = lanac
    _predlog(b)
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A).status_code == 200
    pre = len(b.tabele["predmet_hronologija"])
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(13)}, headers=A)
    assert r.status_code == 409 and len(b.tabele["predmet_hronologija"]) == pre


def test_odbijen_predlog_se_ne_ispravlja(lanac):
    k, b = lanac
    _predlog(b)
    assert k.post("/api/rokovi/rok-ai/odbij", json={}, headers=A).status_code == 200
    pre = len(b.tabele["predmet_hronologija"])
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A).status_code == 409
    assert len(b.tabele["predmet_hronologija"]) == pre


def test_obrisan_predlog_404_bez_upisa(lanac):
    k, b = lanac
    _predlog(b)
    b.tabele["predmet_hronologija"] = [x for x in b.tabele["predmet_hronologija"] if x["id"] != "rok-ai"]
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A).status_code == 404
    assert b.tabele["predmet_hronologija"] == []


def test_tudji_korisnik_ne_moze_da_ispravi_ni_da_sazna_postojanje(lanac):
    k, b = lanac
    _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=B)
    assert r.status_code == 404 and _stanje(k, "rok-ai") == "UNCONFIRMED"
    assert len(b.tabele["predmet_hronologija"]) == 1


def test_istovremena_ispravka_istog_roka_drugi_dobija_409(lanac):
    """Brana je u procesu (`_ISPRAVKA_U_TOKU`); produkcija radi sa jednim procesom (/health: workers=1)."""
    import routers.rok_odluka as ro
    k, b = lanac
    _predlog(b)
    ro._ISPRAVKA_U_TOKU.add(("uid-A", "rok-ai"))                  # prvi zahtev je u toku
    try:
        r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    finally:
        ro._ISPRAVKA_U_TOKU.discard(("uid-A", "rok-ai"))
    assert r.status_code == 409 and len(b.tabele["predmet_hronologija"]) == 1 and _stanje(k, "rok-ai") == "UNCONFIRMED"
