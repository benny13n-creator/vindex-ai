# -*- coding: utf-8 -*-
"""NS008 Task 10 — overeno znanje kancelarije kroz postojeći Pinecone namespace vlasnika.

Lažni Pinecone primenjuje STVARNI filter iz `rag_acl.filter_za_namespace_vlasnika` (type $in, predmet_id $in),
pa test dokazuje da se ACL zaista prosleđuje. AI_GENERATED isključen; nepoznato poreklo ne nadjačava overeno ni
sa višim skorom; overen vektor čiji je staging izvor odbijen se ne vraća; skor je „sličnost teksta".
"""
import types
from datetime import date

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

DANAS = date(2026, 10, 10)
K1 = "e1e1e1e1-1010-4000-8000-000000000001"
PA, PA2, PB = ("aaaaaaaa-1010-4000-8000-00000000000a", "aaaaaaaa-1010-4000-8000-00000000000b",
               "bbbbbbbb-1010-4000-8000-00000000000b")
NS = f"kancelarija_{K1}"


def _v(vid, pid, score, **md):
    return {"id": vid, "score": score, "ns": NS, "metadata": {"predmet_id": pid, "type": "draft_final",
                                                             "text": f"Tekst {vid}", **md}}


VEKTORI = [
    _v("v-overen", PA, 0.70, origin="LAWYER_VERIFIED", parent_id="s-ok", origin_chain=["AI_GENERATED", "LAWYER_VERIFIED"],
       created_at="2026-09-01T00:00:00+00:00", source_filename="Nacrt — Tužba"),
    _v("v-legacy", PA, 0.99, created_at="2020-01-01T00:00:00+00:00"),                      # bez porekla
    _v("v-ai", PA, 0.98, origin="AI_GENERATED"),
    _v("v-opozvan", PA2, 0.95, origin="LAWYER_VERIFIED", parent_id="s-odbijen"),
    _v("v-bez-roditelja", PA, 0.94, origin="LAWYER_VERIFIED"),
    _v("v-dok", PA, 0.80, type="case_doc", origin="CLIENT_DOC", source_filename="Ugovor.pdf"),
    _v("v-povucen", PA, 0.60, origin="LAWYER_VERIFIED", parent_id="s-ok2", status="DEPRECATED"),
    _v("v-B", PB, 0.99, origin="LAWYER_VERIFIED", parent_id="s-B"),                        # B-ov predmet
]


def _poklapa(md, f):
    for kljuc, uslov in (f or {}).items():
        if "$in" in uslov and md.get(kljuc) not in uslov["$in"]:
            return False
    return True


@pytest.fixture
def svet(monkeypatch):
    _, b = f8.pripremi(monkeypatch, {
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": u, "status": "ACTIVE"} for u in ("uid-A", "uid-B")],
        "predmeti": [{"id": PA, "user_id": "uid-A", "status": "zatvoren"}, {"id": PA2, "user_id": "uid-A", "status": "zatvoren"},
                     {"id": PB, "user_id": "uid-B", "status": "zatvoren"}],
        "predmet_delegiranja": [],
        "staging_memory": [{"id": "s-ok", "user_id": "uid-A", "predmet_id": PA, "status": "approved", "is_lawyer_approved": True},
                           {"id": "s-ok2", "user_id": "uid-A", "predmet_id": PA, "status": "approved", "is_lawyer_approved": True},
                           {"id": "s-odbijen", "user_id": "uid-A", "predmet_id": PA2, "status": "rejected", "is_lawyer_approved": False},
                           {"id": "s-B", "user_id": "uid-B", "predmet_id": PB, "status": "approved", "is_lawyer_approved": True}],
    })
    from app.services import retrieve as rt
    pozivi = []

    def _pretraga(vec, ns, k, filt):
        pozivi.append({"ns": ns, "filter": filt, "k": k})
        hits = [v for v in VEKTORI if v["ns"] == ns and _poklapa(v["metadata"], filt)]
        hits.sort(key=lambda v: -v["score"])
        return [types.SimpleNamespace(id=v["id"], score=v["score"], metadata=dict(v["metadata"])) for v in hits[:k]]
    monkeypatch.setattr(rt, "_pretraga_ns", _pretraga)
    monkeypatch.setattr(rt, "_ugradi_query", lambda q: [0.1, 0.2])
    yield b, pozivi
    f8.ocisti()


def _ids(r):
    return [dict(it.attrs)["vektor_id"] for it in r["stavke"]]


def test_hijerarhija_poverenja_i_iskljucenja(svet):
    b, pozivi = svet
    r = lb.pretrazi_znanje_kancelarije(b, "uid-A", "isplata zarade", today=DANAS)
    assert pozivi[0]["ns"] == NS
    assert pozivi[0]["filter"]["predmet_id"]["$in"] == sorted([PA, PA2])
    ids = _ids(r)
    assert ids[0] == "v-overen", "overeno ispred nepoznatog iako je nepoznato imalo skor 0.99"
    assert ids.index("v-dok") < ids.index("v-legacy")
    assert "v-ai" not in ids and "v-opozvan" not in ids and "v-bez-roditelja" not in ids and "v-B" not in ids
    assert ids[-1] == "v-legacy"
    po = {dict(it.attrs)["vektor_id"]: it for it in r["stavke"]}
    o = po["v-overen"].to_dict()
    assert o["trust_class"] == lb.LAWYER_VERIFIED_ARTIFACT and o["source_ref"] == {"table": "staging_memory", "id": "s-ok"}
    assert o["lineage"] == ["AI_GENERATED", "LAWYER_VERIFIED"]
    assert o["attrs"]["slicnost_napomena"].startswith("retrieval sličnost") and "pravn" in r["napomena"]
    assert po["v-legacy"].trust_class == lb.UNKNOWN_LEGACY and po["v-legacy"].to_dict()["attrs"]["moze_biti_zastarelo"]
    assert po["v-dok"].trust_class == lb.SOURCE_CASE_FACT
    assert po["v-povucen"].validity == lb.DEPRECATED and not po["v-povucen"].trusted


def test_kolega_iz_iste_kancelarije_ne_vidi_tudje_vektore(svet):
    b, pozivi = svet
    r = lb.pretrazi_znanje_kancelarije(b, "uid-B", "isplata zarade", today=DANAS)
    assert pozivi[0]["filter"]["predmet_id"]["$in"] == [PB]
    assert _ids(r) == ["v-B"]


def test_odbrana_u_dubini_kad_filter_ne_radi(svet, monkeypatch):
    b, _ = svet
    from app.services import retrieve as rt
    monkeypatch.setattr(rt, "_pretraga_ns", lambda vec, ns, k, filt: [
        types.SimpleNamespace(id=v["id"], score=v["score"], metadata=dict(v["metadata"])) for v in VEKTORI])
    r = lb.pretrazi_znanje_kancelarije(b, "uid-B", "x", today=DANAS)
    assert _ids(r) == ["v-B"]


def test_tudj_predmet_kao_fokus_nije_autorizovan(svet):
    b, pozivi = svet
    r = lb.pretrazi_znanje_kancelarije(b, "uid-B", "x", today=DANAS, predmet_id=PA)
    assert r["stanje"] == lb.NOT_AUTHORIZED and pozivi == []


def test_pad_pinecone_se_propusta(svet, monkeypatch):
    b, _ = svet
    from app.services import retrieve as rt

    def _pad(*a, **k):
        raise RuntimeError("pinecone down")
    monkeypatch.setattr(rt, "_pretraga_ns", _pad)
    with pytest.raises(RuntimeError):
        lb.pretrazi_znanje_kancelarije(b, "uid-A", "x", today=DANAS)


def test_prazan_upit_bez_troska(svet, monkeypatch):
    b, pozivi = svet
    from app.services import retrieve as rt
    monkeypatch.setattr(rt, "_ugradi_query", lambda q: (_ for _ in ()).throw(AssertionError("embedding")))
    assert lb.pretrazi_znanje_kancelarije(b, "uid-A", "   ", today=DANAS)["stanje"] == lb.EMPTY
    assert pozivi == []
