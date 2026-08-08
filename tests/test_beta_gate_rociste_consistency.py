# -*- coding: utf-8 -*-
"""
Final Beta Gate — F17/F26/F27: routers/rocista.py's PATCH endpoint
(izmeni_rociste) had neither an optimistic-concurrency guard (unlike its
direct siblings api.py::update_predmet and zadaci.py::azuriraj_status) nor
any downstream event emission on reschedule (unlike hearing CREATION, which
emits ROCISTE_ZAKAZANO -> genome_refresh/refresh_case_actions/
project_notifications). Dashboard (reads `rocista` live) and Workspace
(reads `case_actions`, only updated by those 3 consequences) could disagree
about the SAME hearing after a reschedule. Separately, lista_rocista (the
Calendar view's own endpoint) never filtered by predmeti.status.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/rocista", method="POST"):
    scope = {
        "type": "http", "method": method, "headers": [],
        "query_string": b"", "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaaaaaa-0000-0000-0000-000000000001", "email": "test@vindex.rs", "role": "advokat"}


def _supa_ok(data):
    supa = MagicMock()
    result = MagicMock()
    result.data = data
    chain = MagicMock()
    chain.execute.return_value = result
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.offset.return_value = chain
    chain.in_.return_value = chain
    chain.not_.in_.return_value = chain
    supa.table.return_value.select.return_value = chain
    supa.table.return_value.insert.return_value = chain
    supa.table.return_value.update.return_value = chain
    supa.table.return_value.delete.return_value = chain
    return supa


# ─── F17: optimistic-concurrency guard ─────────────────────────────────────

@pytest.mark.anyio
async def test_izmeni_rociste_without_if_updated_at_is_unconditional_as_before():
    """Backward-compat: a caller not sending if_updated_at must behave
    exactly as before -- no regression for the existing frontend."""
    from routers.rocista import RocistePatchReq, izmeni_rociste

    updated_row = {"id": "r1", "status": "odrzano", "sud": "Sud C", "datum": "2026-07-01", "vreme": None, "predmet_id": "p1"}
    supa = _supa_ok([updated_row])
    body = RocistePatchReq(sudnica="Sala 3")  # not a "materially changed" field

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    assert result["ok"] is True


@pytest.mark.anyio
async def test_izmeni_rociste_stale_if_updated_at_rejects_with_409():
    from routers.rocista import RocistePatchReq, izmeni_rociste
    from fastapi import HTTPException

    supa = MagicMock()
    update_result = MagicMock(data=[])  # precondition didn't match -> 0 rows
    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = update_result

    exists_result = MagicMock(data={"id": "r1"})  # row DOES exist, just changed
    select_chain = MagicMock()
    select_chain.eq.return_value = select_chain
    select_chain.maybe_single.return_value = select_chain
    select_chain.execute.return_value = exists_result

    supa.table.return_value.update.return_value = update_chain
    supa.table.return_value.select.return_value = select_chain

    body = RocistePatchReq(status="odrzano", if_updated_at="2026-01-01T00:00:00+00:00")

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_izmeni_rociste_stale_if_updated_at_on_missing_row_is_404_not_409():
    from routers.rocista import RocistePatchReq, izmeni_rociste
    from fastapi import HTTPException

    supa = MagicMock()
    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = MagicMock(data=[])

    select_chain = MagicMock()
    select_chain.eq.return_value = select_chain
    select_chain.maybe_single.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=None)  # row genuinely doesn't exist/isn't owned

    supa.table.return_value.update.return_value = update_chain
    supa.table.return_value.select.return_value = select_chain

    body = RocistePatchReq(status="odrzano", if_updated_at="2026-01-01T00:00:00+00:00")

    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await izmeni_rociste("does-not-exist", body, _req(method="PATCH"), _user())

    assert exc.value.status_code == 404


# ─── F26: downstream event on material changes ─────────────────────────────

@pytest.mark.anyio
async def test_izmeni_rociste_reschedule_emits_rociste_event():
    from routers.rocista import RocistePatchReq, izmeni_rociste

    updated_row = {"id": "r1", "status": "zakazano", "sud": "Sud C", "datum": "2026-09-01", "vreme": "10:00", "predmet_id": "p1"}
    supa = _supa_ok([updated_row])
    body = RocistePatchReq(datum="2026-09-01")  # reschedule

    with patch("routers.rocista._get_supa", return_value=supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    mock_emit.assert_called_once()
    from services.event_bus import EventType
    assert mock_emit.call_args.args[0] == EventType.ROCISTE_ZAKAZANO
    assert mock_emit.call_args.args[2] == "p1"
    assert mock_emit.call_args.args[3]["trigger"] == "rociste_updated"


@pytest.mark.anyio
async def test_izmeni_rociste_cosmetic_edit_does_not_emit_event():
    """Editing sudnica/napomena/broj_predmeta_suda doesn't change readiness/
    risk/deadlines -- must not spend a GPT-backed genome refresh on it."""
    from routers.rocista import RocistePatchReq, izmeni_rociste

    updated_row = {"id": "r1", "status": "zakazano", "sud": "Sud C", "datum": "2026-07-01", "vreme": None, "predmet_id": "p1", "sudnica": "Sala 5"}
    supa = _supa_ok([updated_row])
    body = RocistePatchReq(sudnica="Sala 5")

    with patch("routers.rocista._get_supa", return_value=supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    mock_emit.assert_not_called()


@pytest.mark.anyio
async def test_izmeni_rociste_status_change_emits_event():
    from routers.rocista import RocistePatchReq, izmeni_rociste

    updated_row = {"id": "r1", "status": "odrzano", "sud": "Sud C", "datum": "2026-07-01", "vreme": None, "predmet_id": "p1"}
    supa = _supa_ok([updated_row])
    body = RocistePatchReq(status="odrzano")

    with patch("routers.rocista._get_supa", return_value=supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    mock_emit.assert_called_once()


@pytest.mark.anyio
async def test_izmeni_rociste_event_emission_failure_does_not_break_response():
    """emit_durable failing (e.g. a transient DB hiccup) must not turn a
    successful reschedule into a 500 -- same fail-soft shape as
    kreiraj_rociste's own ROCISTE_ZAKAZANO emission a few lines up."""
    from routers.rocista import RocistePatchReq, izmeni_rociste

    updated_row = {"id": "r1", "status": "zakazano", "sud": "Sud C", "datum": "2026-09-01", "vreme": None, "predmet_id": "p1"}
    supa = _supa_ok([updated_row])
    body = RocistePatchReq(datum="2026-09-01")

    with patch("routers.rocista._get_supa", return_value=supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock(side_effect=RuntimeError("db hiccup"))):
        result = await izmeni_rociste("r1", body, _req(method="PATCH"), _user())

    assert result["ok"] is True


# ─── F27: lista_rocista excludes archived cases in the cross-case view ─────

@pytest.mark.anyio
async def test_lista_rocista_without_predmet_id_excludes_archived_cases():
    from routers.rocista import lista_rocista

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.not_.in_.return_value.execute.return_value = MagicMock(
                data=[{"id": "p-active"}]
            )
            return t
        if name == "rocista":
            chain = MagicMock()
            chain.eq.return_value = chain
            chain.in_.return_value = chain
            chain.order.return_value = chain
            chain.limit.return_value = chain
            chain.offset.return_value = chain
            chain.execute.return_value = MagicMock(data=[
                {"id": "r1", "predmet_id": "p-active", "sud": "Sud", "datum": "2026-07-01", "vreme": None, "status": "zakazano"},
            ])
            t.select.return_value = chain
            return t
        return MagicMock()

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await lista_rocista(_req(method="GET"), user=_user())

    assert result["ukupno"] == 1
    assert result["rocista"][0]["predmet_id"] == "p-active"


@pytest.mark.anyio
async def test_lista_rocista_with_explicit_predmet_id_does_not_apply_active_filter():
    """A lawyer viewing one specific (possibly closed) case's own hearing
    history from that case's own page must still see it."""
    from routers.rocista import lista_rocista

    rows = [{"id": "r1", "predmet_id": "p-closed", "sud": "Sud A", "datum": "2026-07-01", "vreme": None, "status": "odrzano"}]
    supa = _supa_ok(rows)

    with patch("routers.rocista._get_supa", return_value=supa):
        result = await lista_rocista(_req(method="GET"), predmet_id="p-closed", user=_user())

    assert result["ukupno"] == 1
    assert result["rocista"][0]["predmet_id"] == "p-closed"
