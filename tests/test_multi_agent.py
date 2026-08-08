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


@pytest.fixture(autouse=True)
def _mock_rag():
    """The research/litigation agents build a RAG context by calling
    app.services.retrieve.retrieve_documents (routers/multi_agent.py's "RAG
    kontekst za Research + Litigation agenta" block, and the equivalent in
    run_parallel). That is the full pipeline: real OpenAI embeddings, real
    Pinecone, real gpt-4o-mini query expansion. These tests mocked
    openai.OpenAI for the AGENT call but nothing for the retrieval call, so
    every `agent="research"` case here made billed requests.

    Returns the real (docs, meta) tuple contract with one plausible passage,
    so the rag_ctx block downstream is exercised with content rather than
    skipped. Nothing here asserts on retrieval — the assertions are on the
    agent id, the mocked LLM's answer, and the prompt's predmet context.
    """
    _docs = [
        "Zakon o obligacionim odnosima, Član 376: Potraživanje naknade "
        "prouzrokovane štete zastareva za tri godine od kada je oštećenik "
        "doznao za štetu i za lice koje je štetu učinilo."
    ]
    _meta = {
        "confidence": "HIGH", "top_score": 0.82,
        "top_article": "Član 376", "top_law": "zakon o obligacionim odnosima",
        "doc_passages": [], "praksa_matches": [],
    }
    with patch("app.services.retrieve.retrieve_documents", return_value=(_docs, _meta)):
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


# ── T8: NIGHTLY REPAIR (2026-07-24) — event loop liberation regression ──────
#
# routers/multi_agent.py had 7 supa.table(...).execute() calls inside async
# def functions with no asyncio.to_thread wrapper (run_agent + run_parallel),
# blocking the entire event loop on every DB round trip. This test populates
# predmet_dokumenti/rocista/case_dna/billing_entries with REAL (non-empty)
# data so every one of those 7 call sites is actually exercised end-to-end
# with meaningful content flowing into the LLM prompt -- T6 above only ever
# saw empty-list fallbacks for those tables, which would not have caught a
# broken lambda/asyncio.to_thread wiring.

@pytest.mark.anyio
async def test_run_agent_exercises_all_thread_wrapped_db_calls_with_real_data():
    from routers.multi_agent import AgentReq, run_agent

    pred_data = [{"naziv": "Radni spor", "tip": "radno", "status": "aktivan",
                  "tuzilac": "Petar", "tuzeni": "Firma", "opis": "Nezakonit otkaz",
                  "case_dna": {"snaga_predmeta_procent": 70}}]
    dok_data = [{"id": "d1", "naziv_fajla": "otkaz.pdf", "redni_broj": 1,
                 "tekst_sadrzaj": "Rešenje o otkazu ugovora o radu.", "velicina_kb": 120}]
    rok_data = [{"sud": "Prvi osnovni sud", "datum": "2026-08-01", "status": "zakazano", "napomena": ""}]
    billing_data = [{"opis": "Sastanak", "kolicina": 2, "jedinica": "h",
                      "cena_po_jedinici": 5000, "ukupno": 10000, "datum": "2026-07-20", "fakturisano": False}]

    def _table(name):
        return {
            "predmeti": _make_chain(pred_data),
            "predmet_dokumenti": _make_chain(dok_data),
            "rocista": _make_chain(rok_data),
            "billing_entries": _make_chain(billing_data),
        }.get(name, _make_chain([]))

    supa = MagicMock()
    supa.table.side_effect = _table
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_resp("Naplatiti 10.000 RSD.")

    req = AgentReq(agent="billing", task="Koliko naplatiti?", predmet_id="pred-001")
    with patch("routers.multi_agent._get_supa", return_value=supa), \
         patch("openai.OpenAI", return_value=mock_client):
        result = await run_agent(req, _req(), _user())

    assert result["agent"] == "billing"
    user_msg = mock_client.chat.completions.create.call_args[1]["messages"][1]["content"]
    assert "Radni spor" in user_msg
    assert "otkaz.pdf" in user_msg or "DOK-01" in user_msg
    assert "10.000" in user_msg or "10,000" in user_msg or "Nefakturisano" in user_msg


@pytest.mark.anyio
async def test_run_parallel_exercises_thread_wrapped_predmet_fetch():
    from routers.multi_agent import ParalelnaReq, run_parallel

    pred_data = [{"naziv": "Ugovorni spor", "tip": "gradjansko", "status": "aktivan",
                  "tuzilac": "ACME", "tuzeni": "Beta", "opis": "Neispunjenje ugovora"}]

    def _table(name):
        return _make_chain(pred_data) if name == "predmeti" else _make_chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    # agenti=["billing"] namerno izbegava RAG granu (research/litigation) --
    # ovaj test cilja isključivo predmet-context fetch (linija koju smo
    # obavili asyncio.to_thread-om), ne RAG pipeline.
    mock_async_client = MagicMock()
    mock_async_client.chat.completions.create = AsyncMock(return_value=_mock_openai_resp("Analiza gotova."))

    req = ParalelnaReq(agenti=["billing"], task="Analiziraj ugovor", predmet_id="pred-002")
    with patch("routers.multi_agent._get_supa", return_value=supa), \
         patch("openai.AsyncOpenAI", return_value=mock_async_client), \
         patch("shared.usage.UsageService.consume", new_callable=AsyncMock, return_value=10):
        result = await run_parallel(req, _req(), _user())

    assert "rezultati" in result
    assert result["rezultati"][0]["odgovor"] == "Analiza gotova."
