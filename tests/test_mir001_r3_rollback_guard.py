# -*- coding: utf-8 -*-
"""MIR001 FINAL RELEASE R3 — zaštita CILJA POVRATKA (f33dcce8 + guard).

Posle eventualnog povratka sa MIR001 grane u `staging_memory` mogu ostati redovi novog toka (`nacrt_iz_spisa`,
`dokument_za_sud`). Ova verzija ih ne odobrava, ne menja, ne upisuje u bazu znanja (ni „Ponovi upis"), ne prikazuje
kao overen rad kancelarije i ne izvozi tekst sa internim napomenama. Ostali nacrti rade kao pre (regresija)."""
import uuid

import pytest

from tests.ns005_harness import zaglavlje
from tests.test_ns005_t8_nacrti import ok  # noqa: F401

GRANICA = "═══ VINDEX — INTERNE NAPOMENE ZA ADVOKATA (upisao sistem; NISU deo podneska i ne izvoze se u DOCX) ═══"


def _dodaj(b, sid, tip, status="pending", **kw):
    red = {"id": sid, "user_id": "uid-A", "predmet_id": "p-A", "tip": tip, "naziv": tip, "tekst": "Tekst. " + GRANICA + "\nINTERNO",
           "status": status, "is_lawyer_approved": status == "approved", "pinecone_indexed": False, "confidence_score": 0.95,
           "quality_detail": {"usvajanje": {"rev": 1}}, "created_at": "2026-10-24T10:00:00Z", **kw}
    b.tabele.setdefault("staging_memory", []).append(red)
    return red


@pytest.mark.parametrize("tip", ["nacrt_iz_spisa", "dokument_za_sud"])
def test_novi_tok_se_ne_odobrava_ne_menja_ne_upisuje_u_znanje(ok, monkeypatch, tip):  # noqa: F811
    k, b, *_ = ok
    import routers.drafting as D
    promocije = []

    async def _promocija(supa, red):
        promocije.append(red.get("id"))
        return True
    monkeypatch.setattr(D, "_promote_staged_draft_to_pinecone", _promocija)
    p = _dodaj(b, str(uuid.uuid4()), tip)
    o = _dodaj(b, str(uuid.uuid4()), tip, status="approved")
    h = zaglavlje("A")
    assert k.post(f"/api/staging/{p['id']}/approve", headers=h).status_code == 409
    assert k.patch(f"/api/staging/{p['id']}/tekst", json={"tekst": "Izmena"}, headers=h).status_code == 409
    assert k.post(f"/api/staging/{o['id']}/ponovi-upis", headers=h).status_code == 409
    assert promocije == [] and p["status"] == "pending" and p["quality_detail"] == {"usvajanje": {"rev": 1}}
    lista = {x["id"]: x for x in k.get("/api/staging/predmet/p-A", headers=h).json()["stavke"]}
    assert lista[o["id"]]["ponovni_upis_moguc"] is False
    # odbijanje i čitanje rade
    assert k.get(f"/api/staging/{p['id']}", headers=h).status_code == 200
    assert k.post(f"/api/staging/{p['id']}/reject", headers=h).status_code == 200 and p["status"] == "rejected"
    # odobren dokument za sud se ne odbija naknadno (zapis odluke); odobren AI predlog (nastao van ugovora) sme da se odbije
    r = k.post(f"/api/staging/{o['id']}/reject", headers=h)
    if tip == "dokument_za_sud":
        assert r.status_code == 409 and o["status"] == "approved"
    else:
        assert r.status_code == 200 and o["status"] == "rejected"


def test_izvoz_ne_izvozi_interne_napomene_ni_novi_tok(ok):  # noqa: F811
    k, b, *_ = ok
    h = zaglavlje("A")
    assert k.post("/api/nacrti/export/docx", json={"tekst": "Tekst. " + GRANICA, "naslov": "X", "tip": "tuzba"}, headers=h).status_code == 409
    assert k.post("/api/nacrti/export/docx", json={"tekst": "Čist tekst podneska.", "naslov": "X", "tip": "dokument_za_sud"},
                  headers=h).status_code == 409
    assert k.post("/export/docx", json={"naslov": "X", "tekst": "Tekst dovoljno dug za izvoz. " + GRANICA, "tip": "podnesak"},
                  headers=h).status_code == 409
    r = k.post("/api/nacrti/export/docx", json={"tekst": "Čist tekst podneska.", "naslov": "X", "tip": "tuzba"}, headers=h)
    assert r.status_code == 200                                                   # regresija: obični nacrti se izvoze


def test_law_brain_novi_tok_nije_overeno_znanje():
    from services import law_brain as LB
    red = {"id": "s1", "user_id": "u", "predmet_id": "p", "tip": "dokument_za_sud", "status": "approved",
           "is_lawyer_approved": True, "approved_at": "2026-10-24T10:00:00Z", "tekst": "Usvojen tekst.\n\n" + GRANICA + "\nINTERNO"}
    it = LB.artifact_item(red, {"id": "p", "user_id": "u"})
    assert it.trust_class == LB.AI_WORK_PRODUCT and not it.trusted and "INTERNO" not in it.excerpt
    obican = dict(red, tip="tuzba", tekst="Tuzba.")
    assert LB.artifact_item(obican, {"id": "p", "user_id": "u"}).trust_class == LB.LAWYER_VERIFIED_ARTIFACT    # regresija


def test_obican_nacrt_i_dalje_odobrava_i_upisuje(ok, monkeypatch):  # noqa: F811
    k, b, *_ = ok
    import routers.drafting as D
    promocije = []

    async def _promocija(supa, red):
        promocije.append(red.get("id"))
        return True
    monkeypatch.setattr(D, "_promote_staged_draft_to_pinecone", _promocija)
    r = _dodaj(b, "st-obican", "tuzba", tekst="Tužba za naknadu štete.")
    assert k.post(f"/api/staging/{r['id']}/approve", headers=zaglavlje("A")).status_code == 200
    assert promocije == ["st-obican"]
