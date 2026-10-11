"""RH001 Faza B — klasifikacija crash prozora rasporedivača (NS007 `/api/cron/autonomy`).

Pitanje: proces umre POSLE upisa ciklusa (`autonomy_cycles`, RUNNING), a PRE nego što je ijedan posao upisan.
Ciklus ostaje RUNNING zauvek (namerno: „RUNNING se nikad ne otima", migracija 136) — da li se rad gubi?

Dokazano ovde (lažna baza, pravi ruter, pravi planer i izvršilac pripreme ročišta, model zamenjen):
  1. isti UTC sat: svako novo okidanje → SKIPPED / ALREADY_CLAIMED, 0 poslova, 0 poziva modela;
  2. sledeći UTC sat: nov prozor → ciklus se zauzima, ročište se planira i priprema (model 1×), bez duplikata.
Gubitak je dakle ograničen na JEDAN prozor rasporeda — planer je deterministički nad trenutnim stanjem baze, a ne
nad događajima tog sata. Koliko to vremenski košta zavisi od kadence koju founder bira (NS007_RENDER_CRON_PLAN.md).
"""
from datetime import datetime, timedelta, timezone

import pytest

from services.agent_tasks import hearing_prep as hp
from tests.test_ns007_t8_hearing_executor import _model, svet  # noqa: F401 — realan predmet, ročište sutra

TAJNA = "t" * 40


class Pad(BaseException):
    """Proces je umro (ne hvata ga `except Exception` u ruteru)."""


def test_pad_posle_zauzimanja_ciklusa_gubi_najvise_jedan_prozor(svet, monkeypatch):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    mp.setenv("AUTONOMY_CRON_SECRET", TAJNA)
    import api
    import routers.autonomy as ra
    from fastapi.testclient import TestClient

    sat = datetime(2026, 10, 10, 9, 15, tzinfo=timezone.utc)
    mp.setattr(ra, "_sada", lambda: sat)
    pravi_ciklus = ba.run_autonomy_cycle

    async def umire(run_id):
        raise Pad()
    mp.setattr(ba, "run_autonomy_cycle", umire)
    k = TestClient(api.app)
    with pytest.raises(BaseException):        # middleware ga umotava u grupu izuzetaka; bitno je stanje baze
        k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    c = baza.tabele["autonomy_cycles"]
    assert len(c) == 1 and c[0]["status"] == "RUNNING" and not c[0].get("finished_at")
    assert baza.tabele.get("autonomy_work_items", []) == []

    # 1. isti sat — proces je ponovo živ, ali prozor ostaje zauzet: preskače se, bez rada i bez modela
    mp.setattr(ba, "run_autonomy_cycle", pravi_ciklus)
    mp.setattr(ra, "_sada", lambda: sat + timedelta(minutes=40))
    r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert r.json()["status"] == "SKIPPED" and r.json()["razlog"] == "ALREADY_CLAIMED"
    assert baza.tabele.get("autonomy_work_items", []) == [] and st["pozivi"] == []

    # 2. sledeći sat — nov prozor: isto ročište se planira i priprema, tačno jednom
    mp.setattr(ra, "_sada", lambda: sat + timedelta(hours=1))
    r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert r.json()["status"] == "COMPLETED"
    poslovi = baza.tabele["autonomy_work_items"]
    assert len(poslovi) == 1 and poslovi[0]["status"] == "READY_FOR_REVIEW" and len(st["pozivi"]) == 1
    assert [x["status"] for x in baza.tabele["autonomy_cycles"]] == ["RUNNING", "COMPLETED"]   # stari ostaje vidljiv
