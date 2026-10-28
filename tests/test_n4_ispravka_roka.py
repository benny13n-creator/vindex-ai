# -*- coding: utf-8 -*-
"""N4 — ispravka AI predloga roka (POST /api/rokovi/{id}/ispravi) nad stvarnim rutama i stvarnim lancem odluka
(shared/rok_potvrda, audit_immutable u bazi u memoriji). Browser tok: frontend-v2-ng/tests/live-n4-rokovi-e2e.mjs."""
from datetime import date, timedelta

import pytest

from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401


@pytest.fixture
def lanac(solo, monkeypatch):
    """`log_action` upisuje u bazu u memoriji (uz `seq` i stvarnu proveru AUDITABLE_ACTIONS)."""
    import shared.audit_immutable as AUD
    k, b = solo
    brojac = {"seq": 0}

    async def _upis(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        if action not in AUD.AUDITABLE_ACTIONS:
            return None
        if b.__dict__.get("lanac_puca") == action:
            return None
        brojac["seq"] += 1
        r = b.table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                               "resource_id": resource_id, "metadata": metadata or {}, "seq": brojac["seq"]}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(AUD, "log_action", _upis)
    import shared.rokovi as RD
    monkeypatch.setattr(RD, "_sema_ima_129", lambda supa=None: True)
    return k, b


def _predlog(b, rid="rok-ai", uid="uid-A", pid="p-1", dana=10):
    b.tabele.setdefault("predmeti", []).append({"id": pid, "user_id": uid, "naziv": "P", "status": "aktivan"})
    d = (date.today() + timedelta(days=dana)).isoformat()
    b.tabele.setdefault("predmet_hronologija", []).append({"id": rid, "predmet_id": pid, "user_id": uid, "dogadjaj": "Rok za tužbu",
        "datum": d, "datum_iso": d, "vaznost": "važan", "akter": "Smart Intake (AI)", "izvor": "AI_AUTONOMOUS", "vrsta": "rok",
        "dokument_id": "dok-1", "dokument_naziv": "Resenje.pdf"})
    return d


def _stanje(k, rid):
    from shared.rok_potvrda import odluke, stanje_roka
    return stanje_roka(rid, odluke([rid], True))


def test_ispravka_upisuje_potvrdjen_nov_rok_i_odbija_predlog(lanac):
    k, b = lanac
    _predlog(b)
    tacan = (date.today() + timedelta(days=12)).isoformat()
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": tacan}, headers=A)
    assert r.status_code == 200, r.text
    d = r.json()
    nov = next(x for x in b.tabele["predmet_hronologija"] if x["id"] == d["rok_id"])
    assert nov["datum_iso"] == tacan and nov["izvor"] == "HUMAN_DIRECT" and nov["dokument_id"] == "dok-1" and nov["vrsta"] == "rok"
    assert _stanje(k, d["rok_id"]) == "CONFIRMED" and _stanje(k, "rok-ai") == "REJECTED" and d["stari_odbijen"] is True


def test_isti_datum_nije_ispravka(lanac):
    k, b = lanac
    d = _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": d}, headers=A)
    assert r.status_code == 409 and len(b.tabele["predmet_hronologija"]) == 1
    assert _stanje(k, "rok-ai") == "UNCONFIRMED"


@pytest.mark.parametrize("telo,status", [({"datum_iso": "2027-02-30"}, 422), ({"datum_iso": "2026-W44-2"}, 422)])
def test_neispravan_datum(lanac, telo, status):
    k, b = lanac
    _predlog(b)
    assert k.post("/api/rokovi/rok-ai/ispravi", json=telo, headers=A).status_code == status


def test_tudj_i_potvrdjen_rok(lanac):
    k, b = lanac
    _predlog(b)
    tacan = (date.today() + timedelta(days=13)).isoformat()
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": tacan}, headers=B).status_code == 404
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": tacan}, headers=A).status_code == 409
    assert len(b.tabele["predmet_hronologija"]) == 1


def test_delimican_neuspeh_pa_ponovni_pokusaj_ne_pravi_drugi_rok(lanac):
    k, b = lanac
    _predlog(b)
    tacan = (date.today() + timedelta(days=14)).isoformat()
    b.lanac_puca = "rok_potvrdjen"                               # upis novog reda uspe, potvrda ne
    r1 = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": tacan}, headers=A)
    assert r1.status_code == 503
    # S1: predlog se odbija PRE potvrde ispravke — posle pada potvrde predlog je odbijen, ispravka upisana i nepotvrđena,
    # a NIJEDNA obaveza nije potvrđena (ranije: predlog ostajao nepotvrđen uz mogućnost druge potvrđene obaveze)
    assert _stanje(k, "rok-ai") == "REJECTED"
    assert [x for x in b.tabele["predmet_hronologija"] if x["datum_iso"] == tacan and _stanje(k, x["id"]) == "CONFIRMED"] == []
    b.lanac_puca = None
    r2 = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": tacan}, headers=A)
    assert r2.status_code == 200, r2.text
    novi = [x for x in b.tabele["predmet_hronologija"] if x["datum_iso"] == tacan]
    assert len(novi) == 1 and _stanje(k, novi[0]["id"]) == "CONFIRMED" and _stanje(k, "rok-ai") == "REJECTED"
