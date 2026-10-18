# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 3: `case_patterns` (pobede/porazi po presudnom faktoru) mora da odgovara zabeleženim ishodima.

`case_patterns` čitaju `court_predictor` (kalibracija pouzdanosti), `case_intelligence`, `benchmarking`, `cio`.
Zatečeno (`routers/learning.py::zabeleži_ishod`): brojači se UVEĆAVAJU samo pri prvom ishodu predmeta. Ispravka
ishoda (pobeda → poraz) zadržava staru pobedu zauvek; promena faktora zadržava stari faktor; promena vrste spora
ostavlja doprinos u staroj vrsti; dva istovremena prva slanja istog ishoda oba uvećavaju.

Ugovor posle ispravke: brojači za (korisnik, vrsta spora) su funkcija `outcome_log` (jedan red po predmetu), pa su
ponovljeno slanje, ispravka i trka idempotentni. Stvarna ruta kroz TestClient, NS008 baza u memoriji.
"""
import pytest

import tests.ns008_fake as f8

PA = "aaaaaaaa-3333-4000-8000-00000000000a"
PA2 = "aaaaaaaa-3333-4000-8000-00000000000b"
PB = "bbbbbbbb-3333-4000-8000-00000000000b"


@pytest.fixture
def svet(monkeypatch):
    k, baza = f8.pripremi(monkeypatch, {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "A1", "status": "aktivan", "tip": "radni"},
            {"id": PA2, "user_id": "uid-A", "naziv": "A2", "status": "aktivan", "tip": "radni"},
            {"id": PB, "user_id": "uid-B", "naziv": "B1", "status": "aktivan", "tip": "radni"},
        ],
        "outcome_log": [], "case_patterns": [], "recommendation_log": [], "lessons_learned": [],
        "predmet_hronologija": [], "events": [], "case_actions": [], "v2_mutation_idempotency": [],
    })
    yield k, baza
    f8.ocisti()


def _posalji(k, pid, ishod, faktori, ko="A"):
    r = k.post("/api/learning/outcome", headers=f8.zaglavlje(ko),
               json={"predmet_id": pid, "ishod": ishod, "presudni_faktori": faktori})
    assert r.status_code == 200, r.text
    return r.json()


def _obrasci(baza, uid="uid-A", tip="radni"):
    return {r["faktor"]: (r["pobede"], r["porazi"], r["ukupno"]) for r in baza.tabele["case_patterns"]
            if r["user_id"] == uid and r["tip_spora"] == tip and (r["pobede"] or r["porazi"] or r["ukupno"])}


def test_ispravka_pobede_u_poraz_ne_zadrzava_staru_pobedu(svet):
    k, baza = svet
    _posalji(k, PA, "pobeda", ["svedoci"])
    _posalji(k, PA, "poraz", ["svedoci"])
    assert _obrasci(baza) == {"svedoci": (0, 1, 1)}, "ispravljen ishod i dalje broji staru pobedu"


def test_promena_faktora_skida_doprinos_starog(svet):
    k, baza = svet
    _posalji(k, PA, "pobeda", ["svedoci"])
    _posalji(k, PA, "pobeda", ["vestacenje"])
    assert _obrasci(baza) == {"vestacenje": (1, 0, 1)}


def test_promena_vrste_spora_premesta_doprinos(svet):
    k, baza = svet
    _posalji(k, PA, "pobeda", ["svedoci"])
    next(p for p in baza.tabele["predmeti"] if p["id"] == PA).update({"tip": "porodicni", "status": "aktivan"})
    _posalji(k, PA, "poraz", ["svedoci"])
    assert _obrasci(baza, tip="radni") == {}, "doprinos ostao u staroj vrsti spora"
    assert _obrasci(baza, tip="porodicni") == {"svedoci": (0, 1, 1)}


def test_dva_predmeta_se_sabiraju(svet):
    k, baza = svet
    _posalji(k, PA, "pobeda", ["svedoci"])
    _posalji(k, PA2, "poraz", ["svedoci", "vestacenje"])
    assert _obrasci(baza) == {"svedoci": (1, 1, 2), "vestacenje": (0, 1, 1)}


def test_ponovljeno_slanje_ne_uvecava(svet):
    k, baza = svet
    for _ in range(3):
        _posalji(k, PA, "pobeda", ["svedoci"])
    assert _obrasci(baza) == {"svedoci": (1, 0, 1)}


def test_nagodba_broji_ukupno_ali_nije_pobeda_ni_poraz(svet):
    k, baza = svet
    _posalji(k, PA, "nagodba", ["svedoci"])
    assert _obrasci(baza) == {"svedoci": (0, 0, 1)}


def test_trka_dva_prva_slanja_ne_duplira(svet, monkeypatch):
    """Model trke: drugi zahtev je pročitao `outcome_log` PRE nego što je prvi upisao (oba vide „nema ishoda")."""
    k, baza = svet
    _posalji(k, PA, "pobeda", ["svedoci"])
    izvorni = baza.table

    def zastareo_pogled(ime):
        u = izvorni(ime)
        if ime == "outcome_log":
            iz = u.execute

            def execute():
                if u.radnja[0] == "select" and ("eq", "predmet_id", PA) in u.filt:
                    return type("R", (), {"data": [], "count": 0})()
                return iz()
            u.execute = execute
        return u
    monkeypatch.setattr(baza, "table", zastareo_pogled)
    _posalji(k, PA, "pobeda", ["svedoci"])
    assert _obrasci(baza) == {"svedoci": (1, 0, 1)}, "dva istovremena prva slanja istog ishoda su dvaput brojana"


def test_tudji_obrasci_netaknuti(svet):
    k, baza = svet
    _posalji(k, PB, "pobeda", ["svedoci"], ko="B")
    _posalji(k, PA, "poraz", ["svedoci"])
    assert _obrasci(baza, uid="uid-B") == {"svedoci": (1, 0, 1)}
    assert _obrasci(baza) == {"svedoci": (0, 1, 1)}


def test_tudj_predmet_ne_upisuje_nista(svet):
    k, baza = svet
    r = k.post("/api/learning/outcome", headers=f8.zaglavlje("A"),
               json={"predmet_id": PB, "ishod": "pobeda", "presudni_faktori": ["svedoci"]})
    assert r.status_code == 404
    assert baza.tabele["outcome_log"] == [] and baza.tabele["case_patterns"] == []


def test_zatvaranje_ne_izmislja_ishod(svet):
    """Bez ljudskog ishoda nema reda u outcome_log ni u case_patterns — ni kada je predmet zatvoren."""
    k, baza = svet
    next(p for p in baza.tabele["predmeti"] if p["id"] == PA)["status"] = "zatvoren"
    _posalji(k, PA2, "pobeda", ["svedoci"])
    assert [o["predmet_id"] for o in baza.tabele["outcome_log"]] == [PA2]


def test_tacno_puna_strana_ne_obara_preracun(svet, monkeypatch):
    """Broj ishoda = tačno veličina strane: sledeći `range` je iza kraja → PostgREST PGRST103. Preračun mora da
    završi sa tačnim brojem (ranije nezaštićeno — uhvatila ga je klasna provera `test_z017_registar_offset`)."""
    import routers.learning as L
    from shared.stranicenje import KOD_VAN_OPSEGA
    k, baza = svet
    monkeypatch.setattr(L, "_STRANA", 1)
    izvorni = baza.table

    def sa_416(ime):
        u = izvorni(ime)
        if ime == "outcome_log":
            iz = u.execute

            def execute():
                if (u.radnja[0] == "select" and u.opseg and any(f[1] == "tip_spora" for f in u.filt)
                        and u.opseg[0] >= len(baza.tabele["outcome_log"])):
                    e = Exception("Requested range not satisfiable")
                    e.code = KOD_VAN_OPSEGA
                    raise e
                return iz()
            u.execute = execute
        return u
    monkeypatch.setattr(baza, "table", sa_416)
    _posalji(k, PA, "pobeda", ["svedoci"])
    assert _obrasci(baza) == {"svedoci": (1, 0, 1)}
