"""NS007 Task 17 — revizioni trag autonomnog rada kroz POSTOJEĆEG vlasnika (`audit_immutable.log_action`).

  • ceo životni ciklus: QUEUED → STARTED → READY (ili FAILED / SUPERSEDED) → ACCEPTED / REJECTED, svaki zapis vezan
    za korisnika, predmet i radnu stavku; korelacija = id radne stavke, ista kao korelacija AI poziva izvršioca;
  • metapodaci su samo identifikatori i bezbedne klasifikacije — naslov, razlog, sažetak i sadržaj NIKAD;
  • nove akcije su u `AUDITABLE_ACTIONS` (inače bi `log_action` tiho preskočio — „declared != enforced");
  • revizija nedostupna → rad se nastavlja, ali se neuspeh BROJI (ne tvrdi se da je zabeleženo).
"""
import asyncio
import json

import pytest

from services import autonomy as au
from services.agent_tasks import hearing_prep as hp
from shared.audit_immutable import AUDITABLE_ACTIONS
from tests.test_ns007_t8_hearing_executor import _model, svet  # noqa: F401 — isti svet (realan predmet, ročište sutra)
import tests.ns007_fake as f7

AKCIJE = {"AUTONOMY_WORK_QUEUED", "AUTONOMY_WORK_STARTED", "AUTONOMY_WORK_READY", "AUTONOMY_WORK_FAILED",
          "AUTONOMY_WORK_SUPERSEDED", "AUTONOMY_WORK_ACCEPTED", "AUTONOMY_WORK_REJECTED"}


@pytest.fixture
def trag(monkeypatch):
    zapisi = []

    async def log_action(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        assert action in AUDITABLE_ACTIONS, f"{action} nije u AUDITABLE_ACTIONS — log_action bi ga tiho preskočio"
        zapisi.append({"action": action, "user_id": user_id, "resource_type": resource_type, "resource_id": resource_id,
                       "metadata": metadata, "correlation_id": correlation_id})
        return "audit-" + str(len(zapisi))
    import shared.audit_immutable as ai
    monkeypatch.setattr(ai, "log_action", log_action)
    return zapisi


def test_akcije_su_dozvoljene():
    assert AKCIJE <= AUDITABLE_ACTIONS


def test_ceo_zivotni_ciklus_sa_korelacijom_i_bez_sadrzaja(svet, trag):
    baza, ba, mp = svet
    model, st = _model()
    korelacije = []
    import shared.ai_provenance as prov
    pravi = prov.case_context

    def spijun(**kw):
        korelacije.append((kw.get("correlation_id"), kw.get("operation_name"), kw.get("predmet_id")))
        return pravi(**kw)
    mp.setattr(prov, "case_context", spijun)

    async def kroz_pravi_case_context(prompt, predmet_id, work_id=None):
        from shared.ai_provenance import case_context
        with case_context(predmet_id=predmet_id, module_name="autonomy.hearing_prep", operation_name="HEARING_PREP", correlation_id=work_id):
            return await model(prompt, predmet_id)
    mp.setattr(hp, "_pozovi_model", kroz_pravi_case_context)
    s = asyncio.run(ba.run_autonomy_cycle("run-trag"))
    rad = baza.tabele["autonomy_work_items"][0]
    assert [z["action"] for z in trag] == ["AUTONOMY_WORK_QUEUED", "AUTONOMY_WORK_STARTED", "AUTONOMY_WORK_READY"]
    for z in trag:
        assert z["resource_type"] == "autonomy_work_item" and z["resource_id"] == rad["id"] and z["correlation_id"] == rad["id"]
        assert z["user_id"] == "uid-A" and z["metadata"]["predmet_id"] == rad["predmet_id"] and z["metadata"]["run_id"] == "run-trag"
        tekst = json.dumps(z["metadata"], ensure_ascii=False)
        for zabranjeno in (rad["title"], rad["summary"], rad["reason"], "Rešenje je uručeno", "Osnovni sud"):
            assert zabranjeno not in tekst, (z["action"], zabranjeno)
    assert trag[2]["metadata"]["quality_state"] == "AI_PREPARED_FOR_REVIEW" and trag[2]["metadata"]["model"]
    assert trag[1]["metadata"]["attempt_count"] == 1 and trag[1]["metadata"]["budget_units"] == 1
    assert korelacije == [(rad["id"], "HEARING_PREP", rad["predmet_id"])], "AI poziv nosi isti id kao revizija"
    assert s["revizija_nije_upisana"] == 0
    import api
    from fastapi.testclient import TestClient
    r = TestClient(api.app).post(f"/api/autonomy/work-items/{rad['id']}/accept", headers=f7.zaglavlje("A"))
    assert r.status_code == 200 and trag[-1]["action"] == "AUTONOMY_WORK_ACCEPTED" and trag[-1]["correlation_id"] == rad["id"]
    assert trag[-1]["user_id"] == "uid-A"


def test_neuspeh_i_zastarevanje_su_u_tragu(svet, trag):
    baza, ba, mp = svet
    model, _ = _model()
    mp.setattr(hp, "_pozovi_model", model)
    plan = asyncio.run(hp.planiraj(baza))
    asyncio.run(au.upisi_kandidata(baza, plan["kandidati"][0]))
    baza.tabele["rocista"][0]["status"] = "otkazano"
    asyncio.run(ba.run_autonomy_cycle("r1"))
    akcije = [z["action"] for z in trag]
    assert "AUTONOMY_WORK_SUPERSEDED" in akcije and "AUTONOMY_WORK_STARTED" not in akcije


def test_konacan_i_prolazan_neuspeh(svet, trag):
    baza, ba, mp = svet
    model, _ = _model()
    mp.setattr(hp, "_pozovi_model", model)
    baza.greske["predmet_dokazi"] = RuntimeError("izvor nedostupan")
    asyncio.run(ba.run_autonomy_cycle("r1"))
    f = [z for z in trag if z["action"] == "AUTONOMY_WORK_FAILED"]
    assert len(f) == 1 and f[0]["metadata"]["konacno"] is False and f[0]["metadata"]["safe_error_code"].startswith("TRANSIENT_")


def test_revizija_nedostupna_rad_se_nastavlja_i_broji(svet, monkeypatch):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)

    async def pada(*a, **k):
        return None                                # log_action vraća None kad upis ne uspe
    import shared.audit_immutable as ai
    monkeypatch.setattr(ai, "log_action", pada)
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert s["spremno"] == 1 and s["revizija_nije_upisana"] == 3, s
    assert baza.tabele["autonomy_work_items"][0]["status"] == "READY_FOR_REVIEW"
