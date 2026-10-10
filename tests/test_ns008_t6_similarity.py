# -*- coding: utf-8 -*-
"""NS008 Task 6 — objašnjiva, bezbedna sličnost predmeta.

Adversarijalno (obavezno): A i B su u ISTOJ kancelariji; A ima privatan zatvoren predmet; B pita Law Brain →
B ne dobija ni naziv, ni klijenta, ni činjenice, ni Genome, ni ishod, ni SIGNAL POSTOJANJA (odgovor je
bajt-identičan sa i bez A-ovog predmeta). Ishod nije ulaz u bodove.
"""
import json

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

KANC = "kkkkkkkk-6666-4000-8000-00000000000k".replace("k", "e")
PA_CUR = "aaaaaaaa-6666-4000-8000-000000000001"
PA_OLD = "aaaaaaaa-6666-4000-8000-000000000002"
PA_OLD2 = "aaaaaaaa-6666-4000-8000-000000000003"
PA_AKT = "aaaaaaaa-6666-4000-8000-000000000004"
PA_SUD = "aaaaaaaa-6666-4000-8000-000000000005"
PB_CUR = "bbbbbbbb-6666-4000-8000-000000000001"
SUD = "Osnovni sud u Beogradu"


def _p(pid, uid, naziv, status="zatvoren", tip="radni", oblast="radno", g=3, upd="2026-09-01"):
    return {"id": pid, "user_id": uid, "naziv": naziv, "tip": tip, "oblast": oblast, "status": status,
            "case_dna": {"verzija": g, "rezime": f"Genome {naziv}"}, "updated_at": upd}


def _svet(sa_a_starim=True, delegiranja=()):
    predmeti = [_p(PA_CUR, "uid-A", "A tekući", status="aktivan"),
                _p(PB_CUR, "uid-B", "B tekući", status="aktivan"),
                _p(PA_AKT, "uid-A", "A aktivan sličan", status="aktivan"),
                _p(PA_SUD, "uid-A", "A samo isti sud", tip="porodicni", oblast="porodicno")]
    if sa_a_starim:
        predmeti += [_p(PA_OLD, "uid-A", "Petrović protiv Gradnja Invest DOO"),
                     _p(PA_OLD2, "uid-A", "Jovanović protiv Gradnja Invest DOO", upd="2026-08-01")]
    roc = [{"predmet_id": pid, "user_id": uid, "sud": SUD, "status": "odrzano"}
           for pid, uid in ((PA_CUR, "uid-A"), (PB_CUR, "uid-B"), (PA_OLD, "uid-A"), (PA_SUD, "uid-A"))]
    dok = [{"predmet_id": pid, "user_id": uid, "kategorija": k}
           for pid, uid in ((PA_CUR, "uid-A"), (PB_CUR, "uid-B"), (PA_OLD, "uid-A"), (PA_OLD2, "uid-A"))
           for k in ("svedok", "dokaz")]
    ishodi = [{"id": "o1", "predmet_id": PA_OLD, "user_id": "uid-A", "ishod": "pobeda", "presudni_faktori": []},
              {"id": "o2", "predmet_id": PA_OLD2, "user_id": "uid-A", "ishod": "poraz", "presudni_faktori": []}] \
        if sa_a_starim else []
    return {
        "predmeti": predmeti, "rocista": roc, "predmet_dokazi": dok, "outcome_log": ishodi,
        "predmet_issues": [], "predmet_contradictions": [], "staging_memory": [],
        "kancelarije": [{"id": KANC, "admin_uid": "uid-X", "naziv": "Kancelarija"}],
        "kancelarija_clanovi": [{"kancelarija_id": KANC, "user_id": u, "status": "ACTIVE"} for u in ("uid-A", "uid-B")],
        "predmet_delegiranja": list(delegiranja),
    }


@pytest.fixture
def svet(monkeypatch):
    stanje = {}

    def _napravi(**kw):
        stanje["k"], stanje["b"] = f8.pripremi(monkeypatch, _svet(**kw))
        return stanje["b"]
    yield _napravi
    f8.ocisti()


def test_sopstveni_zatvoreni_predmeti_sa_objasnjenjem(svet):
    b = svet()
    r = lb.slicni_predmeti(b, "uid-A", PA_CUR)
    assert r["stanje"] == lb.OK
    ids = [s["predmet_id"] for s in r["stavke"]]
    assert ids[0] == PA_OLD and PA_OLD2 in ids
    assert PA_AKT not in ids, "aktivan predmet nije istorija"
    assert PA_SUD not in ids, "samo isti sud je ispod praga"
    s = r["stavke"][0]
    assert [x["dimenzija"] for x in s["razlozi"]] == ["tip", "oblast", "sud", "dokazi"]
    assert s["bodovi"] == 3 + 2 + 1 + 2
    assert s["zasto"].startswith("Sličan jer: isti tip predmeta (radni); ista oblast (radno); isti sud")
    assert s["ishod"]["status"] == lb.OUTCOME_RECORDED and s["ishod"]["ishod"] == "pobeda"
    assert r["pretrazeno_zavrsenih"] == 3 and "šanse" in r["napomena"]
    assert "%" not in json.dumps(r, ensure_ascii=False)


def test_ishod_nije_ulaz_u_bodove(svet):
    b = svet()
    pt = lb.ucitaj_profile(b, [p for p in b.tabele["predmeti"] if p["id"] == PA_CUR])[PA_CUR]
    kand = lb.ucitaj_profile(b, [p for p in b.tabele["predmeti"] if p["id"] == PA_OLD2])[PA_OLD2]
    osnov = lb.similarity(pt, kand)
    for ishod in ("pobeda", "poraz", None):
        k2 = json.loads(json.dumps(kand))
        k2["ljudski_ishod"] = {"status": lb.OUTCOME_RECORDED if ishod else lb.OUTCOME_UNKNOWN, "ishod": ishod, "item": None}
        assert lb.similarity(pt, k2) == osnov


def test_ista_kancelarija_bez_signala_postojanja(svet):
    sa = lb.slicni_predmeti(svet(sa_a_starim=True), "uid-B", PB_CUR)
    f8.ocisti()
    bez = lb.slicni_predmeti(svet(sa_a_starim=False), "uid-B", PB_CUR)
    tekst = json.dumps(sa, ensure_ascii=False, sort_keys=True)
    assert tekst == json.dumps(bez, ensure_ascii=False, sort_keys=True), "B ne sme ni da nasluti A-ov predmet"
    assert sa["stavke"] == [] and sa["pretrazeno_zavrsenih"] == 0
    for zabranjeno in ("Petrović", "Gradnja", PA_OLD, "Genome", "pobeda"):
        assert zabranjeno not in tekst


def test_tudj_tekuci_predmet_nije_autorizovan(svet):
    b = svet()
    r = lb.slicni_predmeti(b, "uid-B", PA_CUR)
    assert r == {"stanje": lb.NOT_AUTHORIZED, "stavke": []}


def test_aktivno_delegiranje_dozvoljava_opozvano_ne(svet):
    b = svet(delegiranja=[{"predmet_id": PA_OLD, "na_user_id": "uid-B", "status": "aktivno"}])
    r = lb.slicni_predmeti(b, "uid-B", PB_CUR)
    assert [s["predmet_id"] for s in r["stavke"]] == [PA_OLD] and r["stavke"][0]["sopstveni"] is False
    f8.ocisti()
    b = svet(delegiranja=[{"predmet_id": PA_OLD, "na_user_id": "uid-B", "status": "opozvano"}])
    assert lb.slicni_predmeti(b, "uid-B", PB_CUR)["stavke"] == []


def test_predmet_u_brisanju_nije_kandidat(svet):
    b = svet()
    next(p for p in b.tabele["predmeti"] if p["id"] == PA_OLD)["brisanje_zapoceto"] = "2026-10-01"
    ids = [s["predmet_id"] for s in lb.slicni_predmeti(b, "uid-A", PA_CUR)["stavke"]]
    assert PA_OLD not in ids


def test_bez_kolone_oblast_radi_bez_te_dimenzije(svet):
    b = svet()
    b.nepostojece_kolone["predmeti"] = {"oblast"}
    r = lb.slicni_predmeti(b, "uid-A", PA_CUR)
    assert r["stavke"][0]["predmet_id"] == PA_OLD
    assert "oblast" not in [x["dimenzija"] for x in r["stavke"][0]["razlozi"]]


def test_greska_autorizacije_se_propusta(svet):
    b = svet()
    b.greske["predmeti"] = Exception("down")
    with pytest.raises(Exception):
        lb.slicni_predmeti(b, "uid-A", PA_CUR)


def test_bez_modela_i_bez_upisa(svet, monkeypatch):
    b = svet()
    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model")))
    b.dnevnik.clear()
    lb.slicni_predmeti(b, "uid-A", PA_CUR)
    assert {d["radnja"] for d in b.dnevnik} == {"select"}


def test_delegiran_predmet_u_brisanju_nije_kandidat(svet):
    # `rag_acl` filtrira tombstone samo za SOPSTVENE predmete; delegirani put ga ne filtrira — zato Law Brain
    # proverava `brisanje_zapoceto` i sam.
    b = svet(delegiranja=[{"predmet_id": PA_OLD, "na_user_id": "uid-B", "status": "aktivno"}])
    next(p for p in b.tabele["predmeti"] if p["id"] == PA_OLD)["brisanje_zapoceto"] = "2026-10-01"
    assert lb.slicni_predmeti(b, "uid-B", PB_CUR)["stavke"] == []


class _Stub:
    def __init__(self, greske):
        self.greske, self.pozivi = list(greske), []

    def table(self, _t):
        return self

    def select(self, kolone):
        self.pozivi.append(kolone)
        return self

    def in_(self, *a):
        return self

    def execute(self):
        g = self.greske.pop(0) if self.greske else None
        if g:
            raise g
        import types
        return types.SimpleNamespace(data=[{"id": "x"}])


def test_ucitaj_predmete_pada_na_nekolonsku_gresku():
    s = _Stub([Exception("connection reset")])
    with pytest.raises(Exception, match="connection reset"):
        lb.ucitaj_predmete(s, ["x"])
    assert len(s.pozivi) == 1


def test_ucitaj_predmete_suzava_kolone_samo_za_nepostojecu_kolonu():
    s = _Stub([Exception('{"code": "42703", "message": "column predmeti.oblast does not exist"}')])
    assert lb.ucitaj_predmete(s, ["x"]) == [{"id": "x"}]
    assert s.pozivi == list(lb.PREDMET_KOLONE_POKUSAJI[:2])
