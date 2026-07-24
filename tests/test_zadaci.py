# -*- coding: utf-8 -*-
"""
Regression tests — routers/zadaci.py.

NIGHTLY REPAIR (2026-07-24), Faza 1 item 1: GET /api/zadaci/statistika
crashed for EVERY solo advokat (no kancelarija_id) with AttributeError,
because the "no team" fallback branch used asyncio.coroutine(...)(),
removed in Python 3.11. This is evaluated while building the tuple passed
to asyncio.gather(), so it failed before gather() even ran -- a guaranteed
crash, not a rare edge case, since solo practitioners are this project's
majority user base (v. project memory).

Pure unit tests -- no live Supabase.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routers.zadaci as zadaci  # noqa: E402


def _chain(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "in_", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    # .not_ is accessed as an attribute then called (q.not_.in_(...)) -- it
    # must be a distinct mock whose own methods return the chain `m`.
    not_mock = MagicMock()
    not_mock.in_ = MagicMock(return_value=m)
    m.not_ = not_mock
    m.execute = MagicMock(return_value=execute_return)
    return m


def test_statistika_solo_advokat_does_not_crash():
    """Regression for the exact reported bug: no kancelarija_id must not
    raise AttributeError building the gather() tuple."""
    moji_chain = _chain(MagicMock(data=[
        {"status": "otvoreno", "prioritet": "hitno", "rok_datum": "2020-01-01"},
    ]))
    supa = MagicMock()
    supa.table.return_value = moji_chain

    with patch.object(zadaci, "_get_firma_info", new=AsyncMock(return_value={"kancelarija_id": None})), \
         patch.object(zadaci, "_get_supa", return_value=supa):
        result = asyncio.run(zadaci.zadaci_statistika.__wrapped__(request=MagicMock(), user={"user_id": "u1"}))

    assert result["moji_zadaci"]["ukupno"] == 1
    assert result["moji_zadaci"]["hitnih"] == 1
    assert result["moji_zadaci"]["prekoracenih"] == 1
    assert result["tim_zadaci"] is None


def test_statistika_team_member_gets_both_datasets():
    moji_chain = _chain(MagicMock(data=[{"status": "otvoreno", "prioritet": "normalno", "rok_datum": "9999-01-01"}]))
    tim_chain = _chain(MagicMock(data=[
        {"status": "otvoreno", "prioritet": "hitno", "rok_datum": "9999-01-01", "dodeljen_uid": "u2"},
        {"status": "otvoreno", "prioritet": "hitno", "rok_datum": "9999-01-01", "dodeljen_uid": "u3"},
    ]))

    def _table(name):
        # both calls target "zadaci"; distinguish by call order via closure state
        _table.calls += 1
        return moji_chain if _table.calls == 1 else tim_chain
    _table.calls = 0

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(zadaci, "_get_firma_info", new=AsyncMock(return_value={"kancelarija_id": "firm1"})), \
         patch.object(zadaci, "_get_supa", return_value=supa):
        result = asyncio.run(zadaci.zadaci_statistika.__wrapped__(request=MagicMock(), user={"user_id": "u1"}))

    assert result["moji_zadaci"]["ukupno"] == 1
    assert result["tim_zadaci"]["ukupno"] == 2
    assert result["tim_zadaci"]["hitnih"] == 2


def test_statistika_empty_moji_zadaci_solo():
    empty_chain = _chain(MagicMock(data=[]))
    supa = MagicMock()
    supa.table.return_value = empty_chain

    with patch.object(zadaci, "_get_firma_info", new=AsyncMock(return_value={"kancelarija_id": None})), \
         patch.object(zadaci, "_get_supa", return_value=supa):
        result = asyncio.run(zadaci.zadaci_statistika.__wrapped__(request=MagicMock(), user={"user_id": "u1"}))

    assert result["moji_zadaci"]["ukupno"] == 0
    assert result["tim_zadaci"] is None
