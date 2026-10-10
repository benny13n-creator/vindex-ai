# -*- coding: utf-8 -*-
"""NS008 Task 15 — prihvaćen autonomni rad NE ulazi automatski u Law Brain; izričit predlog ide KROZ staging.

READY → nije u poverljivom znanju; ACCEPTED → i dalje nije; izričit predlog → staging `pending` (AI_WORK_PRODUCT,
nepoverljivo); advokatsko odobrenje (postojeća ruta) → LAWYER_VERIFIED_ARTIFACT. Predlog nikad ne piše u Pinecone.
"""
import uuid

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

PA = "aaaaaaaa-1515-4000-8000-00000000000a"
PB = "bbbbbbbb-1515-4000-8000-00000000000b"
W_READY, W_ACC, W_B, W_REJ = (str(uuid.UUID(int=1500 + i)) for i in range(4))


def _rad(wid, uid, pid, status):
    return {"id": wid, "user_id": uid, "predmet_id": pid, "work_type": "HEARING_PREP", "status": status,
            "title": "Priprema za ročište", "summary": "Šta proveriti pre ročišta.", "dedupe_key": f"k-{wid}",
            "content_json": {"pitanja": [{"tekst": "Proveriti datum uručenja.", "refs": ["x"]}],
                             "beleske": [{"tekst": "Pripremiti dostavnicu.", "refs": ["y"]}]}}


@pytest.fixture
def svet(monkeypatch):
    k, b = f8.pripremi(monkeypatch, {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "B", "status": "aktivan"}],
        "autonomy_work_items": [_rad(W_READY, "uid-A", PA, "READY_FOR_REVIEW"), _rad(W_ACC, "uid-A", PA, "ACCEPTED"),
                                _rad(W_B, "uid-B", PB, "ACCEPTED"), _rad(W_REJ, "uid-A", PA, "REJECTED")],
        "staging_memory": [], "predmet_dokumenti": [], "v2_mutation_idempotency": [], "audit_immutable": [],
        "kancelarije": [], "kancelarija_clanovi": [],
    })
    import services.quality_gate as qg
    import routers.drafting as drafting

    async def _kvalitet(tekst, tip=""):
        return {"confidence_score": 0.9, "detail": {"provera": "lažna"}}
    monkeypatch.setattr(qg, "evaluate_draft_quality", _kvalitet)
    promovisano = []

    async def _promote(supa, row):
        promovisano.append(row["id"])
        return True
    monkeypatch.setattr(drafting, "_promote_staged_draft_to_pinecone", _promote)
    yield k, b, promovisano
    f8.ocisti()


def _pa(b):
    return [p for p in b.tabele["predmeti"] if p["id"] == PA]


def test_ready_i_accepted_nisu_u_poverljivom_znanju(svet):
    _, b, _ = svet
    assert lb.trusted(lb.ucitaj_artefakte(b, _pa(b))) == []
    assert b.tabele["staging_memory"] == [], "prihvatanje rada ne pravi nikakav predlog znanja"


def test_ready_i_odbijen_ne_mogu_da_se_predloze(svet):
    k, b, _ = svet
    for wid in (W_READY, W_REJ):
        assert k.post(f"/api/law-brain/rad/{wid}/predlozi-znanje", headers=f8.zaglavlje("A")).status_code == 409
    assert b.tabele["staging_memory"] == []


def test_izricit_predlog_ide_u_staging_pa_tek_odobrenje_verifikuje(svet):
    k, b, promovisano = svet
    r = k.post(f"/api/law-brain/rad/{W_ACC}/predlozi-znanje", headers=f8.zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["novo"] is True and d["status"] == "pending" and promovisano == [], "predlog nikad ne piše u Pinecone"
    red = b.tabele["staging_memory"][0]
    assert red["is_lawyer_approved"] in (False, None) and red["tip"] == "pripremljen_rad"
    assert "Proveriti datum uručenja." in red["tekst"] and red["quality_detail"]["izvor_rad_id"] == W_ACC
    it = lb.ucitaj_artefakte(b, _pa(b))[0]
    assert (it.trust_class, it.state, it.trusted) == (lb.AI_WORK_PRODUCT, lb.ART_PENDING, False)

    a = k.post(f"/api/staging/{d['staging_id']}/approve", headers=f8.zaglavlje("A"))
    assert a.status_code == 200 and a.json()["indexed"] is True and promovisano == [d["staging_id"]]
    it = lb.ucitaj_artefakte(b, _pa(b))[0]
    assert (it.trust_class, it.state, it.trusted) == (lb.LAWYER_VERIFIED_ARTIFACT, lb.ART_INDEXED, True)
    assert it.lineage == ("AI_GENERATED", "LAWYER_VERIFIED")


def test_ponovljen_predlog_isti_staging(svet):
    k, b, _ = svet
    r1 = k.post(f"/api/law-brain/rad/{W_ACC}/predlozi-znanje", headers=f8.zaglavlje("A")).json()
    r2 = k.post(f"/api/law-brain/rad/{W_ACC}/predlozi-znanje", headers=f8.zaglavlje("A")).json()
    assert r1["staging_id"] == r2["staging_id"] and r2["novo"] is False
    assert len(b.tabele["staging_memory"]) == 1


def test_tudj_rad_404(svet):
    k, b, _ = svet
    assert k.post(f"/api/law-brain/rad/{W_B}/predlozi-znanje", headers=f8.zaglavlje("A")).status_code == 404
    assert k.post("/api/law-brain/rad/nije-uuid/predlozi-znanje", headers=f8.zaglavlje("A")).status_code == 404
    assert b.tabele["staging_memory"] == []


def test_tekst_rada_deterministican():
    from services.law_brain_promocija import tekst_rada
    t = tekst_rada(_rad("w", "u", "p", "ACCEPTED"))
    assert t == "Priprema za ročište\n\nŠta proveriti pre ročišta.\n\nPripremiti dostavnicu.\n\nProveriti datum uručenja."


def test_prihvatanje_kroz_rutu_ne_pravi_predlog_znanja(svet):
    k, b, promovisano = svet
    r = k.post(f"/api/autonomy/work-items/{W_READY}/accept", headers=f8.zaglavlje("A"))
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
    assert b.tabele["staging_memory"] == [] and promovisano == []
    assert lb.trusted(lb.ucitaj_artefakte(b, _pa(b))) == []
