# -*- coding: utf-8 -*-
"""NS005 Task 5 — ročišta predmeta i globalna pretraga: stvarne rute.

POST/GET /api/rocista (routers/rocista.py): predmet mora biti pozivaočev; lista je po vlasniku.
GET /api/search (routers/search.py): samo podaci pozivaoca; pad grane → `nepotpuno`, ne prazno.
"""
import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA, PB = "pred-A-1", "pred-B-1"


def _baza():
    return {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Jović protiv Petrovića", "opis": "naknada štete", "status": "aktivan"},
            {"id": PB, "user_id": "uid-B", "naziv": "TAJNI Jović B", "opis": "tajna", "status": "aktivan"},
        ],
        "rocista": [
            {"id": "r-B", "predmet_id": PB, "user_id": "uid-B", "sud": "TAJNI sud", "datum": "2026-11-01", "status": "zakazano", "created_at": "2026-10-01T00:00:00+00:00"},
        ],
        "predmet_dokumenti": [
            {"id": "d-A", "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "Jović tužba.pdf", "tekst_sadrzaj": "", "tip_dokaza": "podnesak", "status": "ok", "created_at": "2026-10-01"},
            {"id": "d-B", "predmet_id": PB, "user_id": "uid-B", "naziv_fajla": "Jović TAJNO.pdf", "tekst_sadrzaj": "", "tip_dokaza": "podnesak", "status": "ok", "created_at": "2026-10-01"},
        ],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    yield k, b
    ocisti()


def test_rociste_se_zakazuje_na_svom_predmetu(ok):
    k, b = ok
    r = k.post("/api/rocista", json={"predmet_id": PA, "sud": "Osnovni sud u Beogradu", "datum": "2026-11-12", "vreme": "10:30",
                                     "sudnica": "12", "user_id": "uid-B"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    red = r.json()["rociste"]
    assert red["user_id"] == "uid-A" and red["status"] == "zakazano" and red["vreme"] == "10:30"
    lista = k.get("/api/rocista", params={"predmet_id": PA}, headers=zaglavlje("A")).json()
    assert [x["sud"] for x in lista["rocista"]] == ["Osnovni sud u Beogradu"]


def test_rociste_na_tudjem_predmetu_404_bez_upisa(ok):
    k, b = ok
    r = k.post("/api/rocista", json={"predmet_id": PB, "sud": "Upad", "datum": "2026-11-12"}, headers=zaglavlje("A"))
    assert r.status_code == 404
    assert not [x for x in b.tabele["rocista"] if x["sud"] == "Upad"]


def test_tudja_rocista_nisu_vidljiva(ok):
    k, _ = ok
    r = k.get("/api/rocista", params={"predmet_id": PB}, headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["rocista"] == [] and "TAJNI" not in r.text


def test_neispravan_datum_422(ok):
    k, b = ok
    r = k.post("/api/rocista", json={"predmet_id": PA, "sud": "Sud", "datum": "12.11.2026"}, headers=zaglavlje("A"))
    assert r.status_code == 422
    assert not b.upisi("rocista")


def test_pretraga_samo_svoje(ok):
    k, _ = ok
    r = k.get("/api/search", params={"q": "Jović", "vrste": "predmeti,dokumenti"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["id"] for x in d["predmeti"]] == [PA]
    assert [x["id"] for x in d["dokumenti"]] == ["d-A"]
    assert "TAJN" not in r.text and "nepotpuno" not in d


def test_pretraga_pad_grane_je_nepotpuno(ok):
    k, b = ok
    b.greske["predmet_dokumenti"] = RuntimeError("nedostupno")
    d = k.get("/api/search", params={"q": "Jović", "vrste": "predmeti,dokumenti"}, headers=zaglavlje("A")).json()
    assert d["nepotpuno"] == ["dokumenti"] and d["dokumenti"] == []


def test_pretraga_kratak_upit_422(ok):
    k, _ = ok
    assert k.get("/api/search", params={"q": "J"}, headers=zaglavlje("A")).status_code == 422


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
