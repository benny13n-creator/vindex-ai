"""NS007 Task 1–2 — `services/autonomy.py` nad lažnom bazom (pravila pod konkurencijom: test_ns007_t1_t2_contract_pg)."""
import asyncio

import pytest

import tests.ns007_fake as f7
from services import autonomy as au

UID, PID = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b"


def _k(kljuc, trigger_ref="roc-1", cost="PAID"):
    return {"user_id": UID, "predmet_id": PID, "agent_type": "hearing_prep", "work_type": "HEARING_PREP",
            "trigger_type": "ROCISTE", "trigger_ref": trigger_ref, "dedupe_key": kljuc, "reason": "Ročište sutra",
            "cost_class": cost, "budget_key": f"solo:{UID}"}


@pytest.fixture
def baza():
    return f7.Baza7({"predmeti": [{"id": PID, "user_id": UID}]})


def test_ciklus_drugi_put_already_claimed_a_neispravan_prozor_odbijen(baza):
    assert asyncio.run(au.zauzmi_ciklus(baza, "auto:2026-10-10T03", "r1"))["ishod"] == "CLAIMED"
    assert asyncio.run(au.zauzmi_ciklus(baza, "auto:2026-10-10T03", "r2"))["ishod"] == "ALREADY_CLAIMED"
    assert asyncio.run(au.zavrsi_ciklus(baza, "auto:2026-10-10T03", "r2", True, {})) is False, "tuđi run ne završava"
    assert asyncio.run(au.zavrsi_ciklus(baza, "auto:2026-10-10T03", "r1", True, {"poslova": 0})) is True
    with pytest.raises(ValueError):
        asyncio.run(au.zauzmi_ciklus(baza, "auto; DROP", "r3"))


def test_greska_baze_pri_zauzimanju_ciklusa_nije_already_claimed(baza):
    baza.greske["autonomy_cycles"] = RuntimeError("baza nedostupna")
    with pytest.raises(RuntimeError):
        asyncio.run(au.zauzmi_ciklus(baza, "auto:w", "r1"))


def test_rezultat_samo_vlasnik_i_samo_dozvoljeno_stanje_kvaliteta(baza):
    wid = asyncio.run(au.upisi_kandidata(baza, _k("k1")))["id"]
    vlasnik = au.novi_vlasnik()
    assert asyncio.run(au.zauzmi_posao(baza, wid, vlasnik, limit=5))["ishod"] == "CLAIMED"
    args = dict(title="T", summary="S", content={"a": 1}, source_refs=[], quality_state=au.AI_PRIPREMLJENO)
    assert asyncio.run(au.sacuvaj_rezultat(baza, wid, au.novi_vlasnik(), **args)) is False
    with pytest.raises(ValueError):
        asyncio.run(au.sacuvaj_rezultat(baza, wid, vlasnik, **{**args, "quality_state": "VERIFIED_FACT"}))
    assert asyncio.run(au.sacuvaj_rezultat(baza, wid, vlasnik, **args)) is True
    r = baza.tabele["autonomy_work_items"][0]
    assert r["status"] == au.READY and r["lease_owner"] is None and r["quality_state"] == au.AI_PRIPREMLJENO
    assert asyncio.run(au.sacuvaj_rezultat(baza, wid, vlasnik, **args)) is False, "drugi upis istog rezultata ne prolazi"


def test_neuspeh_je_konacan_i_kod_je_bezbedan(baza):
    wid = asyncio.run(au.upisi_kandidata(baza, _k("k1")))["id"]
    v = au.novi_vlasnik()
    asyncio.run(au.zauzmi_posao(baza, wid, v, limit=5))
    assert asyncio.run(au.oznaci_neuspeh(baza, wid, v, "context; drop table")) is True
    r = baza.tabele["autonomy_work_items"][0]
    assert r["status"] == au.FAILED and r["safe_error_code"] == "UNKNOWN_ERROR"
    assert asyncio.run(au.zauzmi_posao(baza, wid, v, limit=5))["ishod"] == "NOT_CLAIMABLE"


def test_zastareli_menja_samo_isti_okidac_druge_verzije(baza):
    stari = asyncio.run(au.upisi_kandidata(baza, _k("roc-1:v1")))["id"]
    drugi_okidac = asyncio.run(au.upisi_kandidata(baza, _k("roc-2:v1", trigger_ref="roc-2")))["id"]
    novi = asyncio.run(au.upisi_kandidata(baza, _k("roc-1:v2")))["id"]
    assert asyncio.run(au.zastareli(baza, UID, PID, "HEARING_PREP", "roc-1", "roc-1:v2")) == 1
    st = {r["id"]: r["status"] for r in baza.tabele["autonomy_work_items"]}
    assert st == {stari: au.SUPERSEDED, drugi_okidac: au.QUEUED, novi: au.QUEUED}
    assert len(baza.tabele["autonomy_work_items"]) == 3, "zastarelo se ne briše"


def test_neispravan_limit_iz_okruzenja_je_nepoznat(baza, monkeypatch):
    monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "neograniceno")
    assert au.budzet_limit() is None
    wid = asyncio.run(au.upisi_kandidata(baza, _k("k1")))["id"]
    assert asyncio.run(au.zauzmi_posao(baza, wid, au.novi_vlasnik()))["ishod"] == "BUDGET_UNKNOWN"
