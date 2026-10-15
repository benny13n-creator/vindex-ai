# -*- coding: utf-8 -*-
"""Night Sprint II / A2 — potvrda daje izvrsivost SAMO redu izjavljenom kao rok.

Izlazni slojevi (podsetnici, .ics, klijent, akcije) pitaju samo `shared.rokovi.sme_pristupiti`,
koja ne zna za `vrsta`. Potvrdjen red bez `vrsta='rok'` (npr. „Predmet zatvoren") bio bi izvrsiv,
a V2 Danas/Dosije ga ne prikazuju. Zato POST /api/rokovi/{id}/potvrdi vraca 409 za neizjavljen red
(posle migracije 129), bez upisa u audit lanac. Odbijanje ostaje dozvoljeno (samo oduzima izvrsivost).
Stvarne rute, stvaran `log_action` nad bazom u memoriji (tests/ns005_harness.py).
"""
from datetime import date, timedelta

import pytest

from shared import rokovi as rokovi_domen
from tests.ns005_harness import ocisti, pripremi, zaglavlje

PA, PB = "pred-A-1", "pred-B-1"
D = lambda n: (date.today() + timedelta(days=n)).isoformat()


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "predmet_hronologija": [
            {"id": "r-rok", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za odgovor na tuzbu", "datum_iso": D(4),
             "vaznost": "visok", "izvor": "HUMAN_DIRECT", "vrsta": "rok"},
            {"id": "r-null", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Predmet zatvoren", "datum_iso": D(2),
             "vaznost": "normalan", "izvor": "SYSTEM"},
            {"id": "r-dog", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Urucenje resenja", "datum_iso": D(1),
             "vaznost": "normalan", "izvor": "HUMAN_DIRECT", "vrsta": "dogadjaj"},
            {"id": "r-B", "user_id": "uid-B", "predmet_id": PB, "dogadjaj": "TAJNI rok B", "datum_iso": D(2),
             "vaznost": "visok", "vrsta": "rok"},
        ],
        "audit_immutable": [],
    }


@pytest.fixture
def ok(monkeypatch):
    rokovi_domen._resetuj_sondu()
    import shared.audit_immutable as audit
    pravi = audit.log_action
    k, b = pripremi(monkeypatch, _baza())
    monkeypatch.setattr(audit, "log_action", pravi)
    yield k, b
    rokovi_domen._resetuj_sondu()
    ocisti()


def _stanja(k):
    r = k.get("/api/rokovi/kandidati", params={"od": D(-5), "dana": 30}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    return {x["id"]: x["stanje_odluke"] for x in r.json()["rokovi"]}


@pytest.mark.parametrize("rid", ["r-null", "r-dog"])
def test_potvrda_neizjavljenog_reda_409_bez_upisa(ok, rid):
    k, b = ok
    r = k.post(f"/api/rokovi/{rid}/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.status_code == 409, r.text
    assert "nije označen kao rok" in r.json()["detail"]
    assert b.tabele["audit_immutable"] == []
    assert _stanja(k)[rid] == "UNCONFIRMED"


def test_potvrda_izjavljenog_roka_i_dalje_radi(ok):
    k, b = ok
    r = k.post("/api/rokovi/r-rok/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["stanje_odluke"] == "CONFIRMED"
    assert [(z["action"], z["resource_id"]) for z in b.tabele["audit_immutable"]] == [("rok_potvrdjen", "r-rok")]


def test_tudj_red_i_dalje_404_pre_provere_vrste(ok):
    k, b = ok
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/r-B/{akcija}", json={}, headers=zaglavlje("A"))
        assert r.status_code == 404 and "TAJNI" not in r.text
    r = k.post("/api/rokovi/ne-postoji/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.status_code == 404
    assert b.tabele["audit_immutable"] == []


def test_odbijanje_neizjavljenog_reda_dozvoljeno_i_opoziva_raniju_potvrdu(ok):
    """Zatecena potvrda reda bez `vrsta` (pre ove kapije) mora moci da se opozove."""
    k, b = ok
    b.tabele["audit_immutable"].append({"action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "r-null",
                                        "user_id": "uid-A", "seq": 0})
    assert _stanja(k)["r-null"] == "CONFIRMED"
    r = k.post("/api/rokovi/r-null/odbij", json={}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["stanje_odluke"] == "REJECTED"
    assert _stanja(k)["r-null"] == "REJECTED"


def test_audit_nedostupan_nema_uspeha(ok):
    k, b = ok
    b.greske["audit_immutable"] = Exception('{"code": "57014", "message": "statement timeout"}')
    r = k.post("/api/rokovi/r-rok/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.status_code == 503 and r.json().get("stanje_odluke") is None
    r = k.post("/api/rokovi/r-null/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.status_code == 409
    del b.greske["audit_immutable"]
    assert b.tabele["audit_immutable"] == []
    assert _stanja(k)["r-rok"] == "UNCONFIRMED"


def test_pre_migracije_129_ponasanje_nepromenjeno(ok, monkeypatch):
    """Bez kolone `vrsta` nijedan red nije izjavljen; kapija se ne primenjuje (inace bi i stvarni
    rokovi postali nepotvrdivi), a upit vlasnistva ne trazi nepostojecu kolonu."""
    k, b = ok
    monkeypatch.setattr(rokovi_domen, "_KOLONE_129", False)
    r = k.post("/api/rokovi/r-null/potvrdi", json={}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert [z["resource_id"] for z in b.tabele["audit_immutable"]] == ["r-null"]


def test_upit_vlasnistva_trazi_vrstu_samo_posle_129(ok, monkeypatch):
    import asyncio
    import routers.rok_odluka as ro
    k, b = ok
    vidjeno = []

    class _Sonda:
        def __init__(self, baza):
            self.b = baza

        def table(self, t):
            u = self.b.table(t)
            orig = u.select

            def _sel(kol, *a, **kw):
                vidjeno.append(kol)
                return orig(kol, *a, **kw)
            u.select = _sel
            return u
    for sema in (True, False):
        red = asyncio.run(ro._rok_u_vlasnistvu(_Sonda(b), "r-rok", "uid-A", sa_vrstom=sema))
        assert ("vrsta" in red) is sema
    assert vidjeno == ["id, predmet_id, dogadjaj, datum_iso, vaznost, akter, vrsta",
                       "id, predmet_id, dogadjaj, datum_iso, vaznost, akter"]


# ── F1: sonda seme 129 kesira samo DOKAZAN odgovor ───────────────────────────────────────────────────────────

class _Sonda129:
    """Lazna baza samo za sondu: redom vraca ishode iz liste (izuzetak ili uspeh)."""
    def __init__(self, ishodi):
        self.ishodi, self.poziva = list(ishodi), 0

    def table(self, t):
        return self

    def select(self, *a, **k):
        return self

    def limit(self, *a):
        return self

    def execute(self):
        self.poziva += 1
        x = self.ishodi.pop(0) if self.ishodi else None
        if isinstance(x, Exception):
            raise x
        return type("R", (), {"data": []})()


ISTEK = Exception('{"code": "57014", "message": "canceling statement due to statement timeout"}')
NEMA_KOLONE = Exception('{"code": "42703", "message": "column predmet_hronologija.vrsta does not exist"}')


def test_sonda_istek_se_ne_kesira_i_ne_gasi_oznaku_pa_se_oporavlja():
    rokovi_domen._resetuj_sondu()
    s = _Sonda129([ISTEK, ISTEK, None])
    assert rokovi_domen._sema_ima_129(s) is True          # neodredjeno → kapija ukljucena, oznaka se upisuje
    assert rokovi_domen._KOLONE_129 is None               # ... ali se NE kesira
    assert rokovi_domen.oznake(vrsta=rokovi_domen.VRSTA_ROK, supa=_Sonda129([ISTEK, ISTEK])) == {"vrsta": "rok"}
    rokovi_domen._NEODREDJENA_SONDA_DO = 0.0                # pauza posle neodredjene sonde istekla
    assert rokovi_domen._sema_ima_129(s) is True and rokovi_domen._KOLONE_129 is True   # oporavak: dokazano, kesirano
    rokovi_domen._resetuj_sondu()


def test_sonda_u_pauzi_posle_isteka_ne_blokira_radnika_novim_upitom():
    # NS2-A2 pregled 2 (N1): sonda je sinhron poziv iz async rukovaoca; za vreme ispada baze ne sme svaki zahtev
    # ponovo da ceka istek klijenta. U pauzi: bez upita, isto znacenje kao neodredjeno (kapija ukljucena).
    rokovi_domen._resetuj_sondu()
    s = _Sonda129([ISTEK, ISTEK])
    assert rokovi_domen._sema_ima_129(s) is True and s.poziva == 2
    for _ in range(5):
        assert rokovi_domen._sema_ima_129(s) is True
    assert s.poziva == 2 and rokovi_domen._KOLONE_129 is None
    rokovi_domen._NEODREDJENA_SONDA_DO = 0.0
    s.ishodi = [None]
    assert rokovi_domen._sema_ima_129(s) is True and s.poziva == 3 and rokovi_domen._KOLONE_129 is True
    rokovi_domen._resetuj_sondu()


def test_sonda_jedan_istek_pa_uspeh_u_istom_pozivu():
    rokovi_domen._resetuj_sondu()
    s = _Sonda129([ISTEK, None])
    assert rokovi_domen._sema_ima_129(s) is True and s.poziva == 2 and rokovi_domen._KOLONE_129 is True
    rokovi_domen._resetuj_sondu()


@pytest.mark.parametrize("greska", [NEMA_KOLONE, Exception('{"code": "42703"}'), Exception('{"code": "PGRST204", "message": "Could not find the vrsta column"}')])
def test_sonda_izricito_nema_kolone_kesira_false_pre_129(greska):
    rokovi_domen._resetuj_sondu()
    s = _Sonda129([greska])
    assert rokovi_domen._sema_ima_129(s) is False and rokovi_domen._KOLONE_129 is False
    assert rokovi_domen.oznake(vrsta=rokovi_domen.VRSTA_ROK, supa=s) == {}
    assert s.poziva == 1
    rokovi_domen._resetuj_sondu()


def test_potvrda_pri_neodredjenoj_semi_kapija_ostaje(ok, monkeypatch):
    """Istek sonde ne sme da pusti potvrdu reda koji nije rok; pravi rok se i dalje potvrdjuje."""
    k, b = ok
    pravi = rokovi_domen._sema_ima_129

    def _neodredjeno(supa):
        rokovi_domen._resetuj_sondu()
        return pravi(_Sonda129([ISTEK, ISTEK]))
    monkeypatch.setattr(rokovi_domen, "_sema_ima_129", _neodredjeno)
    assert k.post("/api/rokovi/r-null/potvrdi", json={}, headers=zaglavlje("A")).status_code == 409
    assert b.tabele["audit_immutable"] == []
    assert k.post("/api/rokovi/r-rok/potvrdi", json={}, headers=zaglavlje("A")).status_code == 200
    assert rokovi_domen._KOLONE_129 is None


def test_citanje_roka_palo_503_bez_upisa(ok):
    k, b = ok
    b.greske["predmet_hronologija"] = ISTEK
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/r-rok/{akcija}", json={}, headers=zaglavlje("A"))
        assert r.status_code == 503 and r.json().get("stanje_odluke") is None   # api.py maskira detalj 5xx
    assert b.tabele["audit_immutable"] == []
