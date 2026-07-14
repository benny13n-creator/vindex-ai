# -*- coding: utf-8 -*-
"""
Tests for POST /api/conflict-check — Conflict Check Engine.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _mock_usage_service():
    """Testi zovu route funkcije direktno (bez FastAPI Depends), pa endpoint-ovo
    await UsageService.consume(...) u telu funkcije izvršava se stvarno protiv
    feature_registry, koja nije seed-ovana u test okruženju. Patch sprečava
    RuntimeError iz get_policy() i drži testove fokusirane na conflict-check logiku."""
    with patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        yield


def _user():
    return {"user_id": "bbbb0000-0000-0000-0000-000000000002", "email": "test@vindex.rs"}


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','gte','lte','order','limit','execute','is_','in_']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _make_supa(predmeti=None, klijenti=None, pred_klijenti=None):
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":    return _make_chain(predmeti or [])
        if name == "klijenti":    return _make_chain(klijenti or [])
        if name == "predmet_klijenti": return _make_chain(pred_klijenti or [])
        return _make_chain([])
    supa.table.side_effect = _table
    return supa


# ── T1: nema termina → clear ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_no_terms_returns_clear():
    from routers.conflict_check import ConflictReq, check_conflict
    req = ConflictReq(ime_prezime=None, firma=None, email=None)
    supa = _make_supa()
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert result["status"] == "clear"
    assert result["konflikti"] == []


# ── T2: poklapanje sa tužiocem u aktivnom predmetu → conflict ─────────────────

@pytest.mark.anyio
async def test_match_tuzilac_active_conflict():
    from routers.conflict_check import ConflictReq, check_conflict
    predmeti = [{"id": "p1", "naziv": "Naknada štete", "tip": "parnicno",
                 "status": "aktivan", "tuzilac": "Marko Marković", "tuzeni": "", "created_at": "2026-01-01"}]
    supa = _make_supa(predmeti=predmeti)
    req = ConflictReq(ime_prezime="Marko Marković")
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert result["status"] == "conflict"
    assert len(result["konflikti"]) >= 1
    assert result["konflikti"][0]["tip_konflikta"] == "tuzilac"


# ── T3: poklapanje sa tuženim → conflict ─────────────────────────────────────

@pytest.mark.anyio
async def test_match_tuzeni_active_conflict():
    from routers.conflict_check import ConflictReq, check_conflict
    predmeti = [{"id": "p2", "naziv": "Ugovorni spor", "tip": "privredno",
                 "status": "aktivan", "tuzilac": "", "tuzeni": "ABC doo", "created_at": "2026-02-01"}]
    supa = _make_supa(predmeti=predmeti)
    req = ConflictReq(firma="ABC doo")
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert result["status"] == "conflict"
    k = result["konflikti"][0]
    assert k["tip_konflikta"] == "tuzeni"
    assert "ABC" in k["opis"]


# ── T4: samo zatvoreni predmeti → review (ne blokirajući) ────────────────────

@pytest.mark.anyio
async def test_only_closed_predmeti_returns_review():
    from routers.conflict_check import ConflictReq, check_conflict
    predmeti = [{"id": "p3", "naziv": "Stari predmet", "tip": "radno",
                 "status": "zatvoren", "tuzilac": "Jovan Jovanović", "tuzeni": "", "created_at": "2024-01-01"}]
    supa = _make_supa(predmeti=predmeti)
    req = ConflictReq(ime_prezime="Jovan Jovanović")
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert result["status"] == "review"
    assert "zatvoren" in result["poruka"].lower() or "zatvorenih" in result["poruka"].lower()


# ── T5: potpuno različito ime → clear ────────────────────────────────────────

@pytest.mark.anyio
async def test_different_name_returns_clear():
    from routers.conflict_check import ConflictReq, check_conflict
    predmeti = [{"id": "p4", "naziv": "Predmet XYZ", "tip": "parnicno",
                 "status": "aktivan", "tuzilac": "Ana Anić", "tuzeni": "Firma doo", "created_at": "2026-01-01"}]
    supa = _make_supa(predmeti=predmeti)
    req = ConflictReq(ime_prezime="Petar Petrović", firma="Sasvim drugačija firma")
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert result["status"] == "clear"
    assert result["konflikti"] == []


# ── T6: prazan string → clear ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_empty_string_returns_clear():
    from routers.conflict_check import ConflictReq, check_conflict
    req = ConflictReq(ime_prezime="   ", firma="")
    supa = _make_supa()
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert result["status"] == "clear"


# ── T7: pretraga vraća listu prethodno proverenih termina ────────────────────

@pytest.mark.anyio
async def test_response_includes_pretraga_termini():
    from routers.conflict_check import ConflictReq, check_conflict
    req = ConflictReq(ime_prezime="Bojan Bojić", firma="Beta doo")
    supa = _make_supa()
    with patch("routers.conflict_check._get_supa", return_value=supa):
        result = await check_conflict(req, _user())
    assert "pretraga" in result
    assert "Bojan Bojić" in result["pretraga"]
    assert "Beta doo" in result["pretraga"]
