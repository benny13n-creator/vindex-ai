# -*- coding: utf-8 -*-
"""
Tests for shared/seats.py — SeatService (Faza 71).

Proverava formulu (iskorišćena_mesta = 1 admin + COUNT(ACTIVE) + COUNT(INVITED)),
dozvoljene prelaze stanja, i da svaki prelaz piše audit red.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supa(profile: dict, clanovi: list, audit_insert_raises=False):
    supa = MagicMock()

    def _table(name):
        chain = MagicMock()
        for attr in ["select", "eq", "insert", "update", "limit", "order", "maybe_single"]:
            setattr(chain, attr, MagicMock(return_value=chain))

        if name == "profiles":
            chain.execute = MagicMock(return_value=MagicMock(data=profile))
        elif name == "kancelarija_clanovi":
            def _select(*a, **kw):
                # .select("status") for get_seat_summary vs. .update(...) for transition
                return chain
            chain.select = MagicMock(side_effect=_select)
            chain.execute = MagicMock(return_value=MagicMock(data=clanovi))
        elif name == "kancelarija_seat_audit":
            if audit_insert_raises:
                chain.execute = MagicMock(side_effect=Exception("DB down"))
            else:
                chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "audit-1"}]))
        else:
            chain.execute = MagicMock(return_value=MagicMock(data=[]))
        return chain

    supa.table = MagicMock(side_effect=_table)
    return supa


# ═══════════════════════════════════════════════════════════════════════════
# get_seat_summary — formula correctness
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_summary_enterprise_base_no_extra():
    from shared.seats import SeatService
    supa = _make_supa(
        profile={"subscription_type": "enterprise", "subscription_seats_extra": 0},
        clanovi=[{"status": "ACTIVE"}, {"status": "ACTIVE"}],
    )
    with patch("shared.seats._get_supa", return_value=supa):
        s = await SeatService.get_seat_summary("kanc-1", "admin-1")

    assert s["tier"] == "enterprise"
    assert s["base_included_seats"] == 3
    assert s["extra_seats_purchased"] == 0
    assert s["total_allowed_seats"] == 3
    # 1 (admin) + 2 ACTIVE + 0 INVITED = 3
    assert s["used_seats"] == 3
    assert s["available_seats"] == 0


@pytest.mark.anyio
async def test_summary_invited_consumes_seat():
    """INVITED must count toward used_seats — without this, an admin on a
    3-seat plan could send unlimited invitations."""
    from shared.seats import SeatService
    supa = _make_supa(
        profile={"subscription_type": "enterprise", "subscription_seats_extra": 0},
        clanovi=[{"status": "ACTIVE"}, {"status": "INVITED"}],
    )
    with patch("shared.seats._get_supa", return_value=supa):
        s = await SeatService.get_seat_summary("kanc-1", "admin-1")

    assert s["used_seats"] == 3  # 1 admin + 1 ACTIVE + 1 INVITED
    assert s["available_seats"] == 0


@pytest.mark.anyio
async def test_summary_suspended_pending_removed_dont_consume():
    from shared.seats import SeatService
    supa = _make_supa(
        profile={"subscription_type": "enterprise", "subscription_seats_extra": 0},
        clanovi=[
            {"status": "ACTIVE"},
            {"status": "SUSPENDED"}, {"status": "SUSPENDED"},
            {"status": "PENDING"},
            {"status": "REMOVED"}, {"status": "REMOVED"}, {"status": "REMOVED"},
        ],
    )
    with patch("shared.seats._get_supa", return_value=supa):
        s = await SeatService.get_seat_summary("kanc-1", "admin-1")

    assert s["used_seats"] == 2  # 1 admin + 1 ACTIVE only
    assert s["available_seats"] == 1
    assert s["breakdown"]["SUSPENDED"] == 2
    assert s["breakdown"]["REMOVED"] == 3


@pytest.mark.anyio
async def test_summary_extra_seats_increase_capacity():
    from shared.seats import SeatService
    supa = _make_supa(
        profile={"subscription_type": "enterprise", "subscription_seats_extra": 2},
        clanovi=[{"status": "ACTIVE"}] * 4,
    )
    with patch("shared.seats._get_supa", return_value=supa):
        s = await SeatService.get_seat_summary("kanc-1", "admin-1")

    assert s["total_allowed_seats"] == 5  # 3 base + 2 extra
    assert s["used_seats"] == 5  # 1 admin + 4 ACTIVE
    assert s["available_seats"] == 0


@pytest.mark.anyio
async def test_summary_basic_professional_single_seat():
    from shared.seats import SeatService
    supa = _make_supa(profile={"subscription_type": "professional", "subscription_seats_extra": 0}, clanovi=[])
    with patch("shared.seats._get_supa", return_value=supa):
        s = await SeatService.get_seat_summary("kanc-1", "admin-1")
    assert s["base_included_seats"] == 1
    assert s["total_allowed_seats"] == 1


@pytest.mark.anyio
async def test_summary_missing_profile_defaults_to_basic():
    """profiles row not found (maybe_single returns None) must not crash —
    defaults to basic tier, matching the rest of the entitlement system's
    fail-safe convention."""
    from shared.seats import SeatService
    supa = _make_supa(profile={}, clanovi=[])
    with patch("shared.seats._get_supa", return_value=supa):
        s = await SeatService.get_seat_summary("kanc-1", "admin-1")
    assert s["tier"] == "basic"
    assert s["base_included_seats"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# assert_seat_available
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_assert_seat_available_blocks_when_full():
    from shared.seats import SeatService
    supa = _make_supa(
        profile={"subscription_type": "enterprise", "subscription_seats_extra": 0},
        clanovi=[{"status": "ACTIVE"}, {"status": "ACTIVE"}],
    )
    with patch("shared.seats._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await SeatService.assert_seat_available("kanc-1", "admin-1")
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "NO_SEATS_AVAILABLE"


@pytest.mark.anyio
async def test_assert_seat_available_passes_when_room():
    from shared.seats import SeatService
    supa = _make_supa(
        profile={"subscription_type": "enterprise", "subscription_seats_extra": 0},
        clanovi=[{"status": "ACTIVE"}],
    )
    with patch("shared.seats._get_supa", return_value=supa):
        summary = await SeatService.assert_seat_available("kanc-1", "admin-1")
    assert summary["available_seats"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# transition — state machine + audit log
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_transition_valid_writes_update_and_audit():
    from shared.seats import SeatService
    supa = _make_supa(profile={}, clanovi=[])
    with patch("shared.seats._get_supa", return_value=supa):
        await SeatService.transition(
            kancelarija_id="kanc-1", clan_id="clan-1", clan_email="a@b.rs",
            actor_uid="admin-1", actor_email="admin@b.rs", action="accept",
            from_status="INVITED", to_status="ACTIVE",
        )

    # kancelarija_clanovi.update() called with the new status
    calls = [c for c in supa.table.call_args_list if c.args[0] == "kancelarija_clanovi"]
    assert len(calls) >= 1
    # kancelarija_seat_audit.insert() called
    audit_calls = [c for c in supa.table.call_args_list if c.args[0] == "kancelarija_seat_audit"]
    assert len(audit_calls) >= 1


@pytest.mark.anyio
async def test_transition_invalid_raises_value_error():
    """REMOVED is (mostly) terminal — REMOVED -> ACTIVE directly must never
    be allowed (that would silently resurrect a removed member without
    going through the invite flow, bypassing seat checks)."""
    from shared.seats import SeatService
    with pytest.raises(ValueError):
        await SeatService.transition(
            kancelarija_id="kanc-1", clan_id="clan-1", clan_email="a@b.rs",
            actor_uid="admin-1", actor_email="admin@b.rs", action="reactivate",
            from_status="REMOVED", to_status="ACTIVE",
        )


@pytest.mark.anyio
async def test_transition_removed_to_invited_allowed_for_reinvite():
    from shared.seats import SeatService
    supa = _make_supa(profile={}, clanovi=[])
    with patch("shared.seats._get_supa", return_value=supa):
        await SeatService.transition(
            kancelarija_id="kanc-1", clan_id="clan-1", clan_email="a@b.rs",
            actor_uid="admin-1", actor_email="admin@b.rs", action="invite",
            from_status="REMOVED", to_status="INVITED",
        )  # must not raise


@pytest.mark.anyio
async def test_transition_audit_write_failure_raises_503():
    from shared.seats import SeatService
    supa = _make_supa(profile={}, clanovi=[], audit_insert_raises=True)
    with patch("shared.seats._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await SeatService.transition(
                kancelarija_id="kanc-1", clan_id="clan-1", clan_email="a@b.rs",
                actor_uid="admin-1", actor_email="admin@b.rs", action="accept",
                from_status="INVITED", to_status="ACTIVE",
            )
    assert exc.value.status_code == 503


def test_all_five_states_in_transition_table():
    from shared.seats import _VALID_TRANSITIONS
    assert set(_VALID_TRANSITIONS.keys()) == {"ACTIVE", "INVITED", "PENDING", "SUSPENDED", "REMOVED"}


def test_seat_consuming_statuses_exactly_active_and_invited():
    from shared.seats import SEAT_CONSUMING_STATUSES
    assert set(SEAT_CONSUMING_STATUSES) == {"ACTIVE", "INVITED"}


def test_base_included_seats_enterprise_is_3():
    """Locks in the 3-included-seats constant from migration 063's own
    comment ('3 uključena u Enterprise') — a silent change here would be a
    pricing regression, not a refactor."""
    from shared.seats import BASE_INCLUDED_SEATS
    assert BASE_INCLUDED_SEATS["enterprise"] == 3
    assert BASE_INCLUDED_SEATS["basic"] == 1
    assert BASE_INCLUDED_SEATS["professional"] == 1
