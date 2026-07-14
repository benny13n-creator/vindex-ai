# -*- coding: utf-8 -*-
"""
Tests for shared/tier_config.py + Admin Tier Config Console (routers/
admin_dashboard.py) — Tier Configuration priority #1.

Verifies tier_config is genuinely the single source of truth for tier
pricing/seats: reader service, cache invalidation, and that the Admin
Console PATCH endpoint writes + invalidates + audits exactly like Feature
Registry does.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
             "path": "/api/admin/tier-config", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _founder():
    return {"user_id": "f-1", "email": "benny13.n@gmail.com"}


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "order", "limit", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# shared/tier_config.py — reader service
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_tier_reads_from_cache_after_load():
    import shared.tier_config as tc
    tc._CACHE = {}
    tc._CACHE_LOADED_AT = 0.0

    rows = [
        {"tier_key": "basic", "display_name": "Basic", "monthly_price_eur": 29, "included_seats": 1, "sort_order": 1},
        {"tier_key": "professional", "display_name": "Professional", "monthly_price_eur": 79, "included_seats": 1, "sort_order": 2},
        {"tier_key": "enterprise", "display_name": "Enterprise", "monthly_price_eur": 249, "included_seats": 3, "extra_seat_price_eur": 49, "sort_order": 3},
    ]
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))

    with patch("shared.tier_config._get_supa", return_value=supa):
        tier = await tc.get_tier("enterprise")

    assert tier["monthly_price_eur"] == 249
    assert tier["included_seats"] == 3
    assert tier["extra_seat_price_eur"] == 49


@pytest.mark.anyio
async def test_get_tier_rejects_invalid_key():
    import shared.tier_config as tc
    with pytest.raises(RuntimeError):
        await tc.get_tier("nonexistent_tier")


@pytest.mark.anyio
async def test_get_all_tiers_sorted_by_sort_order():
    import shared.tier_config as tc
    tc._CACHE = {}
    tc._CACHE_LOADED_AT = 0.0

    rows = [
        {"tier_key": "enterprise", "sort_order": 3},
        {"tier_key": "basic", "sort_order": 1},
        {"tier_key": "professional", "sort_order": 2},
    ]
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))

    with patch("shared.tier_config._get_supa", return_value=supa):
        tiers = await tc.get_all_tiers()

    assert [t["tier_key"] for t in tiers] == ["basic", "professional", "enterprise"]


@pytest.mark.anyio
async def test_invalidate_forces_reload():
    import shared.tier_config as tc
    tc._CACHE = {"basic": {"tier_key": "basic", "monthly_price_eur": 29}}
    tc._CACHE_LOADED_AT = 999999999.0  # far future — would never expire via TTL alone

    rows = [{"tier_key": "basic", "monthly_price_eur": 39}]  # price "changed"
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))

    tc.invalidate()
    with patch("shared.tier_config._get_supa", return_value=supa):
        tier = await tc.get_tier("basic")

    assert tier["monthly_price_eur"] == 39


# ═══════════════════════════════════════════════════════════════════════════
# Admin Tier Config Console — GET/PATCH mirror Feature Registry's pattern
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_tier_config_list_founder_only():
    from routers.admin_dashboard import tier_config_list
    with pytest.raises(Exception):  # HTTPException 403 from _require_founder
        await tier_config_list(_req(), user={"user_id": "x", "email": "not-founder@test.rs"})


@pytest.mark.anyio
async def test_tier_config_update_writes_and_invalidates_and_audits():
    from routers.admin_dashboard import tier_config_update, TierConfigUpdate

    old_row = {"tier_key": "professional", "monthly_price_eur": 79}
    supa = MagicMock()

    def _table(name):
        if name == "tier_config":
            chain = _make_chain(old_row)
            chain.update = MagicMock(return_value=_make_chain([{"tier_key": "professional", "monthly_price_eur": 89}]))
            return chain
        if name == "tier_config_audit":
            return _make_chain([{"id": "audit-1"}])
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.admin_dashboard._get_supa", return_value=supa), \
         patch("shared.tier_config.invalidate") as mock_invalidate:
        result = await tier_config_update("professional", TierConfigUpdate(monthly_price_eur=89), _req(), _founder())

    assert result["azurirano"]["monthly_price_eur"] == 89
    mock_invalidate.assert_called_once()

    # Audit write happened with correct before/after
    audit_calls = [c for c in supa.table.call_args_list if c.args[0] == "tier_config_audit"]
    assert len(audit_calls) == 1


@pytest.mark.anyio
async def test_tier_config_update_rejects_unknown_tier():
    from routers.admin_dashboard import tier_config_update, TierConfigUpdate
    from fastapi import HTTPException

    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(None))

    with patch("routers.admin_dashboard._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await tier_config_update("not_a_tier", TierConfigUpdate(monthly_price_eur=10), _req(), _founder())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_tier_config_update_no_fields_rejected():
    from routers.admin_dashboard import tier_config_update, TierConfigUpdate
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await tier_config_update("basic", TierConfigUpdate(), _req(), _founder())
    assert exc.value.status_code == 400
