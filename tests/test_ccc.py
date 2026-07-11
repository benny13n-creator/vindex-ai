# -*- coding: utf-8 -*-
"""
Tests for GET /api/ccc/predmeti/{predmet_id} — Case Command Center.
All tests run without live Supabase (mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


UID = "aaaa0000-0000-0000-0000-000000000001"
PID = "pred-ccc-0001"


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','gte','lte','like','order','limit','execute',
              'insert','update','delete','is_','in_','desc']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _make_supa(predmet, dokazi=None, dokumenti=None, rokovi=None, billing=None, hron=None, klijenti=None):
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":
            return _make_chain([predmet])
        if name == "predmet_dokazi":
            return _make_chain(dokazi or [])
        if name == "predmet_dokumenti":
            return _make_chain(dokumenti or [])
        if name == "rocista":
            return _make_chain(rokovi or [])
        if name == "billing_entries":
            return _make_chain(billing or [])
        if name == "predmet_hronologija":
            return _make_chain(hron or [])
        if name == "predmet_klijenti":
            return _make_chain(klijenti or [])
        return _make_chain([])
    supa.table.side_effect = _table
    return supa


_PREDMET = {
    "id": PID, "naziv": "Nezakonit otkaz", "tip": "radno",
    "status": "aktivan", "tuzilac": "Petar Petrović", "tuzeni": "Firma doo",
    "oblast": None, "rizik": None, "vrednost_spora": 500000, "opis": None, "created_at": "2026-01-01",
}

# ── T1: osnovna struktura odgovora ────────────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_response_structure():
    from routers.ccc import get_ccc
    supa = _make_supa(_PREDMET)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert "predmet" in result
    assert "dok_stats" in result
    assert "rokovi" in result
    assert "billing" in result
    assert "health_score" in result
    assert "nedostajuci" in result
    assert "kritican_rok" in result
    assert result["predmet"]["naziv"] == "Nezakonit otkaz"


# ── T2: dokazi statistika ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_dok_stats_counts():
    from routers.ccc import get_ccc
    dokazi = [
        {"snaga": "jaka",   "kategorija": "ugovor"},
        {"snaga": "jaka",   "kategorija": "dopis"},
        {"snaga": "srednja","kategorija": "podnesak"},
        {"snaga": "slaba",  "kategorija": "vestacki_nalaz"},
    ]
    supa = _make_supa(_PREDMET, dokazi=dokazi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    ds = result["dok_stats"]
    assert ds["jaka"]   == 2
    assert ds["srednja"]== 1
    assert ds["slaba"]  == 1
    assert ds["ukupno"] == 4


# ── T3: billing agregacija ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_billing_aggregation():
    from routers.ccc import get_ccc
    billing = [
        {"iznos": 10000, "obracunato": True},
        {"iznos": 5000,  "obracunato": False},
        {"iznos": 3000,  "obracunato": False},
    ]
    supa = _make_supa(_PREDMET, billing=billing)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    b = result["billing"]
    assert b["uneseno"]     == 18000
    assert b["naplaceno"]   == 10000
    assert b["nenaplaceno"] == 8000


# ── T4: kritičan rok (≤7 dana) se detektuje ──────────────────────────────────

@pytest.mark.anyio
async def test_ccc_kritican_rok_detected():
    from routers.ccc import get_ccc
    sutra = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    rokovi = [{"id": "r1", "naziv": "Rok za odgovor", "sud": "Osnovni sud", "datum": sutra, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert result["kritican_rok"] is not None
    assert result["kritican_rok"]["naziv"] == "Rok za odgovor"
    assert result["kritican_rok"]["dana_ostalo"] <= 7


# ── T5: nema kritičnog roka kad je rok daleko ─────────────────────────────────

@pytest.mark.anyio
async def test_ccc_no_kritican_rok_when_far():
    from routers.ccc import get_ccc
    daleko = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    rokovi = [{"id": "r2", "naziv": "Rok za žalbu", "sud": "Osnovni sud", "datum": daleko, "status": "aktivan"}]
    supa = _make_supa(_PREDMET, rokovi=rokovi)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    assert result["kritican_rok"] is None


# ── T6: nedostajući dokumenti za radno pravo ─────────────────────────────────

@pytest.mark.anyio
async def test_ccc_nedostajuci_radno():
    from routers.ccc import get_ccc
    # Radno: očekuje ugovor, dopis, finansijska_dokumentacija, sudska_odluka
    # Uploadujemo samo ugovor → ostala 3 nedostaju
    dokumenti = [{"tip_dokaza": "ugovor"}]
    supa = _make_supa(_PREDMET, dokumenti=dokumenti)
    with patch("routers.ccc._get_supa", return_value=supa):
        result = await get_ccc(PID, _user())
    nedo = result["nedostajuci"]
    assert "ugovor" not in nedo
    assert "dopis" in nedo
    assert len(nedo) == 3


# ── T7: health_score pad pri kritičnim rokovima ───────────────────────────────

@pytest.mark.anyio
async def test_ccc_health_score_drops_with_critical_deadline():
    from routers.ccc import _compute_health
    # Sa kritičnim rokovima → predstojeći > 2 → -15 od baseline
    score_bez  = _compute_health({"jaka":2,"srednja":1,"slaba":0}, 0, 3)
    score_sa   = _compute_health({"jaka":2,"srednja":1,"slaba":0}, 5, 3)
    assert score_sa < score_bez


# ── T8: health_score je uvek u [0, 100] ───────────────────────────────────────

@pytest.mark.anyio
async def test_ccc_health_score_bounds():
    from routers.ccc import _compute_health
    # Ekstremi
    assert 0 <= _compute_health({"jaka":0,"srednja":0,"slaba":10}, 10, 10) <= 100
    assert 0 <= _compute_health({"jaka":10,"srednja":5,"slaba":0}, 0, 15)  <= 100


# ── T9: 404 kad predmet nije vlasništvo korisnika ────────────────────────────

@pytest.mark.anyio
async def test_ccc_404_wrong_user():
    from fastapi import HTTPException
    from routers.ccc import get_ccc
    supa = MagicMock()
    supa.table.return_value = _make_chain([])  # prazno = 404
    with patch("routers.ccc._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await get_ccc("nonexistent-id", _user())
    assert exc.value.status_code == 404
