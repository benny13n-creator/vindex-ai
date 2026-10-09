"""NS007 Task 18 — pad radnika, zakup, ponavljanje (tvrda kapija).

„Pad" = izuzetak koji NIJE `Exception` (kao umiranje procesa): izlazi iz petlje radnika i ostavlja stavku tačno onakvom
kakvu je proces ostavio. Pravi izvršilac pripreme ročišta nad realističnim predmetom, model zamenjen.

  A  dva poziva rasporedivača u istom prozoru → jedan ciklus (+ PG: 20 istovremenih → 1, test_ns007_t1_t2_contract_pg)
  B  pad posle zauzimanja, PRE modela → posle isteka zakupa posao se preuzima i završava (model 1×)
  C  pad TOKOM poziva modela → pošteno RUNNING; najviše max_attempts izvršenja, zatim DEAD_LETTER — bez beskonačnog
  D  pad POSLE upisa rezultata, pre kraja ciklusa → rezultat ostaje READY; ponovljen ciklus ga NE generiše ponovo
  E  isti rasporedivač dvaput posle završetka (i u sledećem prozoru) → bez dupliranog rada
  F–J dokazani u svojim zadacima: F ista presuda dva dana (T9–10), G promena ročišta (T6–7), H otkazano ročište
      (T6–8), I budžet nedostupan (T5), J revizija nedostupna (T17)
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from services.agent_tasks import hearing_prep as hp
from tests.test_ns007_t8_hearing_executor import _model, svet  # noqa: F401 — realan predmet, ročište sutra
import tests.ns007_fake as f7

TAJNA = "t" * 40


class Pad(BaseException):
    """Proces je umro (ne hvata ga `except Exception` u radniku)."""


def _istekni(baza):
    for r in baza.tabele["autonomy_work_items"]:
        if r.get("lease_expires_at"):
            r["lease_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()


def _rad(baza):
    return baza.tabele["autonomy_work_items"][0]


def _ciklus(ba, run="r"):
    try:
        return asyncio.run(ba.run_autonomy_cycle(run))
    except Pad:
        return "PAD"


def test_A_dva_poziva_u_istom_prozoru_jedan_ciklus(svet, monkeypatch):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    mp.setenv("AUTONOMY_CRON_SECRET", TAJNA)
    import api
    from fastapi.testclient import TestClient
    k = TestClient(api.app)
    r1 = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    r2 = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert r1.json()["status"] == "COMPLETED" and r2.json()["status"] == "SKIPPED"
    assert len(baza.tabele["autonomy_cycles"]) == 1 and len(st["pozivi"]) == 1


def test_B_pad_posle_zauzimanja_pre_modela_oporavak_posle_zakupa(svet):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    pravi = hp.deterministicki_deo
    stanje = {"padni": True}

    def det(*a, **k):
        if stanje["padni"]:
            raise Pad()
        return pravi(*a, **k)
    mp.setattr(hp, "deterministicki_deo", det)
    assert _ciklus(ba, "r1") == "PAD"
    r = _rad(baza)
    assert r["status"] == "RUNNING" and r["attempt_count"] == 1 and st["pozivi"] == []
    _ciklus(ba, "r2")
    assert st["pozivi"] == [] and _rad(baza)["status"] == "RUNNING", "važeći zakup se ne preuzima"
    stanje["padni"] = False
    _istekni(baza)
    s = _ciklus(ba, "r3")
    assert s["spremno"] == 1 and _rad(baza)["status"] == "READY_FOR_REVIEW" and _rad(baza)["attempt_count"] == 2
    assert len(st["pozivi"]) == 1


def test_C_pad_tokom_modela_ogranicen_pa_dead_letter(svet):
    baza, ba, mp = svet
    pozivi = []

    async def model_pa_pad(prompt, predmet_id, *_):
        pozivi.append(1)                     # provajder je naplatio …
        raise Pad()                          # … a proces je umro pre odgovora
    mp.setattr(hp, "_pozovi_model", model_pa_pad)
    for i in range(5):
        _ciklus(ba, f"r{i}")
        _istekni(baza)
    r = _rad(baza)
    assert r["status"] == "DEAD_LETTER" and r["safe_error_code"] == "ATTEMPTS_EXHAUSTED"
    assert len(pozivi) == 2 and r["budget_units"] == 2, "najviše max_attempts (2) izvršenja modela, zatim kraj"


def test_D_pad_posle_upisa_rezultata_ne_generise_ponovo(svet, monkeypatch):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    from services import autonomy as au
    pravi = au.revizija

    async def revizija(akcija, *a, **k):
        if akcija == "AUTONOMY_WORK_READY":
            raise Pad()                      # proces umire odmah posle trajnog upisa rezultata
        return await pravi(akcija, *a, **k)
    monkeypatch.setattr(au, "revizija", revizija)
    mp.setenv("AUTONOMY_CRON_SECRET", TAJNA)
    import api
    import routers.autonomy as ra
    from fastapi.testclient import TestClient
    k = TestClient(api.app, raise_server_exceptions=False)
    k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert _rad(baza)["status"] == "READY_FOR_REVIEW" and len(st["pozivi"]) == 1
    assert baza.tabele["autonomy_cycles"][0]["status"] == "RUNNING", "nedovršen ciklus ostaje vidljiv, ne krade se"
    monkeypatch.setattr(au, "revizija", pravi)
    mp.setattr(ra, "_sada", lambda: datetime.now(timezone.utc) + timedelta(hours=1))
    r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert r.json()["status"] == "COMPLETED" and r.json()["sazetak"]["zauzeto"] == 0
    assert len(st["pozivi"]) == 1 and len(baza.tabele["autonomy_work_items"]) == 1


def test_E_ponovljeni_rasporedivac_bez_dupliranog_rada(svet):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    mp.setenv("AUTONOMY_CRON_SECRET", TAJNA)
    import api
    import routers.autonomy as ra
    from fastapi.testclient import TestClient
    k = TestClient(api.app)
    for sat in range(4):                     # 4 prozora zaredom + po dva okidanja u svakom
        mp.setattr(ra, "_sada", lambda s=sat: datetime(2026, 10, 10, 2 + s, 5, tzinfo=timezone.utc))
        k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
        k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert len(baza.tabele["autonomy_cycles"]) == 4
    assert len(baza.tabele["autonomy_work_items"]) == 1 and len(st["pozivi"]) == 1
