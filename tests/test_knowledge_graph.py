# -*- coding: utf-8 -*-
"""
Tests for GET /api/knowledge-graph/predmeti/{predmet_id} — Knowledge Graph.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _user():
    return {"user_id": "ffff0000-0000-0000-0000-000000000006", "email": "test@vindex.rs"}


def _req():
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
             "path": "/api/knowledge-graph/predmeti/x", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


PID = "pred-kg-0001"


def _make_chain(data):
    c = MagicMock()
    for a in ['select','eq','neq','order','limit','execute','is_','in_']:
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


_PRED = {"id": PID, "naziv": "Ugovorni spor", "tip": "privredno",
         "status": "aktivan", "tuzilac": "Firma A", "tuzeni": "Firma B"}


def _make_supa(predmet, klijenti=None, dokumenti=None, rokovi=None, hron=None):
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":         return _make_chain([predmet])
        if name == "predmet_klijenti": return _make_chain(klijenti or [])
        if name == "predmet_dokumenti":return _make_chain(dokumenti or [])
        if name == "predmet_rokovi":   return _make_chain(rokovi or [])
        if name == "predmet_hronologija": return _make_chain(hron or [])
        return _make_chain([])
    supa.table.side_effect = _table
    return supa


# ── T1: osnovna struktura odgovora ────────────────────────────────────────────

@pytest.mark.anyio
async def test_kg_response_structure():
    from routers.knowledge_graph import get_knowledge_graph
    supa = _make_supa(_PRED)
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        result = await get_knowledge_graph(PID, _req(), _user())
    assert "nodes" in result
    assert "edges" in result
    assert isinstance(result["nodes"], list)
    assert isinstance(result["edges"], list)


# ── T2: predmet node uvek postoji ────────────────────────────────────────────

@pytest.mark.anyio
async def test_kg_predmet_node_exists():
    from routers.knowledge_graph import get_knowledge_graph
    supa = _make_supa(_PRED)
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        result = await get_knowledge_graph(PID, _req(), _user())
    # Nodes koriste "tip" (ne "type") kao ključ
    pred_nodes = [n for n in result["nodes"] if n.get("tip") == "predmet"]
    assert len(pred_nodes) == 1
    assert pred_nodes[0]["label"] == "Ugovorni spor"


# ── T3: dokument nodovi se dodaju ────────────────────────────────────────────

@pytest.mark.anyio
async def test_kg_document_nodes():
    from routers.knowledge_graph import get_knowledge_graph
    dokumenti = [
        {"id": "d1", "naziv_fajla": "Ugovor o saradnji", "tip_dokaza": "ugovor", "deleted_at": None},
        {"id": "d2", "naziv_fajla": "Dopis klijentu",    "tip_dokaza": "dopis",  "deleted_at": None},
    ]
    supa = _make_supa(_PRED, dokumenti=dokumenti)
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        result = await get_knowledge_graph(PID, _req(), _user())
    dok_nodes = [n for n in result["nodes"] if n.get("tip") == "dokument"]
    assert len(dok_nodes) == 2


# ── T4: rokovi nodovi se dodaju ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_kg_rok_nodes():
    from routers.knowledge_graph import get_knowledge_graph
    rokovi = [
        {"id": "r1", "naziv": "Rok za odgovor", "datum_isteka": "2026-07-01", "status": "aktivan"},
        {"id": "r2", "naziv": "Rok za žalbu",   "datum_isteka": "2026-08-15", "status": "aktivan"},
    ]
    supa = _make_supa(_PRED, rokovi=rokovi)
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        result = await get_knowledge_graph(PID, _req(), _user())
    rok_nodes = [n for n in result["nodes"] if n.get("tip") == "rok"]
    assert len(rok_nodes) == 2


# ── T5: edge postoji između predmeta i dokumenta ─────────────────────────────

@pytest.mark.anyio
async def test_kg_predmet_doc_edge():
    from routers.knowledge_graph import get_knowledge_graph
    # Edges koriste "from"/"to" ključeve
    dokumenti = [{"id": "d1", "naziv_fajla": "Ugovor", "tip_dokaza": "ugovor", "deleted_at": None}]
    supa = _make_supa(_PRED, dokumenti=dokumenti)
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        result = await get_knowledge_graph(PID, _req(), _user())
    edges = result["edges"]
    pred_node_id = f"predmet_{PID}"
    connected = any(
        (e.get("from") == pred_node_id and "dok_d1" in e.get("to",""))
        for e in edges
    )
    assert connected, "Nema edge između predmeta i dokumenta"


# ── T6: 404 za tuđi predmet ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_kg_404_wrong_user():
    from fastapi import HTTPException
    from routers.knowledge_graph import get_knowledge_graph
    supa = MagicMock()
    supa.table.return_value = _make_chain([])
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await get_knowledge_graph("ghost-id", _req(), _user())
    assert exc.value.status_code == 404


# ── T7: prazan predmet → samo 1 node (predmet), 0 edges ──────────────────────

@pytest.mark.anyio
async def test_kg_empty_predmet_single_node():
    from routers.knowledge_graph import get_knowledge_graph
    supa = _make_supa(_PRED)
    with patch("routers.knowledge_graph._get_supa", return_value=supa):
        result = await get_knowledge_graph(PID, _req(), _user())
    # Uvek: 1 predmet + 1 zakon node (tip se mapira na zakon) + klijent nodovi iz tuzilac/tuzeni
    pred_nodes = [n for n in result["nodes"] if n.get("tip") == "predmet"]
    assert len(pred_nodes) == 1
    assert "predmet_naziv" in result
