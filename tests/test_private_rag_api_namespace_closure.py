# -*- coding: utf-8 -*-
"""Authenticated question routes must use the common matter-ACL retrieval path."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-no-network")
os.environ.setdefault("SUPABASE_URL", "https://synthetic.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "synthetic-test-key")
import api


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _request(path):
    from starlette.requests import Request
    return Request({
        "type": "http", "method": "POST", "path": path,
        "headers": [], "query_string": b"", "scheme": "http",
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
    })


def _allow_guard():
    return SimpleNamespace(blocked=False, risk_score=0.0, flags=[])


@pytest.mark.anyio
async def test_standard_question_route_does_not_forward_legacy_office_namespace():
    captured = {}

    async def run_agent(fn, *args, **kwargs):
        captured["args"] = args
        return {"status": "success", "data": "Bezbedan sintetički odgovor", "confidence": "LOW"}

    fake_ns = AsyncMock(return_value="firm-private-office")
    with patch("api._get_firma_namespace", fake_ns), \
         patch("api.pokreni", run_agent), \
         patch("api.UsageService.consume", new=AsyncMock(return_value=9)), \
         patch("api.UsageService.refund", new=AsyncMock()), \
         patch("api._audit", new=AsyncMock()), \
         patch("api.log_cost_to_db", new=AsyncMock()), \
         patch("api._fetch_firm_memory_context", new=AsyncMock(return_value="")), \
         patch("api.begin_cost_tracking"), \
         patch("api.klasifikuj_pitanje", return_value="opste"), \
         patch("security.prompt_guard.analyze", return_value=_allow_guard()), \
         patch("security.prompt_guard.truncate_safe", side_effect=lambda s: s):
        result = await api.pitanje(
            api.PitanjeReq(pitanje="Test privatnog RAG opsega?"),
            _request("/api/pitanje"),
            {"user_id": "synthetic-c", "email": "synthetic@example.invalid"},
        )

    assert result["odgovor"] == "Bezbedan sintetički odgovor"
    assert captured["args"][2] is None  # args: question, history, extra_namespaces, memory
    fake_ns.assert_not_awaited()


@pytest.mark.anyio
async def test_stream_question_route_does_not_forward_legacy_office_namespace():
    captured = {}

    async def run_agent(fn, *args, **kwargs):
        captured["args"] = args
        return {"status": "success", "data": "Bezbedan sintetički streaming odgovor", "confidence": "LOW"}

    fake_ns = AsyncMock(return_value="firm-private-office")
    with patch("api._get_firma_namespace", fake_ns), \
         patch("api.pokreni", run_agent), \
         patch("api.UsageService.consume", new=AsyncMock(return_value=9)), \
         patch("api.UsageService.refund", new=AsyncMock()), \
         patch("api.UsageService.balance", new=AsyncMock(return_value=9)), \
         patch("api._audit", new=AsyncMock()), \
         patch("api._fetch_firm_memory_context", new=AsyncMock(return_value="")), \
         patch("api.begin_cost_tracking", create=True), \
         patch("api.klasifikuj_pitanje", return_value="opste"), \
         patch("security.prompt_guard.analyze", return_value=_allow_guard()):
        response = await api.pitanje_stream(
            api.PitanjeReq(pitanje="Test privatnog RAG opsega?"),
            _request("/api/pitanje/stream"),
            {"user_id": "synthetic-c", "email": "synthetic@example.invalid"},
        )
        chunks = [chunk async for chunk in response.body_iterator]

    assert any("Bezbedan sintetički streaming odgovor" in chunk for chunk in chunks)
    assert captured["args"][2] is None  # args: question, history, extra_namespaces, memory
    fake_ns.assert_not_awaited()
