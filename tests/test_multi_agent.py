# -*- coding: utf-8 -*-
"""
Tests for /api/agents — Multi-Agent Orchestration.
OpenAI calls are mocked throughout.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from starlette.requests import Request as StarletteRequest

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _mock_usage_service():
    """Testi zovu route funkcije direktno (bez FastAPI Depends), pa endpoint-ovo
    await UsageService.consume(...) u telu funkcije izvršava se stvarno protiv
    feature_registry, koja nije seed-ovana u test okruženju. Patch sprečava
    RuntimeError iz get_policy() i drži testove fokusirane na multi-agent logiku."""
    with patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        yield


def _user():
    return {"user_id": "dddd0000-0000-0000-0000-000000000004", "email": "test@vindex.rs"}


def _req():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
              "path": "/api/agents/run", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','order','limit','execute','is_','in_']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _mock_openai_resp(text="Odgovor AI agenta."):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


# ── T1: GET /lista vraća 6 agenata ────────────────────────────────────────────

@pytest.mark.anyio
async def test_lista_returns_6_agents():
    from routers.multi_agent import lista_agenata
    result = await lista_agenata()
    assert "agenti" in result
    assert len(result["agenti"]) == 6
    ids = {a["id"] for a in result["agenti"]}
    assert ids == {"intake","research","drafting","litigation","billing","deadline"}


# ── T2: svaki agent ima obavezna polja ───────────────────────────────────────

@pytest.mark.anyio
async def test_lista_agent_fields():
    from routers.multi_agent import lista_agenata
    result = await lista_agenata()
    for agent in result["agenti"]:
        assert "id"    in agent
        assert "naziv" in agent
        assert "ikona" in agent
        assert "opis"  in agent


# ── T3: run_agent sa poznatim agentom vraća odgovor ──────────────────────────

@pytest.mark.anyio
async def test_run_agent_known():
    from routers.multi_agent import AgentReq, run_agent
    req = AgentReq(agent="research", task="Koji je rok zastarelosti za naknadu štete?")
    supa = MagicMock()
    supa.table.return_value = _make_chain([])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_resp("Zastarelost je 3 godine.")
    with patch("routers.multi_agent._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await run_agent(req, _req(), _user())
    assert result["agent"]  == "research"
    assert result["odgovor"] == "Zastarelost je 3 godine."
    assert result["task"]   == "Koji je rok zastarelosti za naknadu štete?"


# ── T4: nepoznat agent → HTTP 400 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_run_agent_unknown_raises_400():
    from fastapi import HTTPException
    from routers.multi_agent import AgentReq, run_agent
    req = AgentReq(agent="nepostojeci", task="Test")
    supa = MagicMock(); supa.table.return_value = _make_chain([])
    with patch("routers.multi_agent._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await run_agent(req, _req(), _user())
    assert exc.value.status_code == 400


# ── T5: auto-selekcija agenta kad agent=None ──────────────────────────────────

@pytest.mark.anyio
async def test_run_agent_auto_select():
    from routers.multi_agent import AgentReq, run_agent
    req = AgentReq(agent=None, task="Generiši tužbu za naknadu štete")
    supa = MagicMock(); supa.table.return_value = _make_chain([])

    # Router GPT vraća {"agent": "drafting"}
    router_resp = MagicMock()
    router_resp.choices = [MagicMock()]
    router_resp.choices[0].message.content = '{"agent": "drafting", "razlog": "generisanje dokumenta"}'

    # Agent GPT vraća odgovor
    agent_resp = MagicMock()
    agent_resp.choices = [MagicMock()]
    agent_resp.choices[0].message.content = "Tužba je generisana."

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [router_resp, agent_resp]

    with patch("routers.multi_agent._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await run_agent(req, _req(), _user())

    assert result["agent"] == "drafting"
    assert result["odgovor"] == "Tužba je generisana."


# ── T6: run sa predmet_id dohvata kontekst ───────────────────────────────────

@pytest.mark.anyio
async def test_run_agent_with_predmet_context():
    from routers.multi_agent import AgentReq, run_agent
    pred_data = [{"naziv": "Radni spor", "tip": "radno", "status": "aktivan",
                  "tuzilac": "Petar", "tuzeni": "Firma", "opis": "Nezakonit otkaz"}]
    req = AgentReq(agent="billing", task="Koliko naplatiti?", predmet_id="pred-001")
    supa = MagicMock()
    supa.table.side_effect = lambda name: _make_chain(pred_data) if name == "predmeti" else _make_chain([])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_resp("Naplatiti 30.000 RSD.")
    with patch("routers.multi_agent._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await run_agent(req, _req(), _user())
    assert result["agent"] == "billing"
    # Proveri da je predmet kontekst prosleđen GPT-u
    call_args = mock_client.chat.completions.create.call_args
    user_msg = call_args[1]["messages"][1]["content"]
    assert "Radni spor" in user_msg or "radno" in user_msg


# ── T7: OpenAI nedostupan → HTTP 503 ─────────────────────────────────────────

@pytest.mark.anyio
async def test_run_agent_openai_error_503():
    from fastapi import HTTPException
    from routers.multi_agent import AgentReq, run_agent
    req = AgentReq(agent="research", task="Test")
    supa = MagicMock(); supa.table.return_value = _make_chain([])
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Connection timeout")
    with patch("routers.multi_agent._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(HTTPException) as exc:
            await run_agent(req, _req(), _user())
    assert exc.value.status_code == 503
