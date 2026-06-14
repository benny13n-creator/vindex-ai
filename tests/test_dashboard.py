# -*- coding: utf-8 -*-
"""
Tests for routers/dashboard.py — Command Center + Matter Health Score.
All tests run without live Supabase (mocked with table-name routing).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/dashboard/command-center"):
    scope = {"type":"http","method":"GET","headers":[],"query_string":b"","path":path,
             "app":MagicMock(),"state":MagicMock()}
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


UID  = "aaaa0000-0000-0000-0000-000000000001"
PID  = "cccc0000-0000-0000-0000-000000000003"
PID2 = "dddd0000-0000-0000-0000-000000000004"


def _make_chain(data):
    """Return a mock chain that always returns `data` on .execute()."""
    chain = MagicMock()
    for attr in ['select','eq','neq','gte','lte','like','order','limit','execute',
                 'insert','update','delete','is_','in_','desc']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock(); r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _make_cc_supa(predmeti=None, rocista=None, rokovi=None, risks=None,
                  beleske=None, dokumenti=None, ist_recent=None):
    """
    Route by table name — safe for concurrent asyncio.gather calls.
    predmet_istorija queried twice (risks + ist_recent); uses a call counter
    for that table only, all others respond with static data.
    """
    supa = MagicMock()
    risk_data    = risks      or []
    ist_rec_data = ist_recent or []
    ist_calls    = [0]

    table_map = {
        "predmeti":            predmeti  or [],
        "rocista":             rocista   or [],
        "predmet_hronologija": rokovi    or [],
        "predmet_beleske":     beleske   or [],
        "predmet_dokumenti":   dokumenti or [],
    }

    def _table(name):
        if name == "predmet_istorija":
            idx = ist_calls[0]
            ist_calls[0] += 1
            data = risk_data if idx == 0 else ist_rec_data
            return _make_chain(data)
        return _make_chain(table_map.get(name, []))

    supa.table = MagicMock(side_effect=_table)
    return supa


def _make_health_supa(pred=None, bel=None, risk=None, kom=None, hron=None, dok=None, roc=None):
    """Route health queries by table name — each table queried at most once."""
    supa = MagicMock()
    table_map = {
        "predmeti":            pred or [],
        "predmet_beleske":     bel  or [],
        "predmet_istorija":    risk or [],
        "predmet_komentari":   kom  or [],
        "predmet_hronologija": hron or [],
        "predmet_dokumenti":   dok  or [],
        "rocista":             roc  or [],
    }
    supa.table = MagicMock(side_effect=lambda name: _make_chain(table_map.get(name, [])))
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# 1. command_center — happy path
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_cc_returns_required_keys():
    from routers.dashboard import command_center
    supa = _make_cc_supa(
        predmeti=[{"id": PID, "naziv": "Test", "status": "aktivan", "updated_at": "2026-01-01"}]
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    required = {"ukupno_predmeta","ukupno_aktivnih","rokovi_7_dana","hitni_rokovi",
                "neaktivni_30_dana","summary","danasnja_rocista","predmeti_visok_rizik",
                "pad_procene","novi_dokumenti","ai_preporuke","statistike"}
    assert required.issubset(set(result.keys()))


@pytest.mark.anyio
async def test_cc_empty_state():
    from routers.dashboard import command_center
    supa = _make_cc_supa()
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert result["ukupno_aktivnih"] == 0
    assert result["danasnja_rocista"] == []
    assert result["hitni_rokovi"] == []
    assert result["ai_preporuke"] == []
    assert "kontrolom" in result["summary"].lower()


@pytest.mark.anyio
async def test_cc_counts_aktivni():
    from routers.dashboard import command_center
    preds = [
        {"id": PID,  "naziv": "A", "status": "aktivan",  "updated_at": "2026-01-01"},
        {"id": PID2, "naziv": "B", "status": "zatvoren", "updated_at": "2026-01-01"},
    ]
    supa = _make_cc_supa(predmeti=preds)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert result["ukupno_predmeta"] == 2
    assert result["ukupno_aktivnih"] == 1


@pytest.mark.anyio
async def test_cc_rocista_today():
    from routers.dashboard import command_center
    from datetime import date
    today = date.today().isoformat()
    preds   = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocista = [{"id": "r1", "predmet_id": PID, "sud": "Viši sud", "datum": today, "vreme": "10:00:00", "status": "zakazano"}]
    supa = _make_cc_supa(predmeti=preds, rocista=rocista)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["danasnja_rocista"]) == 1
    assert result["danasnja_rocista"][0]["sud"] == "Viši sud"


@pytest.mark.anyio
async def test_cc_hitni_rokovi_within_48h():
    from routers.dashboard import command_center
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    preds  = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rokovi = [{"predmet_id": PID, "dogadjaj": "Rok za žalbu", "datum_iso": tomorrow, "vaznost": "kritičan"}]
    supa   = _make_cc_supa(predmeti=preds, rokovi=rokovi)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["hitni_rokovi"]) == 1
    assert result["hitni_rokovi"][0]["dogadjaj"] == "Rok za žalbu"


@pytest.mark.anyio
async def test_cc_visok_rizik_detection():
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    risks = [{"predmet_id": PID, "odgovor": json.dumps({"nivo": "visok", "faktori_minus": ["nema dokaza"]}), "created_at": "2026-06-01T10:00:00"}]
    supa  = _make_cc_supa(predmeti=preds, risks=risks)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["predmeti_visok_rizik"]) == 1
    assert result["predmeti_visok_rizik"][0]["rizik_nivo"] == "visok"


@pytest.mark.anyio
async def test_cc_pad_procene():
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    risks = [
        {"predmet_id": PID, "odgovor": json.dumps({"nivo": "visok"}), "created_at": "2026-06-10"},
        {"predmet_id": PID, "odgovor": json.dumps({"nivo": "nizak"}), "created_at": "2026-06-01"},
    ]
    supa = _make_cc_supa(predmeti=preds, risks=risks)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["pad_procene"]) == 1
    assert result["pad_procene"][0]["prethodni_rizik"] == "nizak"
    assert result["pad_procene"][0]["trenutni_rizik"] == "visok"


@pytest.mark.anyio
async def test_cc_neaktivni_predmeti():
    from routers.dashboard import command_center
    preds = [
        {"id": PID,  "naziv": "Aktivan", "status": "aktivan", "updated_at": "2026-05-01"},
        {"id": PID2, "naziv": "Neaktiv", "status": "aktivan", "updated_at": "2026-01-01"},
    ]
    # PID has recent beleska → active. PID2 has nothing → neaktivan.
    beleske    = [{"predmet_id": PID}]
    ist_recent = []
    supa = _make_cc_supa(predmeti=preds, beleske=beleske, ist_recent=ist_recent)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    neaktivni_ids = [n["predmet_id"] for n in result["neaktivni_30_dana"]]
    assert PID2 in neaktivni_ids
    assert PID not in neaktivni_ids


@pytest.mark.anyio
async def test_cc_novi_dokumenti():
    from routers.dashboard import command_center
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-06-01"}]
    docs  = [{"id": "d1", "predmet_id": PID, "naziv_fajla": "ugovor.pdf", "created_at": "2026-06-14T10:00:00"}]
    supa  = _make_cc_supa(predmeti=preds, dokumenti=docs)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["novi_dokumenti"]) == 1
    assert result["novi_dokumenti"][0]["naziv_fajla"] == "ugovor.pdf"


@pytest.mark.anyio
async def test_cc_ai_preporuke_generated():
    from routers.dashboard import command_center
    from datetime import date
    today = date.today().isoformat()
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocs  = [{"id": "r1", "predmet_id": PID, "sud": "Sud", "datum": today, "vreme": "09:00:00", "status": "zakazano"}]
    supa  = _make_cc_supa(predmeti=preds, rocista=rocs)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert len(result["ai_preporuke"]) >= 1
    assert any("ročiš" in p.lower() for p in result["ai_preporuke"])


@pytest.mark.anyio
async def test_cc_statistike_keys():
    from routers.dashboard import command_center
    supa = _make_cc_supa()
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    for k in ("ukupno_aktivnih","danasnja_rocista","hitni_rokovi","predmeti_visok_rizik","neaktivni"):
        assert k in result["statistike"]


@pytest.mark.anyio
async def test_cc_handles_db_exceptions():
    from routers.dashboard import command_center
    supa = MagicMock()
    supa.table.side_effect = Exception("DB down")
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())
    assert result["ukupno_predmeta"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. matter_health_score
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_health_404_missing_predmet():
    from routers.dashboard import matter_health_score
    from fastapi import HTTPException
    supa = _make_health_supa(pred=[])
    with patch("routers.dashboard._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_health_max_score():
    from routers.dashboard import matter_health_score
    risk_json = json.dumps({"nivo": "nizak"})
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan"}],
        bel=[{"id": "b1"}],                         # aktivnost: 25
        risk=[{"odgovor": risk_json}],              # rizik nizak: 25
        kom=[],
        hron=[],                                    # no urgent deadlines: 25
        dok=[{"id": f"d{i}"} for i in range(5)],   # 5 docs: 15
        roc=[{"datum": "2026-08-01"}],              # future rociste: 10
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 100
    assert result["status"] == "zdrav"
    assert result["razlozi"] == []


@pytest.mark.anyio
async def test_health_kriticno_no_activity_high_risk():
    from routers.dashboard import matter_health_score
    risk_json = json.dumps({"nivo": "visok"})
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan"}],
        bel=[],
        risk=[{"odgovor": risk_json}],
        kom=[],
        hron=[],
        dok=[],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    # aktivnost=0, rizik=0, rokovi=25, dokumentacija=0, rociste=0 → total=25
    assert result["score"] < 50
    assert result["status"] == "kriticno"
    assert len(result["razlozi"]) >= 2


@pytest.mark.anyio
async def test_health_upozorenje_range():
    from routers.dashboard import matter_health_score
    # no activity(0) + srednji(13) + rokovi(25) + 1 doc(5) + rociste(10) = 53 → upozorenje
    risk_json = json.dumps({"nivo": "srednji"})
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan"}],
        bel=[],
        risk=[{"odgovor": risk_json}],
        kom=[],
        hron=[],
        dok=[{"id": "d1"}],
        roc=[{"datum": "2026-09-01"}],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert 50 <= result["score"] < 75
    assert result["status"] == "upozorenje"


@pytest.mark.anyio
async def test_health_returns_predmet_id():
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(pred=[{"id": PID, "status": "aktivan"}])
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["predmet_id"] == PID
    assert "score" in result
    assert "status" in result
    assert "razlozi" in result
    assert "faktori" in result


@pytest.mark.anyio
async def test_health_hitni_rokovi_reduce_score():
    from routers.dashboard import matter_health_score
    from datetime import date, timedelta
    risk_json = json.dumps({"nivo": "nizak"})
    tomorrow  = (date.today() + timedelta(days=1)).isoformat()
    urgentni  = [
        {"datum_iso": tomorrow, "vaznost": "kritičan"},
        {"datum_iso": tomorrow, "vaznost": "kritičan"},
    ]
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan"}],
        bel=[{"id": "b1"}],
        risk=[{"odgovor": risk_json}],
        kom=[],
        hron=urgentni,
        dok=[{"id": f"d{i}"} for i in range(5)],
        roc=[{"datum": tomorrow}],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    # 2 hitna → rokovi=0
    assert result["faktori"]["hitnih_rokova"] == 2
    assert any("hitan" in r.lower() or "hitnih" in r.lower() for r in result["razlozi"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Router registration
# ═══════════════════════════════════════════════════════════════════════════════

def test_router_has_command_center():
    from routers.dashboard import router
    paths = [r.path for r in router.routes]
    assert "/api/dashboard/command-center" in paths


def test_router_has_health():
    from routers.dashboard import router
    paths = [r.path for r in router.routes]
    assert "/api/predmeti/{predmet_id}/health" in paths


def test_router_tags():
    from routers.dashboard import router
    assert "dashboard" in router.tags
