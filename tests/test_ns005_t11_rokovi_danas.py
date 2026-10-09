# -*- coding: utf-8 -*-
"""NS005 Task 11 — odluka o roku, kalendar, Danas: stvarne rute.

GET  /api/rokovi/kandidati          (routers/rok_odluka.py) — samo rokovi pozivaoca, sa stanjem odluke
POST /api/rokovi/{id}/potvrdi|odbij — tuđ rok 404 bez upisa; odluka = zapis u audit lancu,
                                      hronologija se NE menja i NE briše; poslednja odluka važi
GET  /api/kalendar/pregled          (routers/kalendar.py) — samo podaci pozivaoca; pad izvora se KAŽE
Nijedan test ne šalje mejl/SMS/Viber; potvrda ne zove nijedan kanal.
"""
from datetime import date, timedelta

import pytest

from shared import rokovi as rokovi_domen
from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA, PB = "pred-A-1", "pred-B-1"
D = lambda n: (date.today() + timedelta(days=n)).isoformat()


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "predmet_hronologija": [
            {"id": "r-A-1", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za žalbu", "datum_iso": D(3), "vaznost": "kritičan", "izvor": "ai", "vrsta": "rok", "stanje": "kandidat"},
            {"id": "r-A-old", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Propušten rok", "datum_iso": D(-5), "vaznost": "visok", "izvor": "covek", "vrsta": "rok", "stanje": "kandidat"},
            {"id": "r-B-1", "user_id": "uid-B", "predmet_id": PB, "dogadjaj": "TAJNI rok B", "datum_iso": D(2), "vaznost": "visok", "vrsta": "rok", "stanje": "kandidat"},
        ],
        "rocista": [
            {"id": "ro-A", "user_id": "uid-A", "predmet_id": PA, "datum": D(1), "vreme": "09:30:00", "sud": "Osnovni sud u Beogradu", "status": "zakazano"},
            {"id": "ro-B", "user_id": "uid-B", "predmet_id": PB, "datum": D(1), "vreme": "10:00:00", "sud": "TAJNI sud B", "status": "zakazano"},
        ],
        "audit_immutable": [],
    }


@pytest.fixture
def ok(monkeypatch):
    rokovi_domen._resetuj_sondu()
    import shared.audit_immutable as audit
    pravi = audit.log_action
    k, b = pripremi(monkeypatch, _baza())
    # Harness gasi audit radi tišine; ovde JE audit lanac poslovni upis odluke, pa radi pravi
    # `log_action` nad lažnom bazom (isti hash-lanac i isti `seq` redosled kao u produkciji).
    monkeypatch.setattr(audit, "log_action", pravi)
    yield k, b
    rokovi_domen._resetuj_sondu()
    ocisti()


def _stanja(k, tok="A"):
    r = k.get("/api/rokovi/kandidati", params={"od": D(-30), "dana": 30}, headers=zaglavlje(tok))
    assert r.status_code == 200, r.text
    return {x["id"]: x["stanje_odluke"] for x in r.json()["rokovi"]}


def test_kandidati_samo_sopstveni_sa_stanjem_i_propustenim(ok):
    k, _ = ok
    r = k.get("/api/rokovi/kandidati", params={"od": D(-30), "dana": 30}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert "TAJNI" not in r.text
    assert _stanja(k) == {"r-A-1": "UNCONFIRMED", "r-A-old": "UNCONFIRMED"}
    assert {x["vrsta"] for x in r.json()["rokovi"]} == {"rok"}


def test_tudj_rok_404_bez_upisa_odluke(ok):
    k, b = ok
    for akcija in ("potvrdi", "odbij"):
        r = k.post(f"/api/rokovi/r-B-1/{akcija}", json={}, headers=zaglavlje("A"))
        assert r.status_code == 404 and "TAJNI" not in r.text
    assert b.tabele["audit_immutable"] == []
    assert _stanja(k, "B") == {"r-B-1": "UNCONFIRMED"}


def test_potvrda_je_zapis_o_roku_ne_prepravka_hronologije(ok):
    k, b = ok
    pre = [dict(x) for x in b.tabele["predmet_hronologija"]]
    r = k.post("/api/rokovi/r-A-1/potvrdi", json={"user_id": "uid-B"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["stanje_odluke"] == "CONFIRMED"
    zap = b.tabele["audit_immutable"]
    assert len(zap) == 1 and zap[0]["action"] == "rok_potvrdjen" and zap[0]["user_id"] == "uid-A" and zap[0]["resource_id"] == "r-A-1"
    assert b.tabele["predmet_hronologija"] == pre
    assert _stanja(k)["r-A-1"] == "CONFIRMED"


def test_odbijanje_ne_brise_a_poslednja_odluka_vazi(ok):
    k, b = ok
    assert k.post("/api/rokovi/r-A-1/potvrdi", json={}, headers=zaglavlje("A")).status_code == 200
    assert k.post("/api/rokovi/r-A-1/odbij", json={}, headers=zaglavlje("A")).status_code == 200
    assert _stanja(k)["r-A-1"] == "REJECTED"
    assert any(x["id"] == "r-A-1" for x in b.tabele["predmet_hronologija"])


def test_neuspeo_upis_odluke_503_i_rok_ostaje_nepotvrdjen(ok):
    k, b = ok
    b.greske["audit_immutable"] = Exception("db down")
    r = k.post("/api/rokovi/r-A-1/potvrdi", json={}, headers=zaglavlje("A"))
    # 5xx detalj se ne šalje klijentu (api.py sakriva interni detalj); stanje se proverava ponovnim čitanjem.
    assert r.status_code == 503
    del b.greske["audit_immutable"]
    assert _stanja(k)["r-A-1"] == "UNCONFIRMED"


def test_pad_citanja_kandidata_nije_prazna_lista(ok):
    k, b = ok
    b.greske["predmet_hronologija"] = Exception("db down")
    r = k.get("/api/rokovi/kandidati", params={"od": D(-30), "dana": 30}, headers=zaglavlje("A"))
    assert r.status_code == 503 and "rokovi" not in r.json()


def test_kalendar_samo_sopstveni_i_pad_izvora_se_kaze(ok):
    k, b = ok
    r = k.get("/api/kalendar/pregled", params={"od": D(-30), "do": D(30)}, headers=zaglavlje("A"))
    assert r.status_code == 200 and "TAJNI" not in r.text
    j = r.json()
    ro = [e for e in j["dogadjaji"] if e["tip"] == "rociste"]
    assert len(ro) == 1 and ro[0]["vreme"] == "09:30" and ro[0]["predmet_naziv"] == "Predmet A"
    assert j["degraded_sources"] == [] and j["truncated"] is False
    b.greske["rocista"] = Exception("db down")
    j2 = k.get("/api/kalendar/pregled", params={"od": D(-30), "do": D(30)}, headers=zaglavlje("A")).json()
    assert j2["degraded_sources"] == ["rocista"] and not [e for e in j2["dogadjaji"] if e["tip"] == "rociste"]


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
