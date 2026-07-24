# -*- coding: utf-8 -*-
"""
Regression tests — pagination on lista_predmeta (api.py) and list_klijenti
(klijenti/router.py).

NIGHTLY REPAIR (2026-07-24), Faza 3 item 8: both endpoints previously
fetched the caller's ENTIRE history with no .limit()/.range() -- fine at
small-firm scale, silently slower and slower as case/client history
grows, with no error or warning. Added optional limit/offset with a
generous default (200) that doesn't change behavior for any user under
that count. api.py::lista_predmeta ALSO had its main query running
synchronously inside an async def with no asyncio.to_thread wrapper (the
same bug class as Faza 1 item 2, found incidentally while touching this
exact line for pagination) -- fixed alongside.

Pure unit tests -- no live Supabase.
"""
import asyncio
import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402
import klijenti.router as klijenti_router  # noqa: E402
from klijenti.permissions import Role  # noqa: E402


def _req() -> MagicMock:
    from starlette.requests import Request as StarletteRequest

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "GET", "path": "/api/predmeti",
        "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _chain(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "neq", "order", "range", "or_"):
        setattr(m, method, MagicMock(return_value=m))
    m.execute = MagicMock(return_value=execute_return)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# api.py::lista_predmeta
# ═══════════════════════════════════════════════════════════════════════════

def test_lista_predmeta_applies_range_and_returns_total_count():
    fake_data = [{"id": f"p{i}"} for i in range(5)]
    chain = _chain(MagicMock(data=fake_data, count=137))
    supa = MagicMock()
    supa.table.return_value = chain

    user = types.SimpleNamespace(id="u1", email="a@b.com")
    with patch.object(api, "_require_auth", return_value=user), \
         patch.object(api, "_get_supa", return_value=supa):
        result = asyncio.run(api.lista_predmeta(_req(), authorization="Bearer faketoken", limit=50, offset=100))

    assert result["predmeti"] == fake_data
    assert result["ukupno"] == 137
    chain.range.assert_called_once_with(100, 149)


def test_lista_predmeta_default_limit_is_generous():
    chain = _chain(MagicMock(data=[], count=0))
    supa = MagicMock()
    supa.table.return_value = chain

    user = types.SimpleNamespace(id="u1", email="a@b.com")
    with patch.object(api, "_require_auth", return_value=user), \
         patch.object(api, "_get_supa", return_value=supa):
        asyncio.run(api.lista_predmeta(_req(), authorization="Bearer faketoken"))

    chain.range.assert_called_once_with(0, 199)


def test_lista_predmeta_limit_is_capped_at_500():
    chain = _chain(MagicMock(data=[], count=0))
    supa = MagicMock()
    supa.table.return_value = chain

    user = types.SimpleNamespace(id="u1", email="a@b.com")
    with patch.object(api, "_require_auth", return_value=user), \
         patch.object(api, "_get_supa", return_value=supa):
        asyncio.run(api.lista_predmeta(_req(), authorization="Bearer faketoken", limit=9999))

    called_start, called_end = chain.range.call_args[0]
    assert called_end - called_start + 1 == 500


# ═══════════════════════════════════════════════════════════════════════════
# klijenti/router.py::list_klijenti
# ═══════════════════════════════════════════════════════════════════════════

def test_list_klijenti_applies_range_and_returns_total_count():
    fake_data = [{"id": f"k{i}", "ime": "X", "prezime": "Y", "status": "aktivan"} for i in range(3)]
    chain = _chain(MagicMock(data=fake_data, count=42))
    supa = MagicMock()
    supa.table.return_value = chain

    fake_user = {"user_id": "u1", "role": Role.PARTNER}
    with patch.object(klijenti_router, "_auth_from_request", new=AsyncMock(return_value=fake_user)), \
         patch.object(klijenti_router, "_get_supa", return_value=supa):
        result = asyncio.run(klijenti_router.list_klijenti(_req(), limit=10, offset=20))

    assert result["ukupno"] == 42
    assert len(result["klijenti"]) == 3
    chain.range.assert_called_once_with(20, 29)


def test_list_klijenti_default_limit_is_generous():
    chain = _chain(MagicMock(data=[], count=0))
    supa = MagicMock()
    supa.table.return_value = chain

    fake_user = {"user_id": "u1", "role": Role.PARTNER}
    with patch.object(klijenti_router, "_auth_from_request", new=AsyncMock(return_value=fake_user)), \
         patch.object(klijenti_router, "_get_supa", return_value=supa):
        asyncio.run(klijenti_router.list_klijenti(_req()))

    chain.range.assert_called_once_with(0, 199)
