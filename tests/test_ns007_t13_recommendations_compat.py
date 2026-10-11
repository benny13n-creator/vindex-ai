"""NS007 Task 13 — `agent_recommendations` (legacy preporuke) i `autonomy_work_items` (pripremljen rad) žive zajedno.

  • postojeći `/api/agent-notifications` radi nepromenjeno i ne dira radne proizvode (i obrnuto);
  • rad samo REFERENCIRA preporuku (`recommendation_id`), ne kopira njen ceo sadržaj;
  • advokat odbaci preporuku → pripremljen rad iz nje postaje SUPERSEDED (ne briše se); prihvaćena → rad ostaje;
    obrisana preporuka (FK SET NULL) ne povlači gotov proizvod;
  • legacy `precedents_radar.run` i dalje piše SAMO preporuke (ne pravi radne proizvode).
"""
import asyncio
import json
import types

import pytest

from services.agent_tasks import precedents_radar as pr
from tests import ns006_realni_predmet as rp
from tests import ns007_korpus as kor
from tests.test_ns007_t9_t10_precedent_impact import REC, _model, _rec, svet  # noqa: F401 — isti svet kao T9–10
import tests.ns007_fake as f7


def _gotov(baza, ba, mp):
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(ba.run_autonomy_cycle("r1"))
    return baza.tabele["autonomy_work_items"][0], st


def test_postojeci_endpoint_preporuka_nepromenjen_i_odvojen(svet):
    baza, ind, ba, mp = svet
    rad, _ = _gotov(baza, ba, mp)
    import api
    from fastapi.testclient import TestClient
    k = TestClient(api.app)
    lista = k.get("/api/agent-notifications", headers=f7.zaglavlje("A")).json()
    assert [p["id"] for p in lista["preporuke"]] == [REC]
    assert k.post(f"/api/agent-notifications/{REC}/accept", headers=f7.zaglavlje("A")).json()["preporuka"]["status"] == "accepted"
    assert rad["status"] == "READY_FOR_REVIEW", "prihvatanje preporuke ne menja pripremljen rad"
    assert k.post(f"/api/autonomy/work-items/{rad['id']}/accept", headers=f7.zaglavlje("A")).status_code == 200
    assert baza.tabele["agent_recommendations"][0]["status"] == "accepted", "prihvatanje rada ne menja preporuku"


def test_rad_referencira_preporuku_bez_kopiranja_sadrzaja(svet):
    baza, ind, ba, mp = svet
    rad, _ = _gotov(baza, ba, mp)
    assert rad["recommendation_id"] == REC
    zasto = rad["content_json"]["zasto"]
    assert set(zasto) == {"odnos_radar", "obrazlozenje_radar", "poreklo", "napomena"}
    assert "score" not in json.dumps(rad["content_json"]) and "dedup_key" not in json.dumps(rad["content_json"])


def test_odbacena_preporuka_povlaci_pripremljen_rad(svet):
    baza, ind, ba, mp = svet
    rad, st = _gotov(baza, ba, mp)
    import api
    from fastapi.testclient import TestClient
    TestClient(api.app).post(f"/api/agent-notifications/{REC}/reject", headers=f7.zaglavlje("A"))
    s = asyncio.run(ba.run_autonomy_cycle("r2"))
    assert rad["status"] == "SUPERSEDED" and s["zastarelo"] == 1 and len(st["pozivi"]) == 1
    assert len(baza.tabele["autonomy_work_items"]) == 1, "zastarelo se ne briše"


def test_prihvacena_ostaje_obrisana_ne_povlaci_gotov_proizvod(svet):
    baza, ind, ba, mp = svet
    rad, _ = _gotov(baza, ba, mp)
    baza.tabele["agent_recommendations"][0]["status"] = "accepted"
    asyncio.run(ba.run_autonomy_cycle("r2"))
    assert rad["status"] == "READY_FOR_REVIEW"
    baza.tabele["agent_recommendations"].clear()
    rad["recommendation_id"] = None                       # ON DELETE SET NULL (136)
    asyncio.run(ba.run_autonomy_cycle("r3"))
    assert rad["status"] == "READY_FOR_REVIEW"


def test_legacy_radar_pise_samo_preporuke(svet):
    baza, ind, ba, mp = svet
    baza.tabele["agent_recommendations"].clear()
    import app.services.retrieve as rt
    mp.setattr(rt, "retrieve_sudska_praksa", lambda upit, k: ["m"])
    mp.setattr(rt, "process_praksa_chunks", lambda raw, k: [{"decision_number": kor.ODLUKA, "court": "Vrhovni sud",
                                                             "date": "2023-05-10", "matter": "radno", "text": kor.TEKST_IZREKA, "score": 0.8}])
    mp.setattr(pr, "_pozovi_klasifikaciju", lambda poz, tekst: json.dumps({"odnos": "podupire", "obrazlozenje": "x"}))
    ishod = asyncio.run(pr.run("uid-A", baza))
    assert ishod["preporuke_kreirane"] == 1 and len(baza.tabele["agent_recommendations"]) == 1
    assert baza.tabele.get("autonomy_work_items", []) == []
