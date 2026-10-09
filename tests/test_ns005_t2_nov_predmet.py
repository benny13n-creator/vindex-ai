# -*- coding: utf-8 -*-
"""NS005 Task 2 — nov predmet iz V2: stvarna ruta POST /api/predmeti.

Ugovor (api.py::kreiraj_predmet): telo {naziv (obavezan), opis, tip};
status je uvek „aktivan"; VLASNIK = korisnik iz tokena, nikad iz tela;
isti naziv u 5 s → 409 (zaštita od duplog slanja).
"""
import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI


@pytest.fixture
def okruzenje(monkeypatch):
    k, b = pripremi(monkeypatch)
    yield k, b
    ocisti()


def _napravi(k, korisnik, telo):
    return k.post("/api/predmeti", json=telo, headers=zaglavlje(korisnik))


def test_kreiranje_vraca_id_i_vlasnik_je_iz_tokena(okruzenje):
    k, b = okruzenje
    r = _napravi(k, "A", {"naziv": "Jović protiv Petrovića", "tip": "Parnica", "opis": "Naknada štete"})
    assert r.status_code == 200, r.text
    p = r.json()["predmet"]
    assert p["id"] and p["naziv"] == "Jović protiv Petrovića" and p["status"] == "aktivan"
    red = [x for x in b.tabele["predmeti"] if x["id"] == p["id"]][0]
    assert red["user_id"] == "uid-A"
    assert red["tip"] == "Parnica" and red["opis"] == "Naknada štete"


def test_user_id_iz_tela_se_ignorise(okruzenje):
    k, b = okruzenje
    r = _napravi(k, "A", {"naziv": "Podmetnut vlasnik", "user_id": "uid-B"})
    assert r.status_code == 200
    red = [x for x in b.tabele["predmeti"] if x["naziv"] == "Podmetnut vlasnik"][0]
    assert red["user_id"] == "uid-A"


def test_vlasnik_cita_a_drugi_korisnik_ne_vidi(okruzenje):
    k, _ = okruzenje
    pid = _napravi(k, "A", {"naziv": "Tajni predmet A"}).json()["predmet"]["id"]
    sam = k.get(f"/api/predmeti/{pid}", headers=zaglavlje("A"))
    assert sam.status_code == 200 and sam.json()["predmet"]["naziv"] == "Tajni predmet A"
    tudji = k.get(f"/api/predmeti/{pid}", headers=zaglavlje("B"))
    assert tudji.status_code == 404
    assert "Tajni predmet A" not in tudji.text
    # i u listi B nema predmeta A
    lista = k.get("/api/predmeti", headers=zaglavlje("B"))
    assert lista.status_code == 200 and "Tajni predmet A" not in lista.text


def test_bez_tokena_401_i_nista_nije_upisano(okruzenje):
    k, b = okruzenje
    r = k.post("/api/predmeti", json={"naziv": "Bez prijave"})
    assert r.status_code == 401
    assert not b.upisi("predmeti")


def test_prazan_naziv_400_i_nista_nije_upisano(okruzenje):
    k, b = okruzenje
    r = _napravi(k, "A", {"naziv": "   "})
    assert r.status_code == 400
    assert not b.upisi("predmeti")


def test_dupli_klik_409_ne_pravi_drugi_predmet(okruzenje):
    k, b = okruzenje
    assert _napravi(k, "A", {"naziv": "Dupli"}).status_code == 200
    r2 = _napravi(k, "A", {"naziv": "Dupli"})
    assert r2.status_code == 409
    assert len([x for x in b.tabele["predmeti"] if x["naziv"] == "Dupli"]) == 1
    # isti naziv kod drugog korisnika nije duplikat
    assert _napravi(k, "B", {"naziv": "Dupli"}).status_code == 200


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
