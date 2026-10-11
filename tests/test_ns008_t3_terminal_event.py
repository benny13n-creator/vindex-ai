# -*- coding: utf-8 -*-
"""NS008 Task 3 — prelaz predmeta u završni status kroz SVAKI put emituje trajni MATTER_BECAME_TERMINAL.

Lanac: AKTIVAN → PATCH status=zatvoren → `events` red (determinističan id) → STVARNI dispečer → Case Evolution
`refresh_case_actions` → otvorena akcija za ročište se zatvara → planer autonomije više ne pravi posao, a
postojeći čekajući posao poništava → Law Brain vidi predmet kao završen (ishod nepoznat dok ga advokat ne unese).

PATCH istog statusa, PATCH drugih polja, tuđ predmet → nijedan događaj. Ponovljena emisija istog prelaza → jedan
red. Ponovno otvaranje pa zatvaranje → nov događaj.
"""
import asyncio
from datetime import date, timedelta

import pytest

import tests.ns008_fake as f8
from tests.ns006_fake import dispecuj
from services import law_brain as lb

PA = "aaaaaaaa-3333-4000-8000-00000000000a"
PB = "bbbbbbbb-3333-4000-8000-00000000000b"
ROC = "cccccccc-3333-4000-8000-00000000000c"
DANAS = date.today()


@pytest.fixture
def svet(monkeypatch):
    k, baza = f8.pripremi(monkeypatch, {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv ABC", "tip": "radno", "status": "aktivan",
             "case_dna": {"verzija": 3}},
            {"id": PB, "user_id": "uid-B", "naziv": "Tajni B", "tip": "radno", "status": "aktivan", "case_dna": {}},
        ],
        "rocista": [{"id": ROC, "predmet_id": PA, "user_id": "uid-A", "sud": "Osnovni sud u Beogradu",
                     "datum": (DANAS + timedelta(days=1)).isoformat(), "status": "zakazano"}],
        "predmet_dokazi": [], "predmet_dokumenti": [], "predmet_issues": [], "predmet_contradictions": [],
        "predmet_contradiction_claims": [], "zadaci": [], "intake_jobs": [],
        "case_actions": [], "events": [], "case_evolution_consequences": [], "notifications": [],
        "autonomy_work_items": [], "kancelarije": [], "kancelarija_clanovi": [],
        "outcome_log": [], "case_patterns": [], "recommendation_log": [], "predmet_hronologija": [],
        "v2_mutation_idempotency": [], "audit_immutable": [],
    })
    yield k, baza
    f8.ocisti()


def _terminalni(baza):
    return [e for e in baza.tabele["events"] if e.get("event_type") == "MatterBecameTerminal"]


def _otvori_akcije(baza):
    from services.case_evolution import _consequence_refresh_case_actions
    from services.event_bus import Event, EventType
    asyncio.run(_consequence_refresh_case_actions(Event(
        type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=PA, payload={}, event_id="pocetak")))
    return [a for a in baza.tabele["case_actions"] if a["status"] == "open" and a["predmet_id"] == PA]


def _predmet(baza, pid):
    return next(p for p in baza.tabele["predmeti"] if p["id"] == pid)


def test_ceo_lanac_patch_do_autonomije(svet):
    k, baza = svet
    assert _otvori_akcije(baza), "ročište sutra → otvorena akcija pre zatvaranja"
    from services.agent_tasks import hearing_prep as hp
    pre = asyncio.run(hp.planiraj(baza))
    assert [c["predmet_id"] for c in pre["kandidati"]] == [PA], "aktivan predmet → planer predlaže pripremu"
    baza.tabele["autonomy_work_items"].append({"id": "w1", "user_id": "uid-A", "predmet_id": PA,
                                               "work_type": hp.WORK_TYPE, "trigger_ref": ROC, "status": "QUEUED"})

    r = k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("A"))
    assert r.status_code == 200, r.text
    ev = _terminalni(baza)
    assert len(ev) == 1
    from services.event_bus import matter_terminal_event_id
    assert ev[0]["id"] == matter_terminal_event_id(PA, "zatvoren", r.json()["updated_at"])
    assert ev[0]["payload"]["prethodni_status"] == "aktivan" and ev[0]["payload"]["trigger"] == "predmet_patch"

    dispecuj(2)
    posledice = {c["consequence_name"]: c["status"] for c in baza.tabele["case_evolution_consequences"]
                 if c["event_id"] == ev[0]["id"]}
    assert posledice == {"refresh_case_actions": "completed"}
    assert not [a for a in baza.tabele["case_actions"] if a["status"] == "open" and a["predmet_id"] == PA]

    posle = asyncio.run(hp.planiraj(baza))
    assert posle["kandidati"] == [], "završen predmet → nema novog posla"
    assert {p["trigger_ref"] for p in posle["ponisteni"]} == {ROC}, "čekajući posao se poništava"

    p = _predmet(baza, PA)
    assert lb.je_terminalan(p)
    assert lb.outcome_view(p, None)["status"] == lb.OUTCOME_UNKNOWN


def test_isti_status_i_druga_polja_bez_dogadjaja(svet):
    k, baza = svet
    k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("A"))
    k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("A"))
    k.patch(f"/api/predmeti/{PA}", json={"naziv": "Novi naziv"}, headers=f8.zaglavlje("A"))
    assert len(_terminalni(baza)) == 1


def test_neterminalan_status_bez_dogadjaja(svet):
    k, baza = svet
    assert k.patch(f"/api/predmeti/{PA}", json={"status": "na_cekanju"}, headers=f8.zaglavlje("A")).status_code == 200
    assert _terminalni(baza) == []


@pytest.mark.parametrize("status", ["arhiviran", "odbijen"])
def test_svaki_zavrsni_status(svet, status):
    k, baza = svet
    k.patch(f"/api/predmeti/{PA}", json={"status": status}, headers=f8.zaglavlje("A"))
    assert [e["payload"]["novi_status"] for e in _terminalni(baza)] == [status]


def test_ponovno_otvaranje_pa_zatvaranje_nov_dogadjaj(svet):
    k, baza = svet
    k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("A"))
    k.patch(f"/api/predmeti/{PA}", json={"status": "aktivan"}, headers=f8.zaglavlje("A"))
    k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("A"))
    ev = _terminalni(baza)
    assert len(ev) == 2 and ev[0]["id"] != ev[1]["id"]


def test_ponovljena_emisija_istog_prelaza_jedan_red(svet):
    _, baza = svet
    from services.event_bus import emit_matter_terminal
    for _ in range(3):
        asyncio.run(emit_matter_terminal(user_id="uid-A", predmet_id=PA, novi_status="zatvoren",
                                         prethodni_status="aktivan", prelaz_ref="2026-10-10T01:00:00", trigger="t",
                                         supa=baza))
    assert len(_terminalni(baza)) == 1


def test_emiter_odbija_neprelaz(svet):
    _, baza = svet
    from services.event_bus import emit_matter_terminal
    for kw in ({"novi_status": "aktivan", "prethodni_status": "zatvoren"},
               {"novi_status": "zatvoren", "prethodni_status": "zatvoren"},
               {"novi_status": "zatvoren", "prethodni_status": "aktivan", "prelaz_ref": ""}):
        args = {"user_id": "uid-A", "predmet_id": PA, "prelaz_ref": "x", "trigger": "t", "supa": baza, **kw}
        assert asyncio.run(emit_matter_terminal(**args)) is False
    assert _terminalni(baza) == []


def test_tudj_predmet_bez_dogadjaja(svet):
    k, baza = svet
    assert k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("B")).status_code == 404
    assert _terminalni(baza) == [] and _predmet(baza, PA)["status"] == "aktivan"


def test_ishod_kroz_learning_zatvara_i_emituje_jednom(svet):
    k, baza = svet
    telo = {"predmet_id": PA, "ishod": "nagodba"}
    k.post("/api/learning/outcome", json=telo, headers=f8.zaglavlje("A"))
    k.post("/api/learning/outcome", json=telo, headers=f8.zaglavlje("A"))
    ev = _terminalni(baza)
    assert len(ev) == 1 and ev[0]["payload"]["trigger"] == "learning_outcome"


def test_pad_outbox_ne_ponistava_izmenu_statusa(svet):
    k, baza = svet
    baza.greske["events"] = Exception("outbox down")
    r = k.patch(f"/api/predmeti/{PA}", json={"status": "zatvoren"}, headers=f8.zaglavlje("A"))
    assert r.status_code == 200 and _predmet(baza, PA)["status"] == "zatvoren"
