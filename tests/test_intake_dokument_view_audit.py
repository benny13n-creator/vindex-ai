# -*- coding: utf-8 -*-
"""
Program Intake Sprint 001 (2026-08-04) — regression test for the missing
'dokument_view' audit_immutable call at api.py::predmet_dokument_preview.

Fork 3 (storage/status/audit/provenance forensics) found 'dokument_view' and
'dokument_download' already registered in AUDITABLE_ACTIONS (shared/
audit_immutable.py) with UI labels already wired (routers/
intelligence_timeline.py) — the only missing piece was the actual
log_action() call site at the preview/download endpoint itself. This test
proves the call now happens on every successful preview.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest

import api


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    scope = {
        "type": "http", "method": "GET", "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-1/dokumenti/dok-1/preview", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope)


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "single", "execute"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


@pytest.mark.anyio
async def test_preview_logs_dokument_view_audit_action():
    row_data = {
        "id": "dok-1", "naziv_fajla": "tuzba.pdf", "pinecone_namespace": "user_1",
        "velicina_kb": 12, "status": "indeksirano", "created_at": "2026-08-04T00:00:00Z",
        "tekst_sadrzaj": "Sadržaj dokumenta.",
    }
    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain(row_data))

    with patch("api._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await api.predmet_dokument_preview(
            "pred-1", "dok-1", _fake_request(),
            user={"user_id": "user-1", "email": "advokat@vindex.rs"},
        )
        await asyncio.sleep(0)  # let the fire-and-forget create_task run

    assert result["dostupan"] is True
    mock_log.assert_awaited_once()
    call_kwargs = mock_log.call_args.kwargs
    assert mock_log.call_args.args[0] == "dokument_view"
    assert call_kwargs["user_id"] == "user-1"
    assert call_kwargs["resource_id"] == "dok-1"
    assert call_kwargs["metadata"]["predmet_id"] == "pred-1"


@pytest.mark.anyio
async def test_preview_404_does_not_log_audit_action():
    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain(None))

    with patch("api._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        with pytest.raises(Exception):
            await api.predmet_dokument_preview(
                "pred-1", "dok-missing", _fake_request(),
                user={"user_id": "user-1", "email": "advokat@vindex.rs"},
            )

    mock_log.assert_not_awaited()  # never viewed a real document — nothing to audit
