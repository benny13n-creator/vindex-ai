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


def _build_supa(pred: dict | None, hron_rows: list[dict] | None = None, update_wins: bool = True):
    """Build Supabase mock for predmeti + predmet_hronologija.

    update_wins=False simulates LAMBDA008-CONC-001's guarded race: the
    .eq().eq().neq("status","zatvoren") update returns zero rows, as it would
    for real if a concurrent request already closed the case between this
    handler's own read and its write.
    """
    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            # Ruter koristi .maybe_single() (vraca None kad nista nije nadjeno,
            # umesto da baci izuzetak kao stari .single()) — mokuj oba da
            # test ne zavisi od toga koju od dve metode kod trenutno zove.
            single_chain = MagicMock()
            single_chain.execute.return_value.data = pred
            t.select.return_value.eq.return_value.eq.return_value.single.return_value = single_chain
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = single_chain
            # update() chain -- LAMBDA008-CONC-001 fix added a 3rd .neq() call.
            upd_chain = MagicMock()
            upd_chain.execute.return_value.data = ([pred] if pred else []) if update_wins else []
            t.update.return_value.eq.return_value.eq.return_value.neq.return_value = upd_chain
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


# ─── T4: konkurentno zatvaranje (LAMBDA008-CONC-001) → 409, ne duplirano zatvaranje ──

@pytest.mark.anyio
async def test_zatvori_concurrent_race_returns_409_not_silent_double_close():
    """Program Lambda, Final Certification 008 (LAMBDA008-CONC-001): two concurrent
    PATCH requests both pass the pre-check (both read status='aktivan' before either
    writes) -- the write itself must be guarded on the status this handler read, not
    just id/owner, or both requests silently succeed (double closure note, double
    hronologija/benchmark side effects). Simulates the SECOND request landing after a
    concurrent one already flipped the status: the guarded update matches 0 rows."""
    from fastapi import HTTPException
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    pred = {"id": "pred-003", "naziv": "Race predmet", "status": "aktivan", "opis": ""}
    body = ZatvoriReq(ishod="pobeda")

    with patch("routers.predmeti_close._get_supa", return_value=_build_supa(pred, update_wins=False)):
        with pytest.raises(HTTPException) as exc:
            await zatvori_predmet("pred-003", body, _fake_request(), _fake_user())

    assert exc.value.status_code == 409


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


# ═══════════════════════════════════════════════════════════════════════════
# Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-036 remainder): closing a case
# must also close its own lingering open case_actions rows, not just hide
# them from the worklist query (Mission 001's earlier, visibility-only fix).
# ═══════════════════════════════════════════════════════════════════════════

def _build_supa_with_case_actions(pred: dict | None, update_wins: bool = True):
    mock = MagicMock()
    case_actions_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            single_chain = MagicMock()
            single_chain.execute.return_value.data = pred
            t.select.return_value.eq.return_value.eq.return_value.single.return_value = single_chain
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value = single_chain
            upd_chain = MagicMock()
            upd_chain.execute.return_value.data = ([pred] if pred else []) if update_wins else []
            t.update.return_value.eq.return_value.eq.return_value.neq.return_value = upd_chain
        elif name == "predmet_hronologija":
            ins_chain = MagicMock()
            ins_chain.execute.return_value.data = [{}]
            t.insert.return_value = ins_chain
        elif name == "case_actions":
            def _update(payload):
                node = MagicMock()
                def _eq(col, val):
                    case_actions_calls.append((col, val))
                    return node
                node.eq.side_effect = _eq
                node.execute.return_value = MagicMock(data=[{"id": "ca-1"}])
                return node
            t.update.side_effect = _update
        return t

    mock.table.side_effect = _table
    return mock, case_actions_calls


@pytest.mark.anyio
async def test_zatvori_predmet_closes_lingering_open_case_actions():
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    pred = {"id": "pred-005", "naziv": "Test", "status": "aktivan", "opis": ""}
    body = ZatvoriReq(ishod="pobeda")
    supa, case_actions_calls = _build_supa_with_case_actions(pred)

    with patch("routers.predmeti_close._get_supa", return_value=supa):
        result = await zatvori_predmet("pred-005", body, _fake_request(), _fake_user())

    assert result["ok"] is True
    # predmet_id, user_id, and status='open' were all applied as filters
    filter_cols = [c for c, _ in case_actions_calls]
    assert "predmet_id" in filter_cols
    assert "user_id" in filter_cols
    assert "status" in filter_cols


@pytest.mark.anyio
async def test_zatvori_predmet_survives_case_actions_update_failure():
    """The case_actions bulk-close is best-effort -- a failure there must
    never block or fail the case closure itself (same non-blocking contract
    as the hronologija insert)."""
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    pred = {"id": "pred-006", "naziv": "Test", "status": "aktivan", "opis": ""}
    body = ZatvoriReq(ishod="poraz")
    supa, _ = _build_supa_with_case_actions(pred)

    _orig_side_effect = supa.table.side_effect
    def _wrapped(name):
        if name == "case_actions":
            t = MagicMock()
            t.update.side_effect = RuntimeError("db unavailable")
            return t
        return _orig_side_effect(name)
    supa.table.side_effect = _wrapped

    with patch("routers.predmeti_close._get_supa", return_value=supa):
        result = await zatvori_predmet("pred-006", body, _fake_request(), _fake_user())

    assert result["ok"] is True  # closure itself still succeeded


@pytest.mark.anyio
async def test_bulk_zatvaranje_closes_case_actions_for_updated_predmeti_only():
    from routers.predmeti_close import BulkAkcijaReq, bulk_promena_statusa

    case_actions_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value = \
                MagicMock(data=[{"id": "p1", "status": "aktivan"}, {"id": "p2", "status": "aktivan"}])
            t.update.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = \
                MagicMock(data=[{"id": "p1"}])  # p2 lost a race, only p1 actually updated
        elif name == "case_actions":
            def _update(payload):
                node = MagicMock()
                def _eq(col, val):
                    return node
                def _in_(col, vals):
                    case_actions_calls.append(list(vals))
                    return node
                node.eq.side_effect = _eq
                node.in_.side_effect = _in_
                node.execute.return_value = MagicMock(data=[])
                return node
            t.update.side_effect = _update
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    body = BulkAkcijaReq(predmet_ids=["p1", "p2"], akcija="zatvaranje")
    with patch("routers.predmeti_close._get_supa", return_value=supa):
        result = await bulk_promena_statusa(body, _fake_request(), _fake_user())

    assert result["azurirano"] == 1
    assert case_actions_calls == [["p1"]]  # only the actually-updated predmet, not p2


@pytest.mark.anyio
async def test_bulk_aktiviranje_does_not_touch_case_actions():
    """Reopening a case must not close/touch its case_actions -- exempt scope."""
    from routers.predmeti_close import BulkAkcijaReq, bulk_promena_statusa

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value = \
                MagicMock(data=[{"id": "p1", "status": "zatvoren"}])
            t.update.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = \
                MagicMock(data=[{"id": "p1"}])
        elif name == "case_actions":
            raise AssertionError("case_actions must not be touched on aktiviranje")
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    body = BulkAkcijaReq(predmet_ids=["p1"], akcija="aktiviranje")
    with patch("routers.predmeti_close._get_supa", return_value=supa):
        result = await bulk_promena_statusa(body, _fake_request(), _fake_user())

    assert result["azurirano"] == 1
