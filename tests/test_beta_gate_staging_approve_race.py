# -*- coding: utf-8 -*-
"""
Final Beta Gate — F16 (HIGH): routers/drafting.py::staging_approve had no
atomic claim on the staging_memory row before promoting it to Pinecone. A
double-click (frontend had no disabled-state guard either, also fixed this
mission) or slow-network retry let 2 concurrent requests both read
status='pending', both pass the confidence check, and both independently
call _promote_staged_draft_to_pinecone -- permanently ingesting 2 duplicate
vectors into the firm's real Pinecone knowledge base plus 2 duplicate
predmet_dokumenti rows, with no reaper ever detecting it.

Fix: the UPDATE that flips pending -> approved now happens FIRST, gated on
`.eq("status", "pending")` (the table's own DEFAULT/CHECK, migration 088).
Only the request that actually wins that atomic claim may promote; the loser
gets an "already processed" response instead of promoting a second time.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "POST", "path": "/api/staging/st1/approve", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(),
              "client": ("127.0.0.1", 1234)}
    return StarletteRequest(scope=scope)


class _StagingMemoryTable:
    """Minimal stateful fake for the ONE staging_memory row this test cares
    about -- real enough to prove the atomic claim actually gates on status,
    not a generic MagicMock chain (which can't express 'this UPDATE only
    applies WHERE status=pending')."""

    def __init__(self, row: dict):
        self._row = row
        self._op = None
        self._payload = None
        self._filters = {}

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def maybe_single(self):
        return self

    def execute(self):
        res = MagicMock()
        matches = all(self._row.get(k) == v for k, v in self._filters.items())
        if self._op == "select":
            res.data = dict(self._row) if matches else None
        elif self._op == "update":
            if matches:
                self._row.update(self._payload)
                res.data = [dict(self._row)]
            else:
                res.data = []  # claim lost -- status no longer matched the WHERE guard
        self._filters = {}
        return res


@pytest.mark.anyio
async def test_second_concurrent_approve_does_not_promote_again():
    from routers import drafting

    row = {
        "id": "st1", "user_id": "u1", "predmet_id": "p1", "tip": "podnesak",
        "naziv": "Nacrt", "tekst": "sadrzaj", "confidence_score": 0.95,
        "status": "pending", "pinecone_indexed": False,
    }
    table = _StagingMemoryTable(row)
    supa = MagicMock()
    supa.table.return_value = table

    promote_calls = {"n": 0}

    async def _fake_promote(supa, staged_row):
        promote_calls["n"] += 1
        return True

    with patch.object(drafting, "_get_supa", return_value=supa), \
         patch.object(drafting, "_promote_staged_draft_to_pinecone", new=_fake_promote):
        first = await drafting.staging_approve("st1", _req(), {"user_id": "u1"})
        second = await drafting.staging_approve("st1", _req(), {"user_id": "u1"})

    assert promote_calls["n"] == 1, "the losing concurrent request must NOT promote a second time"
    assert first["indexed"] is True
    assert second["poruka"] == "Ovaj nacrt je već obrađen (odobren ili odbijen)."
    assert row["status"] == "approved"


@pytest.mark.anyio
async def test_single_approve_still_promotes_and_persists_indexed_flag():
    from routers import drafting

    row = {
        "id": "st2", "user_id": "u1", "predmet_id": "p1", "tip": "podnesak",
        "naziv": "Nacrt", "tekst": "sadrzaj", "confidence_score": 0.95,
        "status": "pending", "pinecone_indexed": False,
    }
    table = _StagingMemoryTable(row)
    supa = MagicMock()
    supa.table.return_value = table

    async def _fake_promote(supa, staged_row):
        return True

    with patch.object(drafting, "_get_supa", return_value=supa), \
         patch.object(drafting, "_promote_staged_draft_to_pinecone", new=_fake_promote):
        result = await drafting.staging_approve("st2", _req(), {"user_id": "u1"})

    assert result == {"status": "approved", "indexed": True, "poruka": "Nacrt odobren i dodat u bazu znanja kancelarije."}
    assert row["status"] == "approved"
    assert row["pinecone_indexed"] is True


@pytest.mark.anyio
async def test_below_threshold_confidence_claims_row_but_does_not_promote():
    from routers import drafting

    row = {
        "id": "st3", "user_id": "u1", "predmet_id": "p1", "tip": "podnesak",
        "naziv": "Nacrt", "tekst": "sadrzaj", "confidence_score": 0.10,
        "status": "pending", "pinecone_indexed": False,
    }
    table = _StagingMemoryTable(row)
    supa = MagicMock()
    supa.table.return_value = table

    promote_calls = {"n": 0}

    async def _fake_promote(supa, staged_row):
        promote_calls["n"] += 1
        return True

    with patch.object(drafting, "_get_supa", return_value=supa), \
         patch.object(drafting, "_promote_staged_draft_to_pinecone", new=_fake_promote):
        result = await drafting.staging_approve("st3", _req(), {"user_id": "u1"})

    assert promote_calls["n"] == 0
    assert result["indexed"] is False
    assert row["status"] == "approved"  # still marked approved -- just not promoted
    assert row["pinecone_indexed"] is False
