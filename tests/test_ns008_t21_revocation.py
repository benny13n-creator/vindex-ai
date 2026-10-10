# -*- coding: utf-8 -*-
"""NS008 Task 21 — opoziv, ispravka i brisanje se šire ODMAH (Law Brain nema izvedeni keš ni indeks).

Kroz STVARNE rute: odobren rad → odbijen (staging reject) nestaje iz Law Brain-a I iz RAG kancelarijske grane
(`retrieve_documents`) iako vektor fizički još postoji; odbijena lekcija nestaje; deaktivirana beleška nestaje;
ispravljen ishod menja opis; predmet u brisanju nestaje i vlasniku i delegatu; uklonjen član gubi memoriju.
Nijedan nepromenjiv revizioni trag se ne briše.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb
from tests.test_ns008_t11_api import PA_CUR, PA_OLD, _tabele


@pytest.fixture
def svet(monkeypatch):
    t = _tabele()
    t["predmet_delegiranja"] = [{"predmet_id": PA_OLD, "na_user_id": "uid-B", "status": "aktivno"}]
    t["audit_immutable"] = [{"action": "staging_approved", "resource_id": "s-ok", "seq": 1}]
    k, b = f8.pripremi(monkeypatch, t)
    yield k, b
    f8.ocisti()


def _ctx(k, ko="A", pid=PA_CUR):
    r = k.get(f"/api/law-brain/predmeti/{pid}", headers=f8.zaglavlje(ko))
    return r.status_code, (r.json() if r.status_code == 200 else None)


def test_opozvan_rad_nestaje_iz_law_brain_i_iz_rag_odmah(svet):
    k, b = svet
    _, d = _ctx(k)
    assert [a["source_ref"]["id"] for a in d["verified_artifacts"]["stavke"]] == ["s-ok"]
    assert k.post("/api/staging/s-ok/reject", headers=f8.zaglavlje("A")).status_code == 200
    _, d = _ctx(k)
    assert d["verified_artifacts"]["stavke"] == []
    sve = {a.source_id: a for a in lb.ucitaj_artefakte(b, [p for p in b.tabele["predmeti"] if p["id"] == PA_OLD])}
    assert sve["s-ok"].state == lb.ART_REJECTED_STILL_INDEXED, "stanje se ne ulepšava: vektor fizički postoji"

    # RAG (jedino usko grlo): isti vektor više se ne servira u odgovorima na pitanja
    import app.services.retrieve as R
    import tests.test_bu004_injection_chunk_quarantine as Q
    vek = SimpleNamespace(id="v-ok", score=0.95, metadata={"text": "Overena tužba — obrazloženje dovoljno dugo za prikaz u kontekstu.",
                                                            "predmet_id": PA_OLD, "type": "draft_final", "origin": "LAWYER_VERIFIED",
                                                            "parent_id": "s-ok", "chunk_index": 0, "source_filename": "Nacrt",
                                                            "article_label": "", "created_at": "2026-08-01"})
    idx = Q._Index(vlasnicki=[vek])
    import shared.deps as deps
    with patch.object(deps, "_get_supa", return_value=b):
        docs, meta = Q._retrieve(idx, acl=(PA_OLD,), ns=Q.NS)
    assert not any("Overena tužba" in d for d in docs), "opozvan overen rad se ne servira u RAG-u"
    b.tabele["staging_memory"][0].update(status="approved", is_lawyer_approved=True)
    with patch.object(deps, "_get_supa", return_value=b):
        docs, _ = Q._retrieve(idx, acl=(PA_OLD,), ns=Q.NS)
    assert any("Overena tužba" in d for d in docs), "kontrola: važeća overa se servira"


def test_rag_fail_closed_kad_staging_nije_citljiv(svet):
    _, b = svet
    import tests.test_bu004_injection_chunk_quarantine as Q
    import shared.deps as deps
    b.greske["staging_memory"] = Exception("down")
    vek = SimpleNamespace(id="v", score=0.95, metadata={"text": "Overena tužba — obrazloženje dovoljno dugo za prikaz.",
                                                         "predmet_id": PA_OLD, "type": "draft_final", "origin": "LAWYER_VERIFIED",
                                                         "parent_id": "s-ok", "chunk_index": 0, "source_filename": "N",
                                                         "article_label": "", "created_at": "2026-08-01"})
    with patch.object(deps, "_get_supa", return_value=b):
        docs, _ = Q._retrieve(Q._Index(vlasnicki=[vek]), acl=(PA_OLD,), ns=Q.NS)
    assert not any("Overena tužba" in d for d in docs)


def test_odbijena_lekcija_nestaje(svet):
    k, _ = svet
    assert k.patch("/api/learning/lessons/l1/potvrdi", headers=f8.zaglavlje("A"), json={"akcija": "odbaci"}).status_code == 200
    _, d = _ctx(k)
    assert d["confirmed_lessons"]["stavke"] == []


def test_deaktivirana_beleska_nestaje(svet):
    k, _ = svet
    _, d = _ctx(k)
    assert d["relevant_human_memory"]["stavke"]
    assert k.delete("/api/firma-memorija/m1", headers=f8.zaglavlje("A")).status_code == 200
    _, d = _ctx(k)
    assert d["relevant_human_memory"]["stavke"] == []


def test_ispravljen_ishod_menja_opis(svet):
    k, _ = svet
    _, d = _ctx(k)
    assert d["descriptive_outcomes"]["po_ishodu"] == {"nagodba": 1}
    k.post("/api/learning/outcome", headers=f8.zaglavlje("A"), json={"predmet_id": PA_OLD, "ishod": "poraz"})
    _, d = _ctx(k)
    assert d["descriptive_outcomes"]["po_ishodu"] == {"poraz": 1}


def test_predmet_u_brisanju_nestaje_vlasniku_i_delegatu(svet):
    k, b = svet
    _, d = _ctx(k, "B", "bbbbbbbb-1111-4000-8000-000000000001")
    assert [s["predmet_id"] for s in d["similar_cases"]["stavke"]] == [PA_OLD], "kontrola: delegat vidi"
    next(p for p in b.tabele["predmeti"] if p["id"] == PA_OLD)["brisanje_zapoceto"] = "2026-10-10T00:00:00+00:00"
    for ko, pid in (("A", PA_CUR), ("B", "bbbbbbbb-1111-4000-8000-000000000001")):
        _, d = _ctx(k, ko, pid)
        assert d["similar_cases"]["stavke"] == [] and d["verified_artifacts"]["stavke"] == [], ko
        assert d["descriptive_outcomes"]["state"] == "EMPTY"
    assert _ctx(k, "A", PA_OLD)[0] == 404
    z = k.get("/api/law-brain/znanje", headers=f8.zaglavlje("A")).json()
    assert z["verifikovani_radovi"]["stavke"] == [] and z["iskustvo"]["state"] == "EMPTY"


def test_tvrdo_brisanje_ne_ostavlja_kopiju(svet):
    k, b = svet
    for t in ("staging_memory", "outcome_log", "rocista", "predmet_dokazi"):
        b.tabele[t] = [r for r in b.tabele[t] if r.get("predmet_id") != PA_OLD]
    b.tabele["predmeti"] = [p for p in b.tabele["predmeti"] if p["id"] != PA_OLD]
    _, d = _ctx(k)
    assert "Petrović protiv" not in str(d) and d["verified_artifacts"]["stavke"] == []
    assert b.tabele["audit_immutable"], "nepromenjiv revizioni trag ostaje (ne briše se)"


def test_uklonjen_clan_gubi_memoriju_od_sledeceg_zahteva(svet):
    k, b = svet
    next(c for c in b.tabele["kancelarija_clanovi"] if c["user_id"] == "uid-B")["status"] = "REMOVED"
    z = k.get("/api/law-brain/znanje", headers=f8.zaglavlje("B")).json()
    assert z["memorija_kancelarije"]["stavke"] == [] and z["memorija_kancelarije"]["kancelarija"] is False


def test_naivni_datumi_ne_obaraju_svezinu():
    from shared.vector_origin import freshness_weight
    assert freshness_weight(origin="LAWYER_VERIFIED", created_at="2026-08-01") == 1.0
    assert freshness_weight(origin="CLIENT_DOC", created_at="2015-01-01") == 0.5
    assert freshness_weight(origin="LAWYER_VERIFIED", created_at="2026-08-01", valid_until="2020-01-01") == 0.1, \
        "istekao naivni valid_until se kažnjava (ranije tiho ignorisan)"
