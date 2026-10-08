# -*- coding: utf-8 -*-
"""NS005 Task 3 — izmena predmeta, beleške, hronologija: stvarne rute.

PATCH /api/predmeti/{id}: samo polja sa liste servera; vlasnik iz tokena;
opciono `if_updated_at` → 409 kad je predmet izmenjen u međuvremenu; tuđ → 404.
POST /api/predmeti/{id}/beleske: vlasnik predmeta proveren PRE upisa.
GET /api/predmeti/{id}: vraća beleske i hronologiju samo vlasniku.
"""
import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA, PB = "pred-A-1", "pred-B-1"


def _baza():
    return {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "tip": "Parnica", "status": "aktivan", "tuzilac": "", "tuzeni": "",
             "opis": "", "vrednost_spora": None, "updated_at": "2026-10-01T10:00:00+00:00", "created_at": "2026-10-01T10:00:00+00:00"},
            {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "tip": "Parnica", "status": "aktivan",
             "updated_at": "2026-10-01T10:00:00+00:00", "created_at": "2026-10-01T10:00:00+00:00"},
        ],
        "predmet_beleske": [{"id": "bel-B", "predmet_id": PB, "user_id": "uid-B", "sadrzaj": "TAJNA beleška B", "created_at": "2026-10-02T09:00:00+00:00"}],
        "predmet_hronologija": [
            {"id": "h1", "predmet_id": PA, "user_id": "uid-A", "dogadjaj": "Tužba podneta", "datum_iso": "2026-09-01", "vaznost": "visoka"},
            {"id": "h2", "predmet_id": PB, "user_id": "uid-B", "dogadjaj": "TAJNI događaj B", "datum_iso": "2026-09-02", "vaznost": "srednja"},
        ],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    yield k, b
    ocisti()


def _red(b, pid):
    return [r for r in b.tabele["predmeti"] if r["id"] == pid][0]


def test_izmena_se_cuva_i_cita_posle_ponovnog_ucitavanja(ok):
    k, b = ok
    r = k.patch(f"/api/predmeti/{PA}", json={"tuzilac": "Ana Jović", "vrednost_spora": 850000,
                                             "if_updated_at": "2026-10-01T10:00:00+00:00"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] and r.json()["updated_at"] != "2026-10-01T10:00:00+00:00"
    d = k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A")).json()["predmet"]
    assert d["tuzilac"] == "Ana Jović" and d["vrednost_spora"] == 850000


def test_zastarela_izmena_409_i_nista_ne_menja(ok):
    k, b = ok
    assert k.patch(f"/api/predmeti/{PA}", json={"tuzeni": "Prvi"}, headers=zaglavlje("A")).status_code == 200
    r = k.patch(f"/api/predmeti/{PA}", json={"tuzeni": "Drugi", "if_updated_at": "2026-10-01T10:00:00+00:00"}, headers=zaglavlje("A"))
    assert r.status_code == 409
    assert _red(b, PA)["tuzeni"] == "Prvi"


def test_tudja_izmena_404_i_red_netaknut(ok):
    k, b = ok
    r = k.patch(f"/api/predmeti/{PA}", json={"naziv": "Preoteo B"}, headers=zaglavlje("B"))
    assert r.status_code == 404
    assert _red(b, PA)["naziv"] == "Predmet A"


def test_vlasnik_se_ne_menja_kroz_telo(ok):
    k, b = ok
    r = k.patch(f"/api/predmeti/{PA}", json={"naziv": "Novi naziv", "user_id": "uid-B"}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert _red(b, PA)["user_id"] == "uid-A" and _red(b, PA)["naziv"] == "Novi naziv"


def test_samo_nepoznata_polja_400(ok):
    k, b = ok
    r = k.patch(f"/api/predmeti/{PA}", json={"broj_predmeta": "P 1/2026"}, headers=zaglavlje("A"))
    assert r.status_code == 400
    assert not b.upisi("predmeti")


def test_beleska_se_upisuje_i_vidi_posle_ucitavanja(ok):
    k, b = ok
    r = k.post(f"/api/predmeti/{PA}/beleske", json={"sadrzaj": "Pozvati svedoka"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["beleska"]["user_id"] == "uid-A"
    d = k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A")).json()
    assert [x["sadrzaj"] for x in d["beleske"]] == ["Pozvati svedoka"]
    assert [x["dogadjaj"] for x in d["hronologija"]] == ["Tužba podneta"]


def test_beleska_u_tudj_predmet_se_ne_upisuje(ok):
    k, b = ok
    r = k.post(f"/api/predmeti/{PA}/beleske", json={"sadrzaj": "Upad B"}, headers=zaglavlje("B"))
    assert r.status_code >= 400
    assert not [x for x in b.tabele["predmet_beleske"] if x["sadrzaj"] == "Upad B"]


def test_tudje_beleske_i_hronologija_nisu_dostupne(ok):
    k, _ = ok
    r = k.get(f"/api/predmeti/{PB}", headers=zaglavlje("A"))
    assert r.status_code == 404
    assert "TAJNA" not in r.text and "TAJNI" not in r.text


def test_prazna_beleska_400(ok):
    k, b = ok
    assert k.post(f"/api/predmeti/{PA}/beleske", json={"sadrzaj": "  "}, headers=zaglavlje("A")).status_code == 400
    assert not b.upisi("predmet_beleske")


def test_html_u_belesci_ne_ulazi_kao_markup(ok):
    k, b = ok
    r = k.post(f"/api/predmeti/{PA}/beleske", json={"sadrzaj": "<script>alert(1)</script>Rok"}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert "<script>" not in r.json()["beleska"]["sadrzaj"]


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
