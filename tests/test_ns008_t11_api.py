# -*- coding: utf-8 -*-
"""NS008 Task 11 — GET /api/law-brain/predmeti/{id}: kanonski kontekst, bez modela, bez kredita, bez upisa.

Pad izvora → ta sekcija DEGRADED (nikad EMPTY), ostale rade. Tuđ i nepostojeć predmet → bajt-identičan 404.
"""
import json

import pytest

import tests.ns008_fake as f8

K1 = "e1e1e1e1-1111-4000-8000-000000000001"
PA_CUR = "aaaaaaaa-1111-4000-8000-000000000001"
PA_OLD = "aaaaaaaa-1111-4000-8000-000000000002"
PB_CUR = "bbbbbbbb-1111-4000-8000-000000000001"
NEPOSTOJI = "dddddddd-1111-4000-8000-000000000009"
SUD = "Osnovni sud u Beogradu"


def _tabele():
    p = lambda pid, uid, naziv, status: {"id": pid, "user_id": uid, "naziv": naziv, "tip": "radni", "oblast": "radno",
                                         "status": status, "case_dna": {"verzija": 2}, "updated_at": "2026-09-01"}
    return {
        "predmeti": [p(PA_CUR, "uid-A", "A tekući", "aktivan"), p(PA_OLD, "uid-A", "Petrović protiv Gradnja Invest DOO", "zatvoren"),
                     p(PB_CUR, "uid-B", "B tekući", "aktivan")],
        "rocista": [{"predmet_id": x, "user_id": u, "sud": SUD, "status": "odrzano"}
                    for x, u in ((PA_CUR, "uid-A"), (PA_OLD, "uid-A"), (PB_CUR, "uid-B"))],
        "predmet_dokazi": [{"predmet_id": x, "user_id": u, "kategorija": "svedok"}
                           for x, u in ((PA_CUR, "uid-A"), (PA_OLD, "uid-A"), (PB_CUR, "uid-B"))],
        "outcome_log": [{"id": "o1", "predmet_id": PA_OLD, "user_id": "uid-A", "ishod": "nagodba",
                         "presudni_faktori": ["svedoci"]}],
        "predmet_issues": [], "predmet_contradictions": [], "predmet_delegiranja": [],
        "staging_memory": [{"id": "s-ok", "user_id": "uid-A", "predmet_id": PA_OLD, "tip": "tuzba", "naziv": "Tužba",
                            "tekst": "Tekst tužbe", "confidence_score": 0.9, "is_lawyer_approved": True,
                            "approved_at": "2026-08-01T00:00:00+00:00", "status": "approved", "pinecone_indexed": True}],
        "lessons_learned": [{"id": "l1", "user_id": "uid-A", "tip_spora": "radni", "lecija": "Pribaviti pisane dokaze rano.",
                             "kategorija": "dokaz", "status_lekcije": "usvojena_praksa", "potvrdio": "uid-A",
                             "potvrdjeno_at": "2026-09-01T00:00:00+00:00", "zastarela": False},
                            {"id": "l2", "user_id": "uid-A", "tip_spora": "radni", "lecija": "AI predlog",
                             "kategorija": "dokaz", "status_lekcije": "predlog_ai", "zastarela": False}],
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": u, "status": "ACTIVE"} for u in ("uid-A", "uid-B")],
        "memory_entries": [{"id": "m1", "kancelarija_id": K1, "user_id": "uid-B", "entity_type": "sudija",
                            "entity_id": "Petrović", "entity_name": "Sudija Petrović", "tip": "obrazac",
                            "sadrzaj": "Traži tabelu rokova.", "aktivan": True, "izvor": "manual", "potvrde_count": 1}],
        "memory_graph_edges": [], "klijenti": [],
    }


@pytest.fixture
def svet(monkeypatch):
    k, b = f8.pripremi(monkeypatch, _tabele())
    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("model pozvan")))
    from shared.usage import UsageService
    krediti = []

    async def _consume(*a, **kw):
        krediti.append(a)
    monkeypatch.setattr(UsageService, "consume", _consume)
    yield k, b, krediti
    f8.ocisti()


def test_pun_kontekst_bez_modela_kredita_i_upisa(svet):
    k, b, krediti = svet
    b.dnevnik.clear()
    r = k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert {d[s]["state"] for s in ("similar_cases", "verified_artifacts", "confirmed_lessons",
                                    "relevant_human_memory", "descriptive_outcomes")} == {"OK"}
    assert d["data_quality"]["state"] == "OK" and d["data_quality"]["nedostupni_izvori"] == []
    assert [s["predmet_id"] for s in d["similar_cases"]["stavke"]] == [PA_OLD]
    assert d["similar_cases"]["stavke"][0]["zasto"].startswith("Sličan jer:")
    assert [a["source_ref"]["id"] for a in d["verified_artifacts"]["stavke"]] == ["s-ok"]
    assert [x["source_ref"]["id"] for x in d["confirmed_lessons"]["stavke"]] == ["l1"]
    assert d["confirmed_lessons"]["kandidata"] == 1
    assert d["descriptive_outcomes"]["po_ishodu"] == {"nagodba": 1} and d["descriptive_outcomes"]["uzorak"] == 1
    assert d["relevant_human_memory"]["stavke"][0]["trust_class"] == "HUMAN_MEMORY_NOTE"
    assert "_profili" not in json.dumps(d) and "%" not in json.dumps(d, ensure_ascii=False)
    assert krediti == []
    assert {x["radnja"] for x in b.dnevnik if x["tabela"] not in ("audit_log", "audit_immutable")} == {"select"}


def test_tudj_i_nepostojeci_predmet_isti_404(svet):
    k, _, _ = svet
    tudj = k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("B"))
    nema = k.get(f"/api/law-brain/predmeti/{NEPOSTOJI}", headers=f8.zaglavlje("B"))
    los = k.get("/api/law-brain/predmeti/nije-uuid", headers=f8.zaglavlje("B"))
    assert tudj.status_code == nema.status_code == los.status_code == 404
    assert tudj.content == nema.content == los.content


def test_kolega_iz_kancelarije_ne_vidi_tudje_predmete(svet):
    k, _, _ = svet
    d = k.get(f"/api/law-brain/predmeti/{PB_CUR}", headers=f8.zaglavlje("B")).json()
    t = json.dumps(d, ensure_ascii=False)
    for zabranjeno in ("Petrović protiv", PA_OLD, "s-ok", "Tekst tužbe", "Pribaviti", "nagodba"):
        assert zabranjeno not in t
    assert d["similar_cases"]["state"] == "EMPTY" and d["similar_cases"]["pretrazeno_zavrsenih"] == 0
    assert d["relevant_human_memory"]["state"] == "OK", "opšta beleška o sudiji je deljena u kancelariji"


def test_pad_izvora_je_degraded_ne_prazno(svet):
    k, b, _ = svet
    b.greske["lessons_learned"] = Exception("down")
    d = k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).json()
    assert d["confirmed_lessons"]["state"] == "DEGRADED"
    assert d["similar_cases"]["state"] == "OK"
    assert d["data_quality"]["state"] == "DEGRADED" and d["data_quality"]["nedostupni_izvori"] == ["confirmed_lessons"]


def test_pad_slicnosti_degradira_i_ishode(svet):
    k, b, _ = svet
    b.greske["outcome_log"] = Exception("down")
    d = k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).json()
    assert d["similar_cases"]["state"] == "DEGRADED" and d["descriptive_outcomes"]["state"] == "DEGRADED"


def test_pad_autorizacije_je_503(svet):
    k, b, _ = svet
    b.greske["predmeti"] = Exception("down")
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).status_code == 503


def test_bez_tokena_401(svet):
    k, _, _ = svet
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}").status_code == 401


def test_predmet_u_brisanju_404(svet):
    k, b, _ = svet
    next(p for p in b.tabele["predmeti"] if p["id"] == PA_CUR)["brisanje_zapoceto"] = "2026-10-01"
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).status_code == 404


def test_delegiran_predmet_u_brisanju_404(svet):
    # vlasnički put `rag_acl` filtrira tombstone; delegirani ne — Law Brain proverava sam
    k, b, _ = svet
    b.tabele["predmet_delegiranja"].append({"predmet_id": PA_CUR, "na_user_id": "uid-B", "status": "aktivno"})
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("B")).status_code == 200
    next(p for p in b.tabele["predmeti"] if p["id"] == PA_CUR)["brisanje_zapoceto"] = "2026-10-01"
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("B")).status_code == 404
