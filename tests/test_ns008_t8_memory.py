# -*- coding: utf-8 -*-
"""NS008 Task 8 — memorija kancelarije i graf: beleške i veze, nikad „proverena činjenica" ni uzrok.

A i B su u istoj kancelariji, C je uklonjen član, D je u drugoj kancelariji. Beleška o sudiji je deljena;
beleška/veza vezana za A-ov privatni predmet ili klijenta nije vidljiva B-u. Čitanje ne upisuje ništa.
"""
import json
from datetime import date

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

DANAS = date(2026, 10, 10)
K1 = "e1e1e1e1-8888-4000-8000-000000000001"
K2 = "e2e2e2e2-8888-4000-8000-000000000002"
PA = "aaaaaaaa-8888-4000-8000-00000000000a"
KL_A = "c1c1c1c1-8888-4000-8000-00000000000a"


def _m(mid, **kw):
    base = {"id": mid, "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "sudija", "entity_id": "Petrović",
            "entity_name": "Sudija Petrović", "tip": "obrazac", "sadrzaj": "Insistira na tabelarnom prikazu rokova.",
            "vaznost": "visoka", "aktivan": True, "izvor": "manual", "potvrde_count": 3, "expires_at": None,
            "zastarela": False, "created_at": "2026-09-01T00:00:00+00:00"}
    base.update(kw)
    return base


@pytest.fixture
def baza(monkeypatch):
    _, b = f8.pripremi(monkeypatch, {
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}, {"id": K2, "admin_uid": "uid-Y"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": "uid-A", "status": "ACTIVE"},
                                {"kancelarija_id": K1, "user_id": "uid-B", "status": "ACTIVE"},
                                {"kancelarija_id": K1, "user_id": "uid-C", "status": "REMOVED"},
                                {"kancelarija_id": K2, "user_id": "uid-D", "status": "ACTIVE"}],
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv Gradnja Invest DOO", "status": "zatvoren"}],
        "klijenti": [{"id": KL_A, "user_id": "uid-A", "ime": "Gradnja Invest DOO"}],
        "predmet_delegiranja": [],
        "memory_entries": [
            _m("m-sud"),
            _m("m-pred", entity_type="predmet", entity_id=PA, entity_name="Petrović protiv Gradnja Invest DOO",
               sadrzaj="Klijent popušta pod pritiskom roka."),
            _m("m-klij", entity_type="klijent", entity_id=KL_A, entity_name="Gradnja Invest DOO",
               sadrzaj="Plaća sa zakašnjenjem."),
            _m("m-auto", izvor="auto", sadrzaj="Automatski izveden obrazac."),
            _m("m-istekla", expires_at="2026-01-01", sadrzaj="Stara napomena o sudu."),
            _m("m-neaktivna", aktivan=False, sadrzaj="Povučena napomena."),
            _m("m-k2", kancelarija_id=K2, user_id="uid-D", sadrzaj="Tuđa kancelarija."),
        ],
        "memory_graph_edges": [
            {"id": "g-opsta", "kancelarija_id": K1, "from_type": "partner", "from_id": "uid-A", "from_naziv": "Partner A",
             "to_type": "argument", "to_id": "zastarelost", "to_naziv": "Zastarelost", "relacija": "koristio_argument",
             "predmet_id": None, "ishod": None},
            {"id": "g-pred", "kancelarija_id": K1, "from_type": "argument", "from_id": "zastarelost",
             "from_naziv": "Zastarelost", "to_type": "predmet", "to_id": PA, "to_naziv": "Petrović protiv Gradnja Invest DOO",
             "relacija": "primenjen_u", "predmet_id": PA, "ishod": "pobeda"},
            {"id": "g-klij", "kancelarija_id": K1, "from_type": "klijent", "from_id": KL_A, "from_naziv": "Gradnja Invest DOO",
             "to_type": "sudija", "to_id": "Petrović", "to_naziv": "Sudija Petrović", "relacija": "pred_sudijom"},
        ],
    })
    yield b
    f8.ocisti()


def _ids(r, kljuc):
    return {it.source_id for it in r[kljuc]}


def test_kolega_vidi_opste_beleske_ali_ne_tudje_predmete_i_klijente(baza):
    b = lb.ucitaj_memoriju(baza, "uid-B", today=DANAS)
    assert _ids(b, "beleske") == {"m-sud", "m-auto", "m-istekla"}
    assert _ids(b, "veze") == {"g-opsta"}
    tekst = json.dumps([it.to_dict() for it in b["beleske"] + b["veze"]], ensure_ascii=False)
    for zabranjeno in ("Gradnja", PA, KL_A, "pobeda", "popušta", "zakašnjenjem"):
        assert zabranjeno not in tekst


def test_vlasnik_vidi_svoje_predmetne_i_klijentske(baza):
    a = lb.ucitaj_memoriju(baza, "uid-A", today=DANAS)
    assert _ids(a, "beleske") == {"m-sud", "m-pred", "m-klij", "m-auto", "m-istekla"}
    assert _ids(a, "veze") == {"g-opsta", "g-pred", "g-klij"}


def test_beleska_je_beleska_ne_cinjenica(baza):
    b = {it.source_id: it for it in lb.ucitaj_memoriju(baza, "uid-B", today=DANAS)["beleske"]}
    s = b["m-sud"]
    assert s.trust_class == lb.HUMAN_MEMORY_NOTE and s.validity == lb.UNKNOWN, "bez roka važenja → nepoznato"
    d = s.to_dict()
    assert d["excerpt"] == "Insistira na tabelarnom prikazu rokova.", 'doslovno, bez dodatog uvek'
    assert d["attrs"]["potvrde_count"] == 3 and d["attrs"]["sopstvena"] is False
    assert "nije proverena činjenica" in d["attrs"]["napomena"]
    assert b["m-auto"].trust_class == lb.AI_CANDIDATE_LESSON and not b["m-auto"].human_verified
    assert b["m-istekla"].validity == lb.STALE


def test_veza_bez_uzrocnosti_i_bez_ishoda_kao_istine(baza):
    a = {it.source_id: it for it in lb.ucitaj_memoriju(baza, "uid-A", today=DANAS)["veze"]}
    g = a["g-pred"].to_dict()
    assert g["trust_class"] == lb.EXPLICIT_GRAPH_RELATION
    assert g["attrs"]["uzrocnost"] is False and g["attrs"]["upisano_uz_vezu"] == "pobeda"
    assert "Ne dokazuje" in g["attrs"]["napomena"]
    assert g["outcome_ref"] is None, "ishod na vezi nije HUMAN_CONFIRMED_OUTCOME"


def test_uklonjen_clan_i_druga_kancelarija(baza):
    c = lb.ucitaj_memoriju(baza, "uid-C", today=DANAS)
    assert c == {"kancelarija": False, "beleske": [], "veze": []}
    d = lb.ucitaj_memoriju(baza, "uid-D", today=DANAS)
    assert _ids(d, "beleske") == {"m-k2"} and _ids(d, "veze") == set()


def test_citanje_ne_menja_istekle_beleske(baza):
    baza.dnevnik.clear()
    lb.ucitaj_memoriju(baza, "uid-A", today=DANAS)
    assert {d["radnja"] for d in baza.dnevnik} == {"select"}
    assert next(m for m in baza.tabele["memory_entries"] if m["id"] == "m-istekla")["zastarela"] is False


def test_delegiran_predmet_otvara_predmetnu_belesku(baza):
    baza.tabele["predmet_delegiranja"].append({"predmet_id": PA, "na_user_id": "uid-B", "status": "aktivno"})
    b = lb.ucitaj_memoriju(baza, "uid-B", today=DANAS)
    assert "m-pred" in _ids(b, "beleske") and "g-pred" in _ids(b, "veze")
    assert "m-klij" not in _ids(b, "beleske"), "klijent i dalje pripada A"
