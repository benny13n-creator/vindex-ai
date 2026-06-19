# -*- coding: utf-8 -*-
"""
Tests for GET /api/outcome-intel/predmeti/{predmet_id} — Outcome Intelligence.
OpenAI calls mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _user():
    return {"user_id": "eeee0000-0000-0000-0000-000000000005", "email": "test@vindex.rs"}


PID = "pred-oi-0001"


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','order','limit','execute','is_','in_']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _mock_gpt(text):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


_PRED = {"id": PID, "naziv": "Radni spor", "tip": "radno", "status": "aktivan", "opis": None}

# ── T1: samo jedan predmet tog tipa → poruka bez istorije ────────────────────

@pytest.mark.anyio
async def test_single_predmet_no_history():
    from routers.outcome_intel import get_outcome_intel
    supa = MagicMock()
    supa.table.return_value = _make_chain([_PRED])
    with patch("routers.outcome_intel._get_supa", return_value=supa):
        result = await get_outcome_intel(PID, _user())
    assert result["ukupno_predmeta"] == 1
    assert "nije" in result["analiza"].lower() or "nema" in result["analiza"].lower() or "jedan" in result["analiza"].lower()


# ── T2: sa istorijom → poziva GPT i vraća analizu ────────────────────────────

@pytest.mark.anyio
async def test_with_history_calls_gpt():
    from routers.outcome_intel import get_outcome_intel
    predmeti = [
        _PRED,
        {"id": "p2", "naziv": "Radni spor 2", "tip": "radno", "status": "zatvoren", "opis": None},
        {"id": "p3", "naziv": "Radni spor 3", "tip": "radno", "status": "uspesno", "opis": None},
    ]
    supa = MagicMock()
    def _table(name):
        if name == "predmeti": return _make_chain(predmeti)
        if name == "predmet_dokumenti": return _make_chain([{"tip_dokaza": "ugovor"}])
        if name == "billing_entries": return _make_chain([{"iznos": 50000}])
        return _make_chain([])
    supa.table.side_effect = _table
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_gpt("📊 STATISTIKA\nTest analiza.")
    with patch("routers.outcome_intel._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await get_outcome_intel(PID, _user())
    assert result["ukupno_predmeta"] == 3
    assert result["zatvoreni"] == 2
    assert "STATISTIKA" in result["analiza"] or "Test" in result["analiza"]


# ── T3: struktura odgovora ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_response_structure():
    from routers.outcome_intel import get_outcome_intel
    # Sa 1 predmetom → skraćeni response
    supa = MagicMock()
    supa.table.return_value = _make_chain([_PRED])
    with patch("routers.outcome_intel._get_supa", return_value=supa):
        result = await get_outcome_intel(PID, _user())
    for key in ["analiza", "ukupno_predmeta", "tip"]:
        assert key in result, f"Nedostaje ključ: {key}"


# ── T4: GPT greška → fallback tekst (ne crash) ───────────────────────────────

@pytest.mark.anyio
async def test_gpt_error_fallback():
    from routers.outcome_intel import get_outcome_intel
    predmeti = [_PRED,
                {"id": "p5", "naziv": "Drugi", "tip": "radno", "status": "zatvoren", "opis": None}]
    supa = MagicMock()
    def _table(name):
        if name in ("predmeti",): return _make_chain(predmeti)
        return _make_chain([])
    supa.table.side_effect = _table
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    with patch("routers.outcome_intel._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await get_outcome_intel(PID, _user())
    # Ne sme da baci exception — mora da vrati fallback
    assert "analiza" in result
    assert len(result["analiza"]) > 10


# ── T5: 404 na nepoznat predmet ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_404_unknown_predmet():
    from fastapi import HTTPException
    from routers.outcome_intel import get_outcome_intel
    supa = MagicMock()
    supa.table.return_value = _make_chain([])
    with patch("routers.outcome_intel._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await get_outcome_intel("ghost-id", _user())
    assert exc.value.status_code == 404


# ── T6: avg_vrednost se ispravno računa ──────────────────────────────────────

@pytest.mark.anyio
async def test_avg_vrednost_calculation():
    from routers.outcome_intel import get_outcome_intel
    predmeti = [_PRED,
                {"id": "p6", "naziv": "Drugi", "tip": "radno", "status": "zatvoren", "opis": None}]
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":        return _make_chain(predmeti)
        if name == "predmet_dokumenti": return _make_chain([])
        if name == "billing_entries":   return _make_chain([{"iznos": 60000}, {"iznos": 40000}])
        return _make_chain([])
    supa.table.side_effect = _table
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_gpt("📊 Test")
    with patch("routers.outcome_intel._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await get_outcome_intel(PID, _user())
    assert result["avg_vrednost"] == 100000
