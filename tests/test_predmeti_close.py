# -*- coding: utf-8 -*-
"""Tests for PATCH /api/predmeti/{id}/zatvori and GET /api/predmeti/{id}/ishod"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest

# Wave 2, Task 2B: routers/predmeti_close.py now calls into
# services.case_evolution (canonical case_actions ownership) from inside
# zatvori_predmet/bulk_promena_statusa. That module-lazy import chain
# (case_evolution -> event_bus -> EventBus() at event_bus's own module
# level -> lazy-imports case_evolution back for handle_case_changed) is
# only safe once both modules are already fully loaded -- exactly what
# importing the full app here guarantees, the same reason every other test
# file that touches Case Evolution does this same import first. Without
# it, a test file that imports routers.predmeti_close in isolation (as
# this file always has) triggers a partial-module ImportError the very
# first time it calls either endpoint.
from api import app  # noqa: E402,F401


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
        return t

    mock.table.side_effect = _table
    return mock


@pytest.mark.anyio
async def test_zatvori_predmet_survives_case_actions_update_failure():
    """The case_actions reconcile is best-effort -- a failure there must
    never block or fail the case closure itself (same non-blocking contract
    as the hronologija insert). services.case_evolution._get_supa is left
    UNPATCHED here on purpose -- it falls through to the real (fake-host)
    client, which raises on any network call, proving the try/except around
    the reconcile call in zatvori_predmet actually swallows a real failure
    rather than one hand-crafted to fail."""
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet

    pred = {"id": "pred-006", "naziv": "Test", "status": "aktivan", "opis": ""}
    body = ZatvoriReq(ishod="poraz")
    supa = _build_supa_with_case_actions(pred)

    with patch("routers.predmeti_close._get_supa", return_value=supa):
        result = await zatvori_predmet("pred-006", body, _fake_request(), _fake_user())

    assert result["ok"] is True  # closure itself still succeeded


@pytest.mark.anyio
async def test_bulk_aktiviranje_reconcile_not_invoked():
    """Reopening a case must not trigger any case_actions reconcile --
    exempt scope, unchanged by Wave 2 Task 2B."""
    from routers.predmeti_close import BulkAkcijaReq, bulk_promena_statusa

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value = \
                MagicMock(data=[{"id": "p1", "status": "zatvoren"}])
            t.update.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = \
                MagicMock(data=[{"id": "p1"}])
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.predmeti_close._get_supa", return_value=supa), \
         patch("services.case_evolution._consequence_refresh_case_actions") as _mock_reconcile:
        body = BulkAkcijaReq(predmet_ids=["p1"], akcija="aktiviranje")
        result = await bulk_promena_statusa(body, _fake_request(), _fake_user())

    assert result["azurirano"] == 1
    _mock_reconcile.assert_not_called()


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
