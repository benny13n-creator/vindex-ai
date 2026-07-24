# -*- coding: utf-8 -*-
"""
Regression tests — routers/billing.py::timer_start (TOCTOU race).

NIGHTLY REPAIR (2026-07-24), Faza 1 item 4: timer_start did a SELECT
(is there an active timer?) followed by a separate INSERT, with no
transactional isolation -- two fast clicks (or two open tabs) could both
pass the SELECT check before either INSERT committed, silently creating
two simultaneous active timers for the same user and corrupting billed
hours. Same bug class as the audit_immutable TOCTOU race found and fixed
in this codebase this session (migration 081) -- same fix pattern:
migration 084 adds a partial UNIQUE index; the code below now catches the
resulting 23505 conflict and returns a clean 409 instead of letting a
duplicate slip through OR crashing with an unhandled DB error.

Pure unit tests -- no live Supabase.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request as StarletteRequest  # noqa: E402
import routers.billing as billing  # noqa: E402


def _req() -> StarletteRequest:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": "/billing/timer/start",
        "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _chain(execute_return=None, execute_side_effect=None):
    m = MagicMock()
    for method in ("select", "eq", "insert", "update", "limit"):
        setattr(m, method, MagicMock(return_value=m))
    if execute_side_effect is not None:
        m.execute = MagicMock(side_effect=execute_side_effect)
    else:
        m.execute = MagicMock(return_value=execute_return)
    return m


def test_timer_start_no_existing_active_timer_succeeds():
    select_chain = _chain(MagicMock(data=[]))
    insert_chain = _chain(MagicMock(data=[{"id": "t1", "aktivan": True}]))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return select_chain if call_count["n"] == 1 else insert_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    req = billing.TimerStartReq(predmet_id="p1")
    with patch.object(billing, "_get_supa", return_value=supa):
        result = asyncio.run(billing.timer_start(req, _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert result["success"] is True
    assert result["timer"]["id"] == "t1"


def test_timer_start_existing_recent_active_timer_returns_409():
    recent = datetime.now(timezone.utc).isoformat()
    select_chain = _chain(MagicMock(data=[{"id": "t0", "predmet_id": "p1", "start_at": recent}]))
    supa = MagicMock()
    supa.table.return_value = select_chain

    req = billing.TimerStartReq(predmet_id="p1")
    with patch.object(billing, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(billing.timer_start(req, _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert exc_info.value.status_code == 409


def test_timer_start_race_conflict_on_insert_returns_409_not_500():
    """Regression for the actual TOCTOU race: SELECT sees no active timer
    (a concurrent request hasn't committed yet), but the INSERT hits the
    migration-084 unique-index conflict -- must become a clean 409, not an
    unhandled 500 or a silently-succeeding duplicate."""
    select_chain = _chain(MagicMock(data=[]))
    conflict_error = Exception('duplicate key value violates unique constraint "timer_sessions_one_active_per_user" 23505')
    insert_chain = _chain(execute_side_effect=conflict_error)

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return select_chain if call_count["n"] == 1 else insert_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    req = billing.TimerStartReq(predmet_id="p1")
    with patch.object(billing, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(billing.timer_start(req, _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert exc_info.value.status_code == 409


def test_timer_start_unrelated_db_error_still_propagates():
    select_chain = _chain(MagicMock(data=[]))
    insert_chain = _chain(execute_side_effect=RuntimeError("connection reset"))

    call_count = {"n": 0}
    def _table(name):
        call_count["n"] += 1
        return select_chain if call_count["n"] == 1 else insert_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    req = billing.TimerStartReq(predmet_id="p1")
    with patch.object(billing, "_get_supa", return_value=supa):
        with pytest.raises(RuntimeError):
            asyncio.run(billing.timer_start(req, _req(), {"user_id": "u1", "email": "a@b.com"}))
