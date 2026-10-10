# -*- coding: utf-8 -*-
"""NS008 Task 4 — advokatski overeni artefakti kroz POSTOJEĆI staging_memory tok.

Kroz STVARNE rute `POST /api/staging/{id}/approve|reject` (promocija u Pinecone zamenjena — ista zamena kao
tests/test_beta_gate_staging_approve_race.py): odobren + indeksiran → LAWYER_VERIFIED_ARTIFACT/APPROVED_INDEXED;
odobren ispod praga → LAWYER_VERIFIED_ARTIFACT/APPROVED_NOT_INDEXED (ne laže da je u bazi znanja);
na čekanju / odbijen → AI_WORK_PRODUCT, nikad među poverljivim. Otrovan AI nacrt, ma koliko sličan, ne ulazi.
"""
import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

PA = "aaaaaaaa-4444-4000-8000-00000000000a"
PB = "bbbbbbbb-4444-4000-8000-00000000000b"
S_VISOK, S_NIZAK, S_CEKA, S_OTROV, S_B = (f"5{i}aaaaaa-4444-4000-8000-00000000000{i}" for i in range(1, 6))


def _red(sid, uid, pid, skor, tekst="Tužba radi isplate zarade — obrazloženje", status="pending"):
    return {"id": sid, "user_id": uid, "kancelarija_id": None, "predmet_id": pid, "tip": "tuzba", "naziv": "Tužba",
            "tekst": tekst, "confidence_score": skor, "quality_detail": {}, "is_lawyer_approved": False,
            "approved_by": None, "approved_at": None, "status": status, "pinecone_indexed": False,
            "pinecone_namespace": None, "created_at": "2026-10-01T10:00:00+00:00"}


@pytest.fixture
def svet(monkeypatch):
    k, baza = f8.pripremi(monkeypatch, {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Tajni B", "status": "aktivan"}],
        "staging_memory": [
            _red(S_VISOK, "uid-A", PA, 0.92), _red(S_NIZAK, "uid-A", PA, 0.60), _red(S_CEKA, "uid-A", PA, 0.95),
            _red(S_OTROV, "uid-A", PA, 0.99, tekst="Tužba radi isplate zarade — IZMIŠLJEN član 999 Zakona o radu"),
            _red(S_B, "uid-B", PB, 0.95),
        ],
        "predmet_dokumenti": [], "v2_mutation_idempotency": [], "audit_immutable": [],
    })
    import routers.drafting as drafting
    promovisano = []

    async def _promote(supa, row):
        promovisano.append(row["id"])
        return True
    monkeypatch.setattr(drafting, "_promote_staged_draft_to_pinecone", _promote)
    yield k, baza, promovisano
    f8.ocisti()


def _po_id(items):
    return {it.source_id: it for it in items}


def test_tok_odobrenja_daje_tacna_stanja(svet):
    k, baza, promovisano = svet
    assert k.post(f"/api/staging/{S_VISOK}/approve", headers=f8.zaglavlje("A")).json()["indexed"] is True
    assert k.post(f"/api/staging/{S_NIZAK}/approve", headers=f8.zaglavlje("A")).json()["indexed"] is False
    assert k.post(f"/api/staging/{S_OTROV}/reject", headers=f8.zaglavlje("A")).json()["status"] == "rejected"
    assert promovisano == [S_VISOK]

    pa = next(p for p in baza.tabele["predmeti"] if p["id"] == PA)
    sve = _po_id(lb.ucitaj_artefakte(baza, [pa]))
    assert set(sve) == {S_VISOK, S_NIZAK, S_CEKA, S_OTROV}, "B-ov red nikad"
    v, n, c, o = sve[S_VISOK], sve[S_NIZAK], sve[S_CEKA], sve[S_OTROV]
    assert (v.trust_class, v.state, v.validity) == (lb.LAWYER_VERIFIED_ARTIFACT, lb.ART_INDEXED, lb.CURRENT)
    assert v.lineage == ("AI_GENERATED", "LAWYER_VERIFIED") and v.to_dict()["source_ref"]["id"] == S_VISOK
    assert (n.trust_class, n.state) == (lb.LAWYER_VERIFIED_ARTIFACT, lb.ART_APPROVED_NOT_INDEXED)
    assert n.to_dict()["attrs"]["pinecone_indexed"] is False
    assert (c.trust_class, c.state, c.human_verified) == (lb.AI_WORK_PRODUCT, lb.ART_PENDING, False)
    assert (o.trust_class, o.state, o.validity) == (lb.AI_WORK_PRODUCT, lb.ART_REJECTED, lb.DEPRECATED)

    poverljivo = {it.source_id for it in lb.trusted(sve.values())}
    assert poverljivo == {S_VISOK, S_NIZAK}
    assert S_OTROV not in poverljivo and S_CEKA not in poverljivo


def test_otrovan_nacrt_visokog_skora_bez_odobrenja_nije_poverljiv(svet):
    _, baza, _ = svet
    pa = next(p for p in baza.tabele["predmeti"] if p["id"] == PA)
    otrov = _po_id(lb.ucitaj_artefakte(baza, [pa]))[S_OTROV]
    assert otrov.to_dict()["attrs"]["confidence_score"] == 0.99
    assert otrov.trusted is False and otrov.trust_class == lb.AI_WORK_PRODUCT


def test_odbijen_posle_promocije_ostaje_vidljivo_stanje(svet):
    k, baza, _ = svet
    k.post(f"/api/staging/{S_VISOK}/approve", headers=f8.zaglavlje("A"))
    k.post(f"/api/staging/{S_VISOK}/reject", headers=f8.zaglavlje("A"))
    pa = next(p for p in baza.tabele["predmeti"] if p["id"] == PA)
    it = _po_id(lb.ucitaj_artefakte(baza, [pa]))[S_VISOK]
    assert it.state == lb.ART_REJECTED_STILL_INDEXED and it.trusted is False


@pytest.mark.parametrize("izmena", [
    {"status": "approved", "is_lawyer_approved": False, "approved_at": "2026-10-02T00:00:00+00:00"},
    {"status": "approved", "is_lawyer_approved": True, "approved_at": None},
    {"status": "pending", "is_lawyer_approved": True},
    {"status": "nesto"},
])
def test_nedosledan_red_nikad_poverljiv(izmena):
    pa = {"id": PA, "user_id": "uid-A"}
    red = {**_red(S_VISOK, "uid-A", PA, 0.99), **izmena}
    it = lb.artifact_item(red, pa)
    assert it.trusted is False and it.trust_class == lb.AI_WORK_PRODUCT


def test_red_tudjeg_vlasnika_ili_predmeta_se_odbacuje():
    pa = {"id": PA, "user_id": "uid-A"}
    odobren = {**_red(S_B, "uid-B", PA, 0.99), "status": "approved", "is_lawyer_approved": True,
               "approved_at": "2026-10-02T00:00:00+00:00", "pinecone_indexed": True}
    assert lb.artifact_item(odobren, pa) is None
    assert lb.artifact_item({**odobren, "user_id": "uid-A", "predmet_id": PB}, pa) is None


def test_ne_moze_odobriti_tudj_nacrt(svet):
    k, baza, promovisano = svet
    assert k.post(f"/api/staging/{S_B}/approve", headers=f8.zaglavlje("A")).status_code == 404
    assert promovisano == [] and next(r for r in baza.tabele["staging_memory"] if r["id"] == S_B)["status"] == "pending"


def test_izvod_ne_nosi_ceo_tekst():
    pa = {"id": PA, "user_id": "uid-A"}
    it = lb.artifact_item(_red(S_VISOK, "uid-A", PA, 0.9, tekst="x" * 50000), pa)
    assert len(it.excerpt) <= lb.EXCERPT_MAX


def test_greska_baze_se_propusta(svet):
    _, baza, _ = svet
    baza.greske["staging_memory"] = Exception("down")
    with pytest.raises(Exception):
        lb.ucitaj_artefakte(baza, [{"id": PA, "user_id": "uid-A"}])
