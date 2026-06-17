# -*- coding: utf-8 -*-
"""Tests for PATCH /api/predmeti/{id}/zatvori and GET /api/predmeti/{id}/ishod"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_user():
    return {"user_id": "uid-001", "email": "test@vindex.rs", "role": "advokat"}


def _fake_request():
    scope = {
        "type": "http", "method": "PATCH",
        "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-001/zatvori",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _build_supa(pred: dict | None, hron_rows: list[dict] | None = None):
    """Build Supabase mock for predmeti + predmet_hronologija."""
    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            # single() chain: .select.eq.eq.single.execute
            single_chain = MagicMock()
            single_chain.execute.return_value.data = pred
            t.select.return_value.eq.return_value.eq.return_value.single.return_value = single_chain
            # update() chain
            upd_chain = MagicMock()
            upd_chain.execute.return_value.data = [pred] if pred else []
            t.update.return_value.eq.return_value.eq.return_value = upd_chain
        elif name == "predmet_hronologija":
            ins_chain = MagicMock()
            ins_chain.execute.return_value.data = [{}]
            t.insert.return_value = ins_chain
            # For GET /ishod
            sel = MagicMock()
            sel.execute.return_value.data = hron_rows or []
            t.select.return_value.eq.return_value.eq.return_value.ilike.return_value.order.return_value.limit.return_value = sel
        return t

    mock.table.side_effect = _table
    return mock


# ─── T1: uspešno zatvaranje predmeta ─────────────────────────────────────────

@pytest.mark.anyio
async def test_zatvori_predmet_success():
    """PATCH /zatvori → sets status zatvoren, returns ishod."""
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    pred = {"id": "pred-001", "naziv": "Test predmet", "status": "aktivan", "opis": "Opis predmeta."}
    body = ZatvoriReq(ishod="pobeda", zakljucak="Klijent dobio spor u celosti.")

    with patch("routers.predmeti_close._get_supa", return_value=_build_supa(pred)):
        result = await zatvori_predmet("pred-001", body, _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["ishod"] == "pobeda"
    assert result["ishod_label"] == "Pobeda"
    assert result["predmet_id"] == "pred-001"


# ─── T2: duplikato zatvaranje → 409 ──────────────────────────────────────────

@pytest.mark.anyio
async def test_zatvori_already_closed():
    """Cannot close a predmet that is already zatvoren → 409."""
    from fastapi import HTTPException
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    pred = {"id": "pred-002", "naziv": "Zatvoren", "status": "zatvoren", "opis": ""}
    body = ZatvoriReq(ishod="nagodba")

    with patch("routers.predmeti_close._get_supa", return_value=_build_supa(pred)):
        with pytest.raises(HTTPException) as exc:
            await zatvori_predmet("pred-002", body, _fake_request(), _fake_user())

    assert exc.value.status_code == 409


# ─── T3: predmet ne postoji → 404 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_zatvori_not_found():
    """Predmet that doesn't belong to user → 404."""
    from fastapi import HTTPException
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    body = ZatvoriReq(ishod="poraz")

    with patch("routers.predmeti_close._get_supa", return_value=_build_supa(None)):
        with pytest.raises(HTTPException) as exc:
            await zatvori_predmet("nonexistent", body, _fake_request(), _fake_user())

    assert exc.value.status_code == 404


# ─── T4: validacija — pogrešan ishod ─────────────────────────────────────────

def test_zatvori_req_invalid_ishod():
    """ZatvoriReq rejects unknown ishod values."""
    from pydantic import ValidationError
    from routers.predmeti_close import ZatvoriReq

    with pytest.raises(ValidationError):
        ZatvoriReq(ishod="nevalidan_ishod")


# ─── T5: validacija — ishod vrednosti ────────────────────────────────────────

@pytest.mark.parametrize("ishod", ["pobeda", "poraz", "nagodba", "odustajanje", "odbacena", "ostalo"])
def test_zatvori_req_all_valid_ishodi(ishod):
    """All valid ishod values must be accepted."""
    from routers.predmeti_close import ZatvoriReq
    req = ZatvoriReq(ishod=ishod)
    assert req.ishod == ishod


# ─── T6: GET /ishod zatvorenog predmeta ──────────────────────────────────────

@pytest.mark.anyio
async def test_get_ishod_closed_predmet():
    """GET /ishod on closed predmet → returns ishod parsed from hronologija."""
    from routers.predmeti_close import get_predmet_ishod

    pred = {"id": "pred-003", "naziv": "Zatvoren predmet", "status": "zatvoren", "opis": ""}
    hron = [{"dogadjaj": "Predmet zatvoren — Ishod: Nagodba / Poravnanje", "datum": "2026-05-10", "akter": "Advokat | Sporazumno rešenje"}]

    req_scope = {
        "type": "http", "method": "GET",
        "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-003/ishod",
        "app": MagicMock(), "state": MagicMock(),
    }
    fake_req = StarletteRequest(scope=req_scope)

    with patch("routers.predmeti_close._get_supa", return_value=_build_supa(pred, hron)):
        result = await get_predmet_ishod("pred-003", fake_req, _fake_user())

    assert result["zatvoren"] is True
    assert result["ishod"] == "nagodba"
    assert result["datum_zatvaranja"] == "2026-05-10"


# ─── T7: GET /ishod aktivnog predmeta ────────────────────────────────────────

@pytest.mark.anyio
async def test_get_ishod_active_predmet():
    """GET /ishod on active predmet → zatvoren=False."""
    from routers.predmeti_close import get_predmet_ishod

    pred = {"id": "pred-004", "naziv": "Aktivan predmet", "status": "aktivan", "opis": ""}

    req_scope = {
        "type": "http", "method": "GET",
        "headers": [], "query_string": b"",
        "path": "/api/predmeti/pred-004/ishod",
        "app": MagicMock(), "state": MagicMock(),
    }
    fake_req = StarletteRequest(scope=req_scope)

    with patch("routers.predmeti_close._get_supa", return_value=_build_supa(pred)):
        result = await get_predmet_ishod("pred-004", fake_req, _fake_user())

    assert result["zatvoren"] is False
    assert result["ishod"] is None
