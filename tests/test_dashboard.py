# -*- coding: utf-8 -*-
"""
Tests for routers/dashboard.py — Command Center + Matter Health Score.
All tests run without live Supabase (mocked with table-name routing).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import date, timedelta
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
                  beleske=None, dokumenti=None, ist_recent=None, rokovi_tabela=None):
    """
    Route by table name — safe for concurrent asyncio.gather calls.
    predmet_istorija is queried twice; discriminated by select() fields:
    - risk query selects "odgovor" → returns risks data
    - recent query selects only "predmet_id" → returns ist_recent data

    rokovi_tabela: rows from the separate "rokovi" table (nightly repair,
    2026-07-24) — distinct from "rokovi" the local variable name (which
    historically held predmet_hronologija rows; kept as-is to avoid
    touching every existing call site in this file).
    """
    supa = MagicMock()
    risk_data    = risks      or []
    ist_rec_data = ist_recent or []

    table_map = {
        "predmeti":            predmeti      or [],
        "rocista":             rocista       or [],
        "predmet_hronologija": rokovi        or [],
        "predmet_beleske":     beleske       or [],
        "predmet_dokumenti":   dokumenti     or [],
        "rokovi":              rokovi_tabela or [],
    }

    def _table(name):
        if name == "predmet_istorija":
            # Discriminate by select fields — thread-safe, no call counter needed
            def _select(fields):
                data = risk_data if "odgovor" in fields else ist_rec_data
                return _make_chain(data)
            chain = MagicMock()
            chain.select = MagicMock(side_effect=_select)
            return chain
        return _make_chain(table_map.get(name, []))

    supa.table = MagicMock(side_effect=_table)
    return supa


def _make_health_supa(pred=None, bel=None, risk=None, kom=None, hron=None, dok=None, roc=None, dokazi=None):
    """Route health queries by table name — each table queried at most once.
    `risk`/`hron` params are kept for signature compatibility with older
    call sites in this file but no longer read by matter_health_score since
    Project Sentinel (2026-08-03) delegated scoring to
    services/risk_engine.py::calculate_procesni_rizik — `dokazi` (predmet_dokazi)
    is the new input that actually drives the risk portion of the score."""
    supa = MagicMock()
    table_map = {
        "predmeti":            pred   or [],
        "predmet_beleske":     bel    or [],
        "predmet_istorija":    risk   or [],
        "predmet_komentari":   kom    or [],
        "predmet_hronologija": hron   or [],
        "predmet_dokumenti":   dok    or [],
        "rocista":             roc    or [],
        "predmet_dokazi":      dokazi or [],
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
async def test_cc_rokovi_tabela_merged_into_rokovi_7():
    """NIGHTLY REPAIR (2026-07-24), Faza 2 item 5: a deadline entered via
    the "rokovi" table (the one AI Deadline Guardian / zastarelost.py
    reads, and 30+ other modules write to) must now also appear in the
    Command Center's rokovi_7/hitni_rokovi -- previously ONLY
    predmet_hronologija rows were shown here, so a deadline entered
    through any rokovi-writing flow was invisible on the main dashboard."""
    from routers.dashboard import command_center
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rokovi_tabela = [{"id": "r1", "naziv": "Žalba na presudu", "datum": tomorrow,
                       "tip": "zalba_zpp", "predmet_id": PID, "opis": ""}]
    supa = _make_cc_supa(predmeti=preds, rokovi_tabela=rokovi_tabela)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())

    assert any(r["dogadjaj"] == "Žalba na presudu" for r in result["rokovi_7_dana"])
    assert any(r["dogadjaj"] == "Žalba na presudu" for r in result["hitni_rokovi"])


@pytest.mark.anyio
async def test_cc_rokovi_7_merges_both_sources_without_dropping_either():
    from routers.dashboard import command_center
    from datetime import date, timedelta
    in3 = (date.today() + timedelta(days=3)).isoformat()
    in4 = (date.today() + timedelta(days=4)).isoformat()
    preds = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    hronologija = [{"predmet_id": PID, "dogadjaj": "Iz hronologije", "datum_iso": in3, "vaznost": "srednja"}]
    rokovi_tabela = [{"id": "r1", "naziv": "Iz rokovi tabele", "datum": in4, "tip": "rok", "predmet_id": PID, "opis": ""}]
    supa = _make_cc_supa(predmeti=preds, rokovi=hronologija, rokovi_tabela=rokovi_tabela)
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await command_center(request=_req(), user=_user())

    dogadjaji = {r["dogadjaj"] for r in result["rokovi_7_dana"]}
    assert "Iz hronologije" in dogadjaji
    assert "Iz rokovi tabele" in dogadjaji


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
    """Project Sentinel (2026-08-03): score/status now come exclusively from
    services/risk_engine.py::calculate_procesni_rizik (same source ccc.py and
    matter_intel.py already use) instead of this endpoint's own 5-category
    formula. With strong evidence (jaka), no missing expected doc types, and
    no critical (0-7 day) rociste, the risk formula's own floor for
    rizik_score is 30 (the only available discount is -20 for "Jaka" off a
    base of 50) → health_score=70, nivo="Nizak" → status="zdrav"."""
    from routers.dashboard import matter_health_score
    far_future = (date.today() + timedelta(days=60)).isoformat()
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[{"id": "b1"}],                                            # aktivnost present
        dokazi=[{"snaga": "jaka"}],                                    # snaga_dokaza=Jaka
        dok=[{"id": "d1", "tip_dokaza": "podnesak"},
             {"id": "d2", "tip_dokaza": "dopis"}],                     # covers both EXPECTED_DOCS["ostalo"]
        roc=[{"datum": far_future}],                                   # non-critical, but present
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 70
    assert result["status"] == "zdrav"
    assert result["razlozi"] == []
    assert result["faktori"]["ima_rociste"] is True


@pytest.mark.anyio
async def test_health_kriticno_no_activity_high_risk():
    """No dokazi at all (+20) plus a critical (within 7 days) rociste (+20)
    → rizik_score=90 → health_score=10, nivo="Visok" → status="kriticno"."""
    from routers.dashboard import matter_health_score
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[], kom=[],
        dokazi=[],
        dok=[],
        roc=[{"datum": tomorrow}],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] < 50
    assert result["status"] == "kriticno"
    assert len(result["razlozi"]) >= 2


@pytest.mark.anyio
async def test_health_faktori_aktivnost_reports_real_subscore_not_total():
    """NIGHTLY REPAIR (2026-07-24), Faza 2 item 7: faktori.aktivnost used
    to be a nonsensical re-derivation from the TOTAL score. This test picks
    a case with no activity but a real (non-zero) total health_score, to
    prove aktivnost is reported independently of the total."""
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[], kom=[],                      # NEMA aktivnosti -> aktivnost poeni = 0
        dokazi=[{"snaga": "jaka"}],          # health_score=70 (non-zero, non-25-coincidence)
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 70
    assert result["faktori"]["aktivnost"] == 0


@pytest.mark.anyio
async def test_health_faktori_aktivnost_reports_25_when_activity_present():
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[{"id": "b1"}],                  # ima aktivnosti -> 25 poena
        dokazi=[{"snaga": "jaka"}],
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["faktori"]["aktivnost"] == 25


@pytest.mark.anyio
async def test_health_upozorenje_range():
    """dokazi snage "srednja" doesn't move rizik_score off its base of 50
    (only "Jaka"/-20 and "Slaba"/+15 do) → health_score=50, nivo="Srednji"
    → status="upozorenje"."""
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[],
        dokazi=[{"snaga": "srednja"}],
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["score"] == 50
    assert result["status"] == "upozorenje"


@pytest.mark.anyio
async def test_health_returns_predmet_id():
    from routers.dashboard import matter_health_score
    supa = _make_health_supa(pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}])
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["predmet_id"] == PID
    assert "score" in result
    assert "status" in result
    assert "razlozi" in result
    assert "faktori" in result


@pytest.mark.anyio
async def test_health_hitni_rokovi_reduce_score():
    """Project Sentinel (2026-08-03): 'hitnih_rokova' now comes from
    calculate_procesni_rizik's kriticni_rokovi count, which reads the
    `rocista` table (0-7 day window), not predmet_hronologija's `vaznost`
    tag (48h window) the old formula used — a different canonical source,
    same observable guarantee: multiple near-term hearings visibly reduce
    the score and appear in razlozi."""
    from routers.dashboard import matter_health_score
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    supa = _make_health_supa(
        pred=[{"id": PID, "status": "aktivan", "tip": "ostalo"}],
        bel=[{"id": "b1"}],
        dokazi=[{"snaga": "jaka"}],
        dok=[{"id": "d1", "tip_dokaza": "podnesak"}, {"id": "d2", "tip_dokaza": "dopis"}],
        roc=[{"datum": tomorrow}, {"datum": tomorrow}],
    )
    with patch("routers.dashboard._get_supa", return_value=supa):
        result = await matter_health_score(predmet_id=PID, request=_req(), user=_user())
    assert result["faktori"]["hitnih_rokova"] == 2
    assert any("kritičan rok" in r.lower() for r in result["razlozi"])


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
