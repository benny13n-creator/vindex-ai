# -*- coding: utf-8 -*-
"""
Tests for GET /api/matter-intel/predmeti/{predmet_id} — Matter Intelligence.
Pure unit tests — no live Supabase, no OpenAI calls.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _user():
    return {"user_id": "cccc0000-0000-0000-0000-000000000003", "email": "test@vindex.rs"}


PID = "pred-mi-0001"


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','order','limit','execute','is_','in_']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _make_supa(predmet, dokazi=None, dokumenti=None, rokovi=None):
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":         return _make_chain([predmet])
        if name == "predmet_dokazi":   return _make_chain(dokazi or [])
        if name == "predmet_dokumenti":return _make_chain(dokumenti or [])
        if name == "rocista":          return _make_chain(rokovi or [])
        return _make_chain([])
    supa.table.side_effect = _table
    return supa


_PRED_RADNO = {"id": PID, "naziv": "Nezakonit otkaz", "tip": "radno",
               "status": "aktivan", "rizik": None, "opis": None, "created_at": "2026-01-01"}

# ── T1: bez dokaza → Nema dokaza + Visok rizik ────────────────────────────────

@pytest.mark.anyio
async def test_no_evidence_high_risk():
    from routers.matter_intel import get_matter_intel
    supa = _make_supa(_PRED_RADNO)
    with patch("routers.matter_intel._get_supa", return_value=supa):
        result = await get_matter_intel(PID, _user())
    assert result["snaga_dokaza"] == "Nema dokaza"
    assert result["procesni_rizik"] == "Visok"
    assert result["rizik_boja"] == "red"
    assert result["health_score"] < 50


# ── T2: većinom jaki dokazi → Jaka snaga ─────────────────────────────────────

@pytest.mark.anyio
async def test_strong_evidence_label():
    from routers.matter_intel import get_matter_intel
    dokazi = [{"snaga":"jaka","kategorija":"ugovor","pravni_element":""},
              {"snaga":"jaka","kategorija":"dopis","pravni_element":""},
              {"snaga":"srednja","kategorija":"podnesak","pravni_element":""}]
    supa = _make_supa(_PRED_RADNO, dokazi=dokazi)
    with patch("routers.matter_intel._get_supa", return_value=supa):
        result = await get_matter_intel(PID, _user())
    assert result["snaga_dokaza"] == "Jaka"
    assert result["snaga_pct"] >= 60


# ── T3: nedostajući dokumenti za tip "radno" ─────────────────────────────────

@pytest.mark.anyio
async def test_missing_docs_radno():
    from routers.matter_intel import get_matter_intel
    # Radno pravo očekuje: ugovor, dopis, finansijska_dokumentacija, sudska_odluka
    # Uploadujemo samo ugovor
    dokumenti = [{"tip_dokaza": "ugovor"}]
    supa = _make_supa(_PRED_RADNO, dokumenti=dokumenti)
    with patch("routers.matter_intel._get_supa", return_value=supa):
        result = await get_matter_intel(PID, _user())
    missing = result["nedostajuci_dokazi"]
    assert "ugovor" not in missing
    assert "dopis" in missing
    assert result["nedostajuci_count"] == 3


# ── T4: kritičan rok u 7 dana povećava rizik ─────────────────────────────────

@pytest.mark.anyio
async def test_critical_deadline_raises_risk():
    from routers.matter_intel import get_matter_intel
    sutra = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    rokovi = [{"sud": "Osnovni sud", "datum": sutra, "status": "aktivan"}]
    supa = _make_supa(_PRED_RADNO, rokovi=rokovi)
    with patch("routers.matter_intel._get_supa", return_value=supa):
        result = await get_matter_intel(PID, _user())
    assert result["kriticni_rokovi"] >= 1
    assert result["procesni_rizik"] in ("Srednji", "Visok")


# ── T5: health_score uvek u [5, 95] ──────────────────────────────────────────

@pytest.mark.anyio
async def test_health_score_bounds():
    from routers.matter_intel import get_matter_intel
    # Najgori scenario: bez dokaza + kritičan rok
    sutra = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    rokovi = [{"sud": "Osnovni sud", "datum": sutra, "status": "aktivan"}]
    supa = _make_supa(_PRED_RADNO, rokovi=rokovi)
    with patch("routers.matter_intel._get_supa", return_value=supa):
        result = await get_matter_intel(PID, _user())
    assert 5 <= result["health_score"] <= 95


# ── T6: identify_case_problems — kritičan rok → kritičan problem ─────────────
# (Core Consolidation Sec 1.2, 2026-07-22 — zamenjuje obrisani _compute_next_action;
#  jedina preostala implementacija "sledece akcije" u celoj platformi.)

def test_next_action_critical_deadline():
    from services.risk_engine import identify_case_problems
    rizik = {"kriticni_rokovi": 2, "snaga_dokaza": "Jaka", "nedostajuci_dokazi": [],
              "predstojeći_rokovi": 1}
    result = identify_case_problems(rizik, "radno")
    assert any(p["ozbiljnost"] == "kritican" for p in result)
    assert any("2" in p["problem"] for p in result)


# ── T7: identify_case_problems — bez dokaza ──────────────────────────────────

def test_next_action_no_evidence():
    from services.risk_engine import identify_case_problems
    rizik = {"kriticni_rokovi": 0, "snaga_dokaza": "Nema dokaza", "nedostajuci_dokazi": [],
              "predstojeći_rokovi": 0}
    result = identify_case_problems(rizik, "parnicno")
    assert any("dokaz" in p["problem"].lower() for p in result)


# ── T7b: identify_case_problems — tip_predmeta se koristi (regresija: parametar
# je ranije bio primljen ali nikad koriscen u telu funkcije, ispravljeno u
# brutal-audit prolazu 2026-07-22) ────────────────────────────────────────────

def test_next_action_uses_tip_predmeta_for_phrasing():
    from services.risk_engine import identify_case_problems
    rizik = {"kriticni_rokovi": 0, "snaga_dokaza": "Nema dokaza", "nedostajuci_dokazi": [],
              "predstojeći_rokovi": 0}
    radno = identify_case_problems(rizik, "radno")
    ostalo = identify_case_problems(rizik, "ostalo")
    assert any("radni predmet" in p["problem"] for p in radno)
    assert not any("radni predmet" in p["problem"] for p in ostalo)


# ── T8: 404 na nepostojeći predmet ───────────────────────────────────────────

@pytest.mark.anyio
async def test_matter_intel_404():
    from fastapi import HTTPException
    from routers.matter_intel import get_matter_intel
    supa = MagicMock()
    supa.table.return_value = _make_chain([])
    with patch("routers.matter_intel._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await get_matter_intel("ghost-id", _user())
    assert exc.value.status_code == 404


# ── Faza 2.2 cleanup (2026-07-18): _d consolidated from two identical local
# closures into one module-level function — behavior-preserving, same body.

def test_d_returns_empty_list_for_exception():
    from routers.matter_intel import _d
    assert _d(Exception("boom")) == []


def test_d_returns_data_for_normal_response():
    from routers.matter_intel import _d
    resp = MagicMock()
    resp.data = [{"id": 1}, {"id": 2}]
    assert _d(resp) == [{"id": 1}, {"id": 2}]


def test_d_returns_empty_list_when_data_is_none():
    from routers.matter_intel import _d
    resp = MagicMock()
    resp.data = None
    assert _d(resp) == []
