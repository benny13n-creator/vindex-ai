# -*- coding: utf-8 -*-
"""NS005 Task 4 — klijenti, vezivanje za predmet, provera sukoba interesa: stvarne rute.

POST /klijenti, GET /klijenti?pretraga=  (klijenti/router.py — vlasnik iz tokena)
POST /api/predmeti/{id}/confirm-links    (api.py — vlasnik predmeta I svakog klijenta)
POST /api/conflict-check                 (routers/conflict_check.py — samo podaci pozivaoca)
"""
import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA, PB = "pred-A-1", "pred-B-1"


def _baza():
    return {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Jović protiv Petrovića", "status": "aktivan", "tuzilac": "Ana Jović", "tuzeni": "Petar Petrović", "created_at": "2026-10-01"},
            {"id": "pred-A-2", "user_id": "uid-A", "naziv": "Stari spor", "status": "zatvoren", "tuzilac": "Marko Marković", "tuzeni": "Omega doo", "created_at": "2026-01-01"},
            {"id": PB, "user_id": "uid-B", "naziv": "TAJNI predmet B", "status": "aktivan", "tuzilac": "Zoran Zorić", "tuzeni": "Ana Jović", "created_at": "2026-10-01"},
        ],
        "klijenti": [
            {"id": "kl-A1", "user_id": "uid-A", "ime": "Ana", "prezime": "Jović", "firma": "", "email": "ana@primer.rs", "status": "aktivan", "tip": "fizicko_lice", "jmbg_encrypted": "ENC-JMBG-A"},
            {"id": "kl-B1", "user_id": "uid-B", "ime": "Zoran", "prezime": "Zorić", "firma": "", "email": "z@b.rs", "status": "aktivan", "tip": "fizicko_lice"},
        ],
        "predmet_klijenti": [],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    # Plan/feature politika nije predmet ovog testa (tenant granica jeste): feature je uključen.
    import shared.permissions as perm

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _zavisnosti(feature):
        return None
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _zavisnosti)
    import shared.usage as us

    async def _potrosi(*a, **kw):
        return None
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_potrosi))
    yield k, b
    ocisti()


def test_kreiranje_klijenta_vlasnik_iz_tokena(ok):
    k, b = ok
    r = k.post("/klijenti", json={"ime": "Mila", "prezime": "Milić", "user_id": "uid-B"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    kid = r.json()["klijent"]["id"]
    assert [x for x in b.tabele["klijenti"] if x["id"] == kid][0]["user_id"] == "uid-A"


def test_pretraga_vidi_samo_svoje(ok):
    k, _ = ok
    a = k.get("/klijenti", params={"pretraga": "Zor"}, headers=zaglavlje("A"))
    assert a.status_code == 200, a.text
    assert a.json()["klijenti"] == []
    b_ = k.get("/klijenti", params={"pretraga": "Zor"}, headers=zaglavlje("B"))
    assert [x["id"] for x in b_.json()["klijenti"]] == ["kl-B1"]


def test_lista_ne_vraca_sifrovana_polja(ok):
    k, _ = ok
    r = k.get("/klijenti", headers=zaglavlje("A"))
    assert r.status_code == 200
    assert "ENC-JMBG-A" not in r.text and "jmbg" not in r.text.lower()


def test_vezivanje_svog_klijenta_za_svoj_predmet(ok):
    k, b = ok
    r = k.post(f"/api/predmeti/{PA}/confirm-links", json={"klijent_ids": ["kl-A1"], "uloga": "stranka"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["linked_klijenti"] == ["kl-A1"]
    d = k.get(f"/api/predmeti/{PA}", headers=zaglavlje("A")).json()
    assert [x["id"] for x in d["klijenti_linked"]] == ["kl-A1"]


def test_tudj_klijent_se_ne_vezuje(ok):
    k, b = ok
    r = k.post(f"/api/predmeti/{PA}/confirm-links", json={"klijent_ids": ["kl-B1"]}, headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["linked_klijenti"] == []
    assert b.tabele["predmet_klijenti"] == []


def test_tudj_predmet_se_ne_vezuje(ok):
    k, b = ok
    r = k.post(f"/api/predmeti/{PB}/confirm-links", json={"klijent_ids": ["kl-A1"]}, headers=zaglavlje("A"))
    assert r.status_code >= 400
    assert b.tabele["predmet_klijenti"] == []


def test_coi_gleda_samo_podatke_pozivaoca(ok):
    k, _ = ok
    # „Zoran Zorić" postoji SAMO kod B. A ne sme da dobije nalaz iz B-ovih podataka.
    r = k.post("/api/conflict-check", json={"ime_prezime": "Zoran Zorić"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert r.json()["konflikti"] == [] and "TAJNI" not in r.text


def test_coi_nalazi_preklapanje_u_svom_predmetu(ok):
    k, _ = ok
    r = k.post("/api/conflict-check", json={"ime_prezime": "Petar Petrović"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "conflict" and d["provera_potpuna"] is True
    assert any(x["predmet_id"] == PA for x in d["konflikti"])


def test_coi_pad_sloja_nije_cisto(ok):
    k, b = ok
    b.greske["predmeti"] = RuntimeError("baza nedostupna")
    r = k.post("/api/conflict-check", json={"ime_prezime": "Nepostojeći Čovek"}, headers=zaglavlje("A"))
    d = r.json()
    assert d["provera_potpuna"] is False and d["status"] != "clear"


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []
