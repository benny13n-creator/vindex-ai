# -*- coding: utf-8 -*-
"""NS008 Task 2 — ishod predmeta: JEDINI izvor je ljudski outcome_log.

Status „zatvoren" bez ishoda → OUTCOME_UNKNOWN; „pobeda" u hronologiji → i dalje UNKNOWN; ljudski ishod →
HUMAN_CONFIRMED_OUTCOME; tuđ predmet → nemoguće; ponovljeno slanje → jedan logički ishod, bez ponovnog
uvećavanja brojača.
"""
import uuid

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

PA = "aaaaaaaa-2222-4000-8000-00000000000a"   # A, zatvoren, bez ishoda, hronologija kaže „pobeda"
PA2 = "aaaaaaaa-2222-4000-8000-00000000000b"  # A, aktivan → dobija ljudski ishod kroz rutu
PB = "bbbbbbbb-2222-4000-8000-00000000000b"   # B


def H(ko="A", kljuc=None):
    h = f8.zaglavlje(ko)
    if kljuc:
        h["Idempotency-Key"] = kljuc
    return h


@pytest.fixture
def svet(monkeypatch):
    k, baza = f8.pripremi(monkeypatch, {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Zatvoren bez ishoda", "status": "zatvoren", "tip": "radni"},
            {"id": PA2, "user_id": "uid-A", "naziv": "Aktivan A", "status": "aktivan", "tip": "radni"},
            {"id": PB, "user_id": "uid-B", "naziv": "Tajni predmet B", "status": "aktivan", "tip": "radni"},
        ],
        "predmet_hronologija": [
            {"predmet_id": PA, "user_id": "uid-A", "dogadjaj": "Predmet zatvoren. Ishod: pobeda", "datum_iso": "2026-01-01"},
        ],
        "outcome_log": [], "case_patterns": [], "recommendation_log": [], "lessons_learned": [],
        "events": [], "case_actions": [], "v2_mutation_idempotency": [],
    })
    yield k, baza
    f8.ocisti()


def _predmet(baza, pid):
    return next(p for p in baza.tabele["predmeti"] if p["id"] == pid)


def test_zatvoren_bez_ishoda_je_nepoznat_i_pored_pobede_u_hronologiji(svet):
    _, baza = svet
    p = _predmet(baza, PA)
    redovi = lb.ucitaj_ishode(baza, [p])
    v = lb.outcome_view(p, redovi.get(PA))
    assert v["status"] == lb.OUTCOME_UNKNOWN and v["ishod"] is None and v["item"] is None


def test_legacy_status_uspesno_nije_ishod(svet):
    _, baza = svet
    p = {"id": PA, "user_id": "uid-A", "status": "uspesno"}
    assert lb.outcome_view(p, None)["status"] == lb.OUTCOME_NOT_TERMINAL


def test_ljudski_ishod_kroz_rutu_je_human_confirmed(svet):
    k, baza = svet
    r = k.post("/api/learning/outcome", headers=H("A"),
               json={"predmet_id": PA2, "ishod": "nagodba", "presudni_faktori": ["svedoci", "vestacenje"]})
    assert r.status_code == 200, r.text
    assert _predmet(baza, PA2)["status"] == "zatvoren"
    p = _predmet(baza, PA2)
    v = lb.outcome_view(p, lb.ucitaj_ishode(baza, [p]).get(PA2))
    it = v["item"]
    assert v["status"] == lb.OUTCOME_RECORDED and v["ishod"] == "nagodba"
    assert it.trust_class == lb.HUMAN_CONFIRMED_OUTCOME and it.human_verified and it.validity == lb.CURRENT
    assert it.outcome_ref == baza.tabele["outcome_log"][0]["id"]
    assert it.to_dict()["attrs"]["presudni_faktori"] == ("svedoci", "vestacenje")


def test_ishod_ponovo_otvorenog_predmeta_je_zastareo_ne_vazeci(svet):
    k, baza = svet
    k.post("/api/learning/outcome", headers=H("A"), json={"predmet_id": PA2, "ishod": "pobeda"})
    _predmet(baza, PA2)["status"] = "aktivan"
    p = _predmet(baza, PA2)
    v = lb.outcome_view(p, lb.ucitaj_ishode(baza, [p]).get(PA2))
    assert v["status"] == lb.OUTCOME_REOPENED and v["item"].validity == lb.STALE


def test_tudj_predmet_ishod_nemoguc(svet):
    k, baza = svet
    r = k.post("/api/learning/outcome", headers=H("B"), json={"predmet_id": PA2, "ishod": "poraz"})
    assert r.status_code == 404
    assert baza.tabele["outcome_log"] == [] and _predmet(baza, PA2)["status"] == "aktivan"


def test_podmetnut_red_tudjeg_vlasnika_se_ne_cita(svet):
    _, baza = svet
    baza.tabele["outcome_log"].append({"id": str(uuid.uuid4()), "predmet_id": PA, "user_id": "uid-B", "ishod": "pobeda"})
    p = _predmet(baza, PA)
    assert lb.ucitaj_ishode(baza, [p]) == {}
    assert lb.outcome_view(p, baza.tabele["outcome_log"][0])["status"] == lb.OUTCOME_UNKNOWN


def test_nevazeci_ishod_u_redu_se_ne_cita():
    p = {"id": PA, "user_id": "uid-A", "status": "zatvoren"}
    assert lb.outcome_view(p, {"id": "x", "predmet_id": PA, "user_id": "uid-A", "ishod": "u_toku"})["status"] == lb.OUTCOME_UNKNOWN


def test_ponovljeno_slanje_bez_kljuca_jedan_logicki_ishod(svet):
    k, baza = svet
    telo = {"predmet_id": PA2, "ishod": "pobeda", "presudni_faktori": ["svedoci"]}
    r1 = k.post("/api/learning/outcome", headers=H("A"), json=telo).json()
    r2 = k.post("/api/learning/outcome", headers=H("A"), json=telo).json()
    assert r1["ponovljen_ishod"] is False and r2["ponovljen_ishod"] is True
    assert len(baza.tabele["outcome_log"]) == 1
    cp = baza.tabele["case_patterns"]
    assert len(cp) == 1 and cp[0]["pobede"] == 1 and cp[0]["ukupno"] == 1


def test_ispravka_ishoda_menja_red_ali_ne_duplira_brojace(svet):
    k, baza = svet
    k.post("/api/learning/outcome", headers=H("A"), json={"predmet_id": PA2, "ishod": "pobeda", "presudni_faktori": ["svedoci"]})
    r = k.post("/api/learning/outcome", headers=H("A"), json={"predmet_id": PA2, "ishod": "poraz", "presudni_faktori": ["svedoci"]})
    assert r.json()["ponovljen_ishod"] is False
    assert len(baza.tabele["outcome_log"]) == 1 and baza.tabele["outcome_log"][0]["ishod"] == "poraz"
    cp = baza.tabele["case_patterns"]
    assert len(cp) == 1 and cp[0]["ukupno"] == 1


def test_isti_idempotency_kljuc_izvrsava_rutu_jednom(svet):
    k, baza = svet
    kljuc = str(uuid.uuid4())
    telo = {"predmet_id": PA2, "ishod": "pobeda", "presudni_faktori": ["svedoci"]}
    r1 = k.post("/api/learning/outcome", headers=H("A", kljuc), json=telo)
    r2 = k.post("/api/learning/outcome", headers=H("A", kljuc), json=telo)
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json(), "sačuvan odgovor, ruta se ne izvršava ponovo"
    assert r2.json()["ponovljen_ishod"] is False
    assert sum(1 for d in baza.dnevnik if d["tabela"] == "outcome_log" and d["radnja"] == "upsert") == 1


def test_baza_ishoda_nedostupna_ne_zatvara_predmet(svet):
    k, baza = svet
    baza.greske["outcome_log"] = Exception("db down")
    r = k.post("/api/learning/outcome", headers=H("A"), json={"predmet_id": PA2, "ishod": "pobeda"})
    assert r.status_code == 503
    assert _predmet(baza, PA2)["status"] == "aktivan"


def test_ucitaj_ishode_ne_guta_gresku(svet):
    _, baza = svet
    baza.greske["outcome_log"] = Exception("db down")
    with pytest.raises(Exception):
        lb.ucitaj_ishode(baza, [_predmet(baza, PA)])


def test_ponovljen_ishod_ne_pokrece_ponovo_gpt_lekcije(svet, monkeypatch):
    k, _ = svet
    from services.learning_engine import learning
    pozivi = []

    async def _gen(**kw):
        pozivi.append(kw["predmet_id"])
        return []

    async def _sacuvaj(*a, **kw):
        return 0
    monkeypatch.setattr(learning, "generate_lessons_learned", _gen)
    monkeypatch.setattr(learning, "save_lessons", _sacuvaj)
    telo = {"predmet_id": PA2, "ishod": "pobeda", "generisi_lekcije": True}
    k.post("/api/learning/outcome", headers=H("A"), json=telo)
    k.post("/api/learning/outcome", headers=H("A"), json=telo)
    assert pozivi == [PA2], "isti ishod dva puta = jedan poziv modela"
