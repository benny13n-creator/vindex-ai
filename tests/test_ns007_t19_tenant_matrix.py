"""NS007 Task 19 — matrica zakupaca A/B (konsolidacija + preostale ćelije).

Već dokazano (ne ponavlja se): B ne vidi / ne može da zaključi postojanje / ne čita naslov ni izvore / ne prihvata ni
odbacuje rad A (T12, bajt-identičan 404, mutacije V1/V2/V4); tabla bez tuđeg rada (T14, W1); ročište A uz predmet B
(planer H2, izvršilac X3); predmet više nije vlasnikov (X14); preporuka A uz predmet B u planeru (P6); zastareo UI
odgovor A kod B (T15, Q1/Q10).

Ovde:
  • preporuka korisnika B koja (oštećeno) pokazuje na predmet A → izvršilac NE radi (vlasnik preporuke ≠ vlasnik rada);
  • tabla i lista korisnika B posle punog ciklusa za A: prazne;
  • okidač ciklusa ne prima zakupca: telo sa user_id/predmet_id se ignoriše, rad nastaje samo za stvarnog vlasnika.
"""
import asyncio

import pytest

from services import autonomy as au
from services.agent_tasks import precedents_radar as pr
from tests import ns006_realni_predmet as rp
from tests.test_ns007_t9_t10_precedent_impact import REC, _model, _plan, _rec, svet  # noqa: F401
import tests.ns007_fake as f7


def test_preporuka_drugog_korisnika_ne_pokrece_rad_u_izvrsiocu(svet):
    baza, ind, ba, mp = svet
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    k = _plan(baza)["kandidati"][0]
    asyncio.run(au.upisi_kandidata(baza, k))
    baza.tabele["agent_recommendations"][0]["user_id"] = "uid-B"     # preporuka sada pripada B, rad je A

    async def prazno(supa):
        return {"kandidati": [], "ponisteni": []}
    mp.setattr(pr, "planiraj", prazno)
    asyncio.run(ba.run_autonomy_cycle("r1"))
    r = baza.tabele["autonomy_work_items"][0]
    assert st["pozivi"] == [] and r["status"] == "FAILED" and r["safe_error_code"] == "RECOMMENDATION_NOT_ACTIVE"


def test_b_posle_punog_ciklusa_za_a_ne_vidi_nista(svet):
    baza, ind, ba, mp = svet
    model, _ = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(ba.run_autonomy_cycle("r1"))
    assert baza.tabele["autonomy_work_items"][0]["status"] == "READY_FOR_REVIEW"
    import api
    from fastapi.testclient import TestClient
    k = TestClient(api.app)
    w = k.get("/api/workspace", headers=f7.zaglavlje("B")).json()
    lista = k.get("/api/autonomy/work-items", headers=f7.zaglavlje("B")).json()
    po_predmetu = k.get(f"/api/autonomy/work-items?matter_id={rp.PA}", headers=f7.zaglavlje("B")).json()
    assert w["vindex_je_pripremio"] == [] and lista["stavke"] == [] and po_predmetu["stavke"] == []
    assert "Petrović" not in str(w) + str(lista) + str(po_predmetu) and "Rev 1234" not in str(w) + str(lista)


def test_okidac_ne_prima_zakupca_iz_tela(svet, monkeypatch):
    baza, ind, ba, mp = svet
    model, _ = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    mp.setenv("AUTONOMY_CRON_SECRET", "t" * 40)
    import api
    from fastapi.testclient import TestClient
    r = TestClient(api.app).post("/api/cron/autonomy", headers={"X-Autonomy-Secret": "t" * 40},
                                 json={"user_id": "uid-B", "predmet_id": rp.PB, "recommendation_id": REC})
    assert r.json()["status"] == "COMPLETED"
    assert {(x["user_id"], x["predmet_id"]) for x in baza.tabele["autonomy_work_items"]} == {("uid-A", rp.PA)}
