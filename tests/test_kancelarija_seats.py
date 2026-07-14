# -*- coding: utf-8 -*-
"""
Tests for routers/kancelarija.py — seat lifecycle endpoints (Faza 71).

Focus: does the ROUTER correctly call SeatService (seat-limit checks before
inviting/reactivating, soft-delete instead of hard delete on remove/leave,
admin-only guards) — shared/seats.py's own formula/transition-table logic is
covered separately in tests/test_seats.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest
from fastapi import HTTPException


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/kancelarija/pozovi", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user(uid="admin-uid-1", email="admin@firma.rs"):
    return {"user_id": uid, "email": email}


_FIRMA = {"id": "firma-1", "naziv": "Firma DOO", "admin_uid": "admin-uid-1"}


def _make_chain(data):
    chain = MagicMock()
    for attr in ["table", "select", "eq", "neq", "insert", "update", "delete",
                 "limit", "order", "maybe_single", "in_"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# pozovi_clana — seat-limit enforcement is the whole point of Faza 71
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_pozovi_blocked_when_no_seats():
    from routers.kancelarija import pozovi_clana, PozovReq

    supa = _make_chain(_FIRMA)  # _require_firma_admin finds the firm
    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.assert_seat_available",
               new_callable=AsyncMock, side_effect=HTTPException(403, detail={"code": "NO_SEATS_AVAILABLE"})):
        with pytest.raises(HTTPException) as exc:
            await pozovi_clana(_req(), PozovReq(email="novi@test.rs", uloga="saradnik"), _user())

    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_pozovi_succeeds_when_seat_available_new_member():
    from routers.kancelarija import pozovi_clana, PozovReq

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            # first call: _require_firma_admin already used kancelarije table;
            # this table is used for _find_existing (no existing row) then insert
            chain = _make_chain(None)
            chain.insert = MagicMock(return_value=_make_chain([{"id": "clan-1", "email": "novi@test.rs"}]))
            return chain
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.assert_seat_available", new_callable=AsyncMock, return_value={"available_seats": 1}), \
         patch("routers.kancelarija.SeatService.transition", new_callable=AsyncMock) as mock_transition:
        result = await pozovi_clana(_req(), PozovReq(email="novi@test.rs", uloga="saradnik"), _user())

    assert result["ok"] is True
    assert result["action"] == "invited"
    mock_transition.assert_called_once()
    assert mock_transition.call_args.kwargs["to_status"] == "INVITED"
    assert mock_transition.call_args.kwargs["from_status"] is None


@pytest.mark.anyio
async def test_pozovi_rejects_already_active_member():
    from routers.kancelarija import pozovi_clana, PozovReq

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "status": "ACTIVE"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.assert_seat_available", new_callable=AsyncMock, return_value={"available_seats": 1}):
        with pytest.raises(HTTPException) as exc:
            await pozovi_clana(_req(), PozovReq(email="postojeci@test.rs", uloga="saradnik"), _user())

    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_pozovi_reinvite_removed_member_reuses_row():
    from routers.kancelarija import pozovi_clana, PozovReq

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-old", "status": "REMOVED"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.assert_seat_available", new_callable=AsyncMock, return_value={"available_seats": 1}), \
         patch("routers.kancelarija.SeatService.transition", new_callable=AsyncMock) as mock_transition:
        result = await pozovi_clana(_req(), PozovReq(email="vratio.se@test.rs", uloga="saradnik"), _user())

    assert result["action"] == "reinvited"
    mock_transition.assert_called_once()
    kw = mock_transition.call_args.kwargs
    assert kw["clan_id"] == "clan-old"
    assert kw["from_status"] == "REMOVED"
    assert kw["to_status"] == "INVITED"


@pytest.mark.anyio
async def test_pozovi_non_admin_gets_403():
    from routers.kancelarija import pozovi_clana, PozovReq

    supa = _make_chain(None)  # _get_firma_for_admin finds nothing
    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await pozovi_clana(_req(), PozovReq(email="x@test.rs", uloga="saradnik"), _user(uid="not-admin"))
    assert exc.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# ukloni_clana — MUST soft-delete (status=REMOVED), never hard DELETE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_ukloni_soft_deletes_not_hard_deletes():
    from routers.kancelarija import ukloni_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "ACTIVE", "user_id": "other-uid"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.transition", new_callable=AsyncMock) as mock_transition:
        result = await ukloni_clana(_req(), "clan-1", _user())

    assert result["ok"] is True
    mock_transition.assert_called_once()
    kw = mock_transition.call_args.kwargs
    assert kw["to_status"] == "REMOVED"
    assert kw["extra_fields"]["removed_reason"] == "removed_by_admin"
    # The endpoint itself must never call .delete() on kancelarija_clanovi —
    # only SeatService.transition (mocked here) writes the status change.
    for call in supa.table.return_value.delete.call_args_list:
        pytest.fail("ukloni_clana must not call .delete() directly — soft-delete only")


@pytest.mark.anyio
async def test_ukloni_cannot_remove_self():
    from routers.kancelarija import ukloni_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "ACTIVE", "user_id": "admin-uid-1"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await ukloni_clana(_req(), "clan-1", _user())
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_ukloni_already_removed_rejected():
    from routers.kancelarija import ukloni_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "REMOVED", "user_id": "other"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await ukloni_clana(_req(), "clan-1", _user())
    assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# suspenduj_clana / reaktiviraj_clana
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_suspenduj_only_works_on_active():
    from routers.kancelarija import suspenduj_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "INVITED"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await suspenduj_clana(_req(), "clan-1", _user())
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_suspenduj_active_member_succeeds():
    from routers.kancelarija import suspenduj_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "ACTIVE"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.transition", new_callable=AsyncMock) as mock_transition:
        result = await suspenduj_clana(_req(), "clan-1", _user())

    assert result["ok"] is True
    kw = mock_transition.call_args.kwargs
    assert kw["from_status"] == "ACTIVE"
    assert kw["to_status"] == "SUSPENDED"


@pytest.mark.anyio
async def test_reaktiviraj_checks_seat_availability_again():
    """SUSPENDED doesn't consume a seat — reactivating must re-check capacity
    since other invites/accepts could have filled it while suspended."""
    from routers.kancelarija import reaktiviraj_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "SUSPENDED"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.assert_seat_available",
               new_callable=AsyncMock, side_effect=HTTPException(403, detail={"code": "NO_SEATS_AVAILABLE"})) as mock_assert:
        with pytest.raises(HTTPException) as exc:
            await reaktiviraj_clana(_req(), "clan-1", _user())

    mock_assert.assert_called_once()
    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_reaktiviraj_rejects_non_suspended():
    from routers.kancelarija import reaktiviraj_clana

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "email": "x@test.rs", "status": "ACTIVE"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await reaktiviraj_clana(_req(), "clan-1", _user())
    assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# napusti_kancelariju — self-leave is also soft-delete
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_napusti_soft_deletes_with_correct_reason():
    from routers.kancelarija import napusti_kancelariju

    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(None)  # not an admin
        if name == "kancelarija_clanovi":
            return _make_chain({"id": "clan-1", "kancelarija_id": "firma-1"})
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.transition", new_callable=AsyncMock) as mock_transition:
        result = await napusti_kancelariju(_req(), _user(uid="member-uid", email="member@test.rs"))

    assert result["ok"] is True
    kw = mock_transition.call_args.kwargs
    assert kw["to_status"] == "REMOVED"
    assert kw["extra_fields"]["removed_reason"] == "left_voluntarily"


@pytest.mark.anyio
async def test_napusti_admin_cannot_leave():
    from routers.kancelarija import napusti_kancelariju

    supa = _make_chain(_FIRMA)  # admin has a firm
    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await napusti_kancelariju(_req(), _user())
    assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# pregled_mesta / istorija_mesta — admin-only, delegate to SeatService
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_pregled_mesta_admin_only():
    from routers.kancelarija import pregled_mesta

    supa = _make_chain(None)
    with patch("routers.kancelarija._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await pregled_mesta(_req(), _user())
    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_pregled_mesta_returns_seat_summary():
    from routers.kancelarija import pregled_mesta

    supa = _make_chain(_FIRMA)
    fake_summary = {"used_seats": 2, "total_allowed_seats": 3, "available_seats": 1}
    with patch("routers.kancelarija._get_supa", return_value=supa), \
         patch("routers.kancelarija.SeatService.get_seat_summary", new_callable=AsyncMock, return_value=fake_summary):
        result = await pregled_mesta(_req(), _user())
    assert result == fake_summary


@pytest.mark.anyio
async def test_istorija_mesta_returns_audit_events():
    from routers.kancelarija import istorija_mesta

    events = [{"action": "invite", "to_status": "INVITED"}, {"action": "accept", "to_status": "ACTIVE"}]
    supa = MagicMock()
    def _table(name):
        if name == "kancelarije":
            return _make_chain(_FIRMA)
        if name == "kancelarija_seat_audit":
            return _make_chain(events)
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.kancelarija._get_supa", return_value=supa):
        result = await istorija_mesta(_req(), _user())

    assert result["firma_id"] == "firma-1"
    assert result["events"] == events


# ═══════════════════════════════════════════════════════════════════════════
# _get_clanovi — REMOVED excluded from default listing
# ═══════════════════════════════════════════════════════════════════════════

def test_get_clanovi_excludes_removed_by_default():
    from routers.kancelarija import _get_clanovi

    chain = _make_chain([{"status": "ACTIVE"}])
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    _get_clanovi(supa, "firma-1")

    neq_calls = [c for c in chain.neq.call_args_list]
    assert any(c.args == ("status", "REMOVED") for c in neq_calls)


def test_get_clanovi_includes_removed_when_requested():
    from routers.kancelarija import _get_clanovi

    chain = _make_chain([{"status": "REMOVED"}])
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    _get_clanovi(supa, "firma-1", ukljuci_uklonjene=True)

    assert chain.neq.call_count == 0
