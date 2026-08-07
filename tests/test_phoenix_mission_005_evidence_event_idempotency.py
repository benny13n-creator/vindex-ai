# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 005 -- Evidence & Event Idempotency.
Closes LIVINGSYS-DEBT-010, -043.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "POST", "path": "/", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(),
              "client": ("127.0.0.1", 1234)}
    return StarletteRequest(scope=scope)


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-010 — Smart Intake's review resolve/reject HTTP endpoints
# emitted a durable event unconditionally, even on a genuine retry that
# changed nothing.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_job_review_skips_event_emission_on_retry():
    import routers.smart_intake as si

    job_row = {"id": "job-1", "status": "awaiting_review", "predmet_id": None}

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = job_row
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(si, "_get_supa", return_value=supa), \
         patch.object(si.intake_documents, "resolve_review", new=AsyncMock(
             return_value={"review_resolved_now": False, "job_status_advanced": False})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await si.resolve_job_review("job-1", _req(), {"user_id": "u1", "email": "a@b.com"})

    mock_emit.assert_not_awaited()
    assert result["ok"] is True
    assert result["review_resolved_now"] is False


@pytest.mark.anyio
async def test_resolve_job_review_emits_event_on_genuine_resolution():
    import routers.smart_intake as si

    job_row = {"id": "job-1", "status": "awaiting_review", "predmet_id": None}

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = job_row
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(si, "_get_supa", return_value=supa), \
         patch.object(si.intake_documents, "resolve_review", new=AsyncMock(
             return_value={"review_resolved_now": True, "job_status_advanced": True})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await si.resolve_job_review("job-1", _req(), {"user_id": "u1", "email": "a@b.com"})

    mock_emit.assert_awaited_once()
    assert result["review_resolved_now"] is True


@pytest.mark.anyio
async def test_reject_job_review_skips_event_emission_on_retry():
    import routers.smart_intake as si

    job_row = {"id": "job-1", "status": "awaiting_review", "predmet_id": None}

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = job_row
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(si, "_get_supa", return_value=supa), \
         patch.object(si.intake_documents, "reject_review", new=AsyncMock(
             return_value={"review_resolved_now": False, "job_status_rejected": False})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await si.reject_job_review("job-1", _req(), {"user_id": "u1", "email": "a@b.com"})

    mock_emit.assert_not_awaited()
    assert result["ok"] is True


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-043 — POST /api/rocista had no idempotency check, cascading
# into duplicate ROCISTE_ZAKAZANO on a client retry.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kreiraj_rociste_returns_existing_row_on_immediate_retry():
    from routers.rocista import RocisteReq, kreiraj_rociste

    existing_row = {
        "id": "rociste-1", "predmet_id": "pred-1", "sud": "Viši sud u Beogradu",
        "datum": "2026-09-20", "vreme": "10:00", "status": "zakazano",
        "sudnica": None, "broj_predmeta_suda": None, "napomena": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "pred-1"}]
        elif name == "rocista":
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value.data = [existing_row]
            def _insert(payload):
                insert_calls.append(payload)
                m = MagicMock(); m.execute.return_value = MagicMock(data=[payload])
                return m
            t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    body = RocisteReq(predmet_id="pred-1", sud="Viši sud u Beogradu", datum="2026-09-20", vreme="10:00")

    with patch("routers.rocista._get_supa", return_value=supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await kreiraj_rociste(body, _req(), {"user_id": "u1"})

    assert insert_calls == []  # no new row created
    mock_emit.assert_not_awaited()  # no duplicate event
    assert result["rociste"]["id"] == "rociste-1"


@pytest.mark.anyio
async def test_kreiraj_rociste_creates_new_row_when_no_recent_duplicate():
    from routers.rocista import RocisteReq, kreiraj_rociste

    new_row = {
        "id": "rociste-new", "predmet_id": "pred-1", "sud": "Viši sud u Beogradu",
        "datum": "2026-09-20", "vreme": "10:00:00", "status": "zakazano",
        "sudnica": None, "broj_predmeta_suda": None, "napomena": None,
    }

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "pred-1"}]
        elif name == "rocista":
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [new_row]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    body = RocisteReq(predmet_id="pred-1", sud="Viši sud u Beogradu", datum="2026-09-20", vreme="10:00")

    with patch("routers.rocista._get_supa", return_value=supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await kreiraj_rociste(body, _req(), {"user_id": "u1"})

    assert result["rociste"]["id"] == "rociste-new"
    mock_emit.assert_awaited_once()
