# -*- coding: utf-8 -*-
"""
Tests for routers/product_intelligence.py — Product Intelligence Layer.
All tests run without live Supabase or external services (mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
             "path": "/admin/pi/overview", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _founder():
    return {"user_id": "aaaa-0000", "email": "benny13.n@gmail.com"}


def _make_chain(data):
    chain = MagicMock()
    for attr in ['select', 'eq', 'gte', 'lte', 'lt', 'order', 'limit', 'execute']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock()
    r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _make_supa(data=None):
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(data or []))
    return supa


# Events fixtures
def _ev(uid, feature, action, dt_str):
    return {"user_id": uid, "feature": feature, "action": action, "created_at": dt_str}


today = date.today()
TODAY = today.isoformat()
T30   = (today - timedelta(days=30)).isoformat()
T60   = (today - timedelta(days=60)).isoformat()
T90   = (today - timedelta(days=90)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Helper: _compute_sessions
# ═══════════════════════════════════════════════════════════════════════════════

def test_compute_sessions_empty():
    from routers.product_intelligence import _compute_sessions
    total, avg, durations = _compute_sessions([])
    assert total == 0
    assert avg == 0.0
    assert durations == []


def test_compute_sessions_single_event():
    from routers.product_intelligence import _compute_sessions
    events = [{"user_id": "u1", "created_at": TODAY + "T10:00:00+00:00"}]
    total, avg, durations = _compute_sessions(events)
    assert total == 1
    assert avg == 0.0


def test_compute_sessions_two_within_gap():
    from routers.product_intelligence import _compute_sessions
    events = [
        {"user_id": "u1", "created_at": TODAY + "T10:00:00+00:00"},
        {"user_id": "u1", "created_at": TODAY + "T10:15:00+00:00"},
    ]
    total, avg, durations = _compute_sessions(events)
    assert total == 1
    assert avg == 15.0


def test_compute_sessions_split_on_gap():
    from routers.product_intelligence import _compute_sessions
    events = [
        {"user_id": "u1", "created_at": TODAY + "T10:00:00+00:00"},
        {"user_id": "u1", "created_at": TODAY + "T11:00:00+00:00"},  # >30min gap
    ]
    total, avg, durations = _compute_sessions(events)
    assert total == 2


def test_compute_sessions_two_users():
    from routers.product_intelligence import _compute_sessions
    events = [
        {"user_id": "u1", "created_at": TODAY + "T10:00:00+00:00"},
        {"user_id": "u2", "created_at": TODAY + "T10:00:00+00:00"},
    ]
    total, avg, durations = _compute_sessions(events)
    assert total == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Helper: _cohort_retention
# ═══════════════════════════════════════════════════════════════════════════════

def test_cohort_retention_empty():
    from routers.product_intelligence import _cohort_retention
    result = _cohort_retention([])
    assert result["cohorts"] == []
    assert result["d7_rate"] == 0.0
    assert result["d30_rate"] == 0.0


def test_cohort_retention_required_keys():
    from routers.product_intelligence import _cohort_retention
    events = [{"user_id": "u1", "created_at": TODAY + "T10:00:00"}]
    result = _cohort_retention(events)
    assert "cohorts" in result
    assert "d7_rate" in result
    assert "d30_rate" in result


def test_cohort_retention_no_crash_on_bad_dates():
    from routers.product_intelligence import _cohort_retention
    events = [
        {"user_id": "u1", "created_at": "not-a-date"},
        {"user_id": "u2", "created_at": None},
        {"user_id": "", "created_at": TODAY + "T10:00:00"},
    ]
    result = _cohort_retention(events)
    assert "cohorts" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Helper: _funnel_conversion
# ═══════════════════════════════════════════════════════════════════════════════

def test_funnel_conversion_empty_events():
    from routers.product_intelligence import _funnel_conversion, _FUNNELS
    result = _funnel_conversion([], _FUNNELS[0])
    assert result["ukupna_konverzija"] == 0.0
    assert result["naziv"] == _FUNNELS[0]["naziv"]


def test_funnel_conversion_required_keys():
    from routers.product_intelligence import _funnel_conversion, _FUNNELS
    result = _funnel_conversion([], _FUNNELS[0])
    assert {"naziv", "koraci", "ukupna_konverzija", "ukupno_korisnika"}.issubset(result.keys())


def test_funnel_conversion_step_counts():
    from routers.product_intelligence import _funnel_conversion
    funnel = {
        "naziv": "Test funnel",
        "koraci": [
            {"feature": "auth", "action": "login", "label": "Login"},
            {"feature": "dashboard", "action": "view", "label": "Dashboard"},
        ],
    }
    events = [
        {"user_id": "u1", "feature": "auth", "action": "login"},
        {"user_id": "u1", "feature": "dashboard", "action": "view"},
        {"user_id": "u2", "feature": "auth", "action": "login"},
    ]
    result = _funnel_conversion(events, funnel)
    koraci = result["koraci"]
    assert koraci[0]["korisnici"] == 2  # both users did auth/login
    assert koraci[1]["korisnici"] == 1  # only u1 viewed dashboard


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Helper: _safe
# ═══════════════════════════════════════════════════════════════════════════════

def test_safe_returns_empty_on_exception():
    from routers.product_intelligence import _safe
    assert _safe(ValueError("boom")) == []


def test_safe_returns_data():
    from routers.product_intelligence import _safe
    r = MagicMock()
    r.data = [{"x": 1}]
    assert _safe(r) == [{"x": 1}]


def test_safe_returns_empty_on_none_data():
    from routers.product_intelligence import _safe
    r = MagicMock()
    r.data = None
    assert _safe(r) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Endpoint: pi_overview
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_overview_required_keys():
    from routers.product_intelligence import pi_overview
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_overview(request=_req(), user=_founder())
    assert {"dau", "wau", "mau", "mau_trend", "total_sessions_90d",
            "avg_session_minutes", "events_per_day_30d", "total_korisnika_90d"}.issubset(result.keys())


@pytest.mark.anyio
async def test_overview_empty_events_zeros():
    from routers.product_intelligence import pi_overview
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_overview(request=_req(), user=_founder())
    assert result["dau"] == 0
    assert result["mau"] == 0
    assert result["total_sessions_90d"] == 0


@pytest.mark.anyio
async def test_overview_events_per_day_length():
    from routers.product_intelligence import pi_overview
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_overview(request=_req(), user=_founder())
    assert len(result["events_per_day_30d"]) == 30


@pytest.mark.anyio
async def test_overview_dau_counts_todays_users():
    from routers.product_intelligence import pi_overview
    events = [
        _ev("u1", "dashboard", "view", TODAY + "T10:00:00+00:00"),
        _ev("u2", "dashboard", "view", TODAY + "T11:00:00+00:00"),
        _ev("u1", "copilot",   "query", T30 + "T10:00:00+00:00"),
    ]
    supa = _make_supa(events)
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_overview(request=_req(), user=_founder())
    assert result["dau"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Endpoint: pi_features
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_features_required_keys():
    from routers.product_intelligence import pi_features
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_features(request=_req(), user=_founder())
    assert {"period_dana", "ukupno_events", "top_features",
            "least_used", "total_credits_spent"}.issubset(result.keys())


@pytest.mark.anyio
async def test_features_empty_events():
    from routers.product_intelligence import pi_features
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_features(request=_req(), user=_founder())
    assert result["ukupno_events"] == 0
    assert result["top_features"] == []
    assert result["total_credits_spent"] == 0


@pytest.mark.anyio
async def test_features_credit_calculation():
    from routers.product_intelligence import pi_features
    events = [
        _ev("u1", "drafting",  "query", TODAY + "T10:00:00+00:00"),  # cost=2
        _ev("u1", "drafting",  "query", TODAY + "T11:00:00+00:00"),  # cost=2
        _ev("u1", "hearing_cc","generate", TODAY + "T12:00:00+00:00"),  # cost=3
    ]
    supa = _make_supa(events)
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_features(request=_req(), user=_founder())
    assert result["total_credits_spent"] == 7  # 2+2+3


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Endpoint: pi_retention
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_retention_required_keys():
    from routers.product_intelligence import pi_retention
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_retention(request=_req(), user=_founder())
    assert {"cohorts", "d7_rate", "d30_rate", "opis"}.issubset(result.keys())


@pytest.mark.anyio
async def test_retention_empty_cohorts():
    from routers.product_intelligence import pi_retention
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_retention(request=_req(), user=_founder())
    assert result["cohorts"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Endpoint: pi_funnels
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_funnels_required_keys():
    from routers.product_intelligence import pi_funnels
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_funnels(request=_req(), user=_founder())
    assert {"period_dana", "funnels"}.issubset(result.keys())


@pytest.mark.anyio
async def test_funnels_count_matches_funnels_definition():
    from routers.product_intelligence import pi_funnels, _FUNNELS
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_funnels(request=_req(), user=_founder())
    assert len(result["funnels"]) == len(_FUNNELS)


@pytest.mark.anyio
async def test_funnels_each_funnel_has_required_keys():
    from routers.product_intelligence import pi_funnels
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_funnels(request=_req(), user=_founder())
    for funnel in result["funnels"]:
        assert {"naziv", "koraci", "ukupna_konverzija"}.issubset(funnel.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Endpoint: pi_timeline
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_timeline_required_keys():
    from routers.product_intelligence import pi_timeline
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_timeline(request=_req(), user=_founder())
    assert {"period_dana", "timeline", "peak_dau", "peak_datum"}.issubset(result.keys())


@pytest.mark.anyio
async def test_timeline_length_matches_period():
    from routers.product_intelligence import pi_timeline
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_timeline(request=_req(), user=_founder(), dana=30)
    assert len(result["timeline"]) == 30


@pytest.mark.anyio
async def test_timeline_each_entry_has_datum_dau_events():
    from routers.product_intelligence import pi_timeline
    supa = _make_supa([])
    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_timeline(request=_req(), user=_founder())
    for entry in result["timeline"]:
        assert "datum" in entry
        assert "dau" in entry
        assert "events" in entry


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Admin guard
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_require_admin_blocks_non_founder():
    from routers.product_intelligence import _require_admin
    from fastapi import HTTPException
    non_founder = {"user_id": "x", "email": "random@user.com"}
    with pytest.raises(HTTPException) as exc:
        await _require_admin(user=non_founder)
    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_require_admin_allows_founder():
    from routers.product_intelligence import _require_admin
    result = await _require_admin(user=_founder())
    assert result["email"] == _founder()["email"]


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Router registration
# ═══════════════════════════════════════════════════════════════════════════════

def test_all_pi_routes_registered():
    from routers.product_intelligence import router
    paths = {r.path for r in router.routes}
    assert "/admin/pi/overview" in paths
    assert "/admin/pi/features" in paths
    assert "/admin/pi/retention" in paths
    assert "/admin/pi/funnels" in paths
    assert "/admin/pi/timeline" in paths


def test_all_pi_routes_are_get():
    from routers.product_intelligence import router
    for r in router.routes:
        if r.path.startswith("/admin/pi/"):
            assert "GET" in r.methods
