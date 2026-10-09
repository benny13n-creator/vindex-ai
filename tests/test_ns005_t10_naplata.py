# -*- coding: utf-8 -*-
"""NS005 Task 10 — naplata predmeta bez spoljnog slanja: stvarne rute (routers/billing.py).

POST /billing/entries        — predmet mora biti pozivaočev; iznos po AKS tarifi računa SERVER.
GET  /billing/entries        — samo stavke pozivaoca.
POST /billing/faktura        — samo sopstvene stavke; faktura nastaje kao NACRT; stavka ne ide na dve fakture.
POST /billing/timer/start|stop — predmet mora biti pozivaočev; stop pravi stavku.
Nijedan test ne zove slanje fakture mejlom ni SEF.
"""
import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA, PB = "pred-A-1", "pred-B-1"


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "billing_entries": [{"id": "e-B", "user_id": "uid-B", "predmet_id": PB, "opis": "TAJNA stavka B", "iznos_rsd": 9999, "obracunato": False, "datum": "2026-10-01"}],
        "fakture": [], "timer_sessions": [], "tarifne_stavke_custom": [],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    yield k, b
    ocisti()


def test_stavka_po_tarifi_iznos_racuna_server(ok):
    k, b = ok
    r = k.post("/billing/entries", json={"predmet_id": PA, "opis": "Sastav tužbe", "tarifa_sifra": "t01", "iznos_rsd": None, "user_id": "uid-B"},
               headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    e = r.json()["entry"]
    assert e["user_id"] == "uid-A" and e["tarifa_sifra"] == "T01" and e["iznos_rsd"] == 12 * 50.0 and e["obracunato"] is False


def test_stavka_na_tudjem_predmetu_404(ok):
    k, b = ok
    r = k.post("/billing/entries", json={"predmet_id": PB, "opis": "Upad", "iznos_rsd": 100}, headers=zaglavlje("A"))
    assert r.status_code == 404
    assert not [x for x in b.tabele["billing_entries"] if x["opis"] == "Upad"]


def test_lista_samo_sopstvenih_stavki(ok):
    k, _ = ok
    r = k.get("/billing/entries", params={"predmet_id": PB}, headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["entries"] == [] and "TAJNA" not in r.text and r.json()["ukupno_rsd"] == 0


def test_faktura_nastaje_kao_nacrt_i_stavka_se_ne_naplacuje_dvaput(ok):
    k, b = ok
    eid = k.post("/billing/entries", json={"predmet_id": PA, "opis": "Rad", "iznos_rsd": 3000}, headers=zaglavlje("A")).json()["entry"]["id"]
    r = k.post("/billing/faktura", json={"predmet_id": PA, "entry_ids": [eid], "klijent_naziv": "Ana Jović"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    f = r.json()["faktura"]
    assert f["status"] == "nacrt" and f["user_id"] == "uid-A"
    assert [x for x in b.tabele["billing_entries"] if x["id"] == eid][0]["obracunato"] is True
    r2 = k.post("/billing/faktura", json={"predmet_id": PA, "entry_ids": [eid], "klijent_naziv": "Ana Jović"}, headers=zaglavlje("A"))
    assert r2.status_code == 409


def test_tudje_stavke_se_ne_fakturisu(ok):
    k, b = ok
    r = k.post("/billing/faktura", json={"predmet_id": PB, "entry_ids": ["e-B"], "klijent_naziv": "X"}, headers=zaglavlje("A"))
    assert r.status_code == 404
    assert [x for x in b.tabele["billing_entries"] if x["id"] == "e-B"][0]["obracunato"] is False
    assert b.tabele["fakture"] == []


def test_tajmer_na_tudjem_predmetu_404_a_na_svom_pravi_stavku(ok):
    k, b = ok
    assert k.post("/billing/timer/start", json={"predmet_id": PB}, headers=zaglavlje("A")).status_code == 404
    assert k.post("/billing/timer/start", json={"predmet_id": PA, "opis": "Priprema"}, headers=zaglavlje("A")).status_code == 200
    akt = k.get("/billing/timer/aktivan", headers=zaglavlje("A")).json()
    assert akt["aktivan"] is True and akt["timer"]["predmet_id"] == PA
    assert k.get("/billing/timer/aktivan", headers=zaglavlje("B")).json()["aktivan"] is False
    assert [x for x in b.tabele["timer_sessions"] if x["predmet_id"] == PB] == []
    assert k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("B")).status_code == 404
    r = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    e = r.json()["entry"]
    assert e["user_id"] == "uid-A" and e["predmet_id"] == PA and e["opis"] == "Priprema" and e["obracunato"] is False
    assert k.get("/billing/timer/aktivan", headers=zaglavlje("A")).json()["aktivan"] is False


def test_pad_baze_na_listi_nije_prazna_lista(ok):
    k, b = ok
    b.greske["billing_entries"] = Exception("db down")
    r = k.get("/billing/entries", params={"predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code >= 500 and "entries" not in r.text


def test_lista_faktura_samo_sopstvenih(ok):
    k, b = ok
    b.tabele["fakture"].append({"id": "f-B", "user_id": "uid-B", "predmet_id": PB, "broj_fakture": "2026/0001", "klijent_naziv": "TAJNI klijent", "status": "nacrt", "iznos_sa_pdv": 1, "created_at": "2026-10-01"})
    r = k.get("/billing/faktura", headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["fakture"] == [] and "TAJNI" not in r.text


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
