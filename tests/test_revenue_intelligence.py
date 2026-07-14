# -*- coding: utf-8 -*-
"""
Tests for routers/product_intelligence.py's pi_revenue_intelligence (Faza
Revenue Intelligence, Priority #3). Every section must be computed from
real tables — no fabricated numbers, honest zero/empty states where data
doesn't exist yet (feature_usage/feature_usage_log had zero rows platform-
wide when this was built).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
             "path": "/admin/pi/revenue-intelligence", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _founder():
    return {"user_id": "f-1", "email": "benny13.n@gmail.com"}


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "gte", "lte", "order", "limit", "execute"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


_TIERS = [
    {"tier_key": "basic", "monthly_price_eur": 29, "extra_seat_price_eur": None},
    {"tier_key": "professional", "monthly_price_eur": 79, "extra_seat_price_eur": None},
    {"tier_key": "enterprise", "monthly_price_eur": 249, "extra_seat_price_eur": 49},
]

_POLICIES = [
    {"feature_key": "case_dna", "naziv": "Case DNA", "status": "ACTIVE", "krediti": 3, "mesecni_limit": 10},
    {"feature_key": "strategija", "naziv": "Strategija", "status": "ACTIVE", "krediti": 1, "mesecni_limit": None},
    {"feature_key": "predmeti_crud", "naziv": "Predmeti", "status": "ACTIVE", "krediti": 0, "mesecni_limit": None},
]


def _mock_supa(profiles, feature_usage_log=None, feature_usage_month=None, feature_usage_30d=None):
    supa = MagicMock()
    feature_usage_call_count = {"n": 0}

    def _table(name):
        if name == "profiles":
            return _make_chain(profiles)
        if name == "feature_usage_log":
            return _make_chain(feature_usage_log or [])
        if name == "feature_usage":
            # First .table("feature_usage") call in the endpoint is the monthly
            # upgrade-candidate query (eq mesec), second is the 30-day unused-
            # features query (gte dan) — counter lives outside _table() so it
            # persists across both separate .table() invocations.
            feature_usage_call_count["n"] += 1
            if feature_usage_call_count["n"] == 1:
                return _make_chain(feature_usage_month or [])
            return _make_chain(feature_usage_30d or [])
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)
    return supa


async def _call(supa, tiers=_TIERS, policies=_POLICIES):
    from routers.product_intelligence import pi_revenue_intelligence
    with patch("routers.product_intelligence._get_supa", return_value=supa), \
         patch("shared.tier_config.get_all_tiers", new_callable=AsyncMock, return_value=tiers), \
         patch("shared.feature_registry.get_all_policies", new_callable=AsyncMock, return_value=policies):
        return await pi_revenue_intelligence(_req(), user=_founder())


# ═══════════════════════════════════════════════════════════════════════════
# Revenue
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_revenue_mrr_from_real_tier_distribution():
    profiles = [
        {"id": "1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0},
        {"id": "2", "subscription_type": "professional", "subscription_expires_at": None, "subscription_seats_extra": 0},
        {"id": "3", "subscription_type": "enterprise", "subscription_expires_at": None, "subscription_seats_extra": 1},
    ]
    supa = _mock_supa(profiles)
    result = await _call(supa)

    # 29 (basic) + 79 (professional) + 249 + 49 (enterprise + 1 extra seat) = 406
    assert result["revenue"]["mrr_eur"] == 406.0
    assert result["revenue"]["arr_eur"] == 406.0 * 12


@pytest.mark.anyio
async def test_revenue_run_rate_is_labeled_not_actual_billing():
    supa = _mock_supa([])
    result = await _call(supa)
    assert "Stripe nije integrisan" in result["revenue"]["napomena"]
    assert result["revenue"]["mrr_eur"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# AI Cost — must be genuinely zero/empty when no usage exists, not fabricated
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_ai_cost_honestly_zero_with_no_usage_log_rows():
    supa = _mock_supa([])
    result = await _call(supa)
    assert result["ai_cost"]["mtd_usd"] == 0.0
    assert result["ai_cost"]["danas_usd"] == 0.0
    assert result["ai_cost"]["po_modelu"] == {}
    assert result["top_profitabilne_funkcije"] == []
    assert result["top_skupe_funkcije"] == []


@pytest.mark.anyio
async def test_ai_cost_aggregates_real_log_rows():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00")
    log_rows = [
        {"feature_key": "case_dna", "ai_model": "gpt-4o", "estimated_cost_usd": 0.05, "krediti_potroseni": 3, "created_at": now_iso},
        {"feature_key": "case_dna", "ai_model": "gpt-4o", "estimated_cost_usd": 0.03, "krediti_potroseni": 3, "created_at": now_iso},
        {"feature_key": "strategija", "ai_model": "gpt-4o-mini", "estimated_cost_usd": 0.01, "krediti_potroseni": 1, "created_at": now_iso},
    ]
    supa = _mock_supa([], feature_usage_log=log_rows)
    result = await _call(supa)

    assert result["ai_cost"]["mtd_usd"] == pytest.approx(0.09)
    assert result["ai_cost"]["po_modelu"]["gpt-4o"] == pytest.approx(0.08)
    assert result["ai_cost"]["po_modelu"]["gpt-4o-mini"] == pytest.approx(0.01)

    case_dna_entry = next(f for f in result["top_skupe_funkcije"] if f["feature_key"] == "case_dna")
    assert case_dna_entry["pozivi_ovaj_mesec"] == 2
    assert case_dna_entry["trosak_usd"] == pytest.approx(0.08)


@pytest.mark.anyio
async def test_profit_margin_reflects_real_cost_vs_revenue():
    profiles = [{"id": "1", "subscription_type": "professional", "subscription_expires_at": None, "subscription_seats_extra": 0}]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00")
    log_rows = [{"feature_key": "case_dna", "ai_model": "gpt-4o", "estimated_cost_usd": 10.0, "krediti_potroseni": 3, "created_at": now_iso}]
    supa = _mock_supa(profiles, feature_usage_log=log_rows)
    result = await _call(supa)

    assert result["revenue"]["mrr_eur"] == 79.0
    # gross_profit = mrr_eur - (ai_cost_usd * 0.93)
    assert result["profit"]["gross_profit_eur"] == pytest.approx(79.0 - 10.0 * 0.93)


# ═══════════════════════════════════════════════════════════════════════════
# Conversion — snapshot, NOT a fabricated conversion rate
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_conversion_is_snapshot_not_fake_rate():
    profiles = [
        {"id": "1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0},
        {"id": "2", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0},
    ]
    supa = _mock_supa(profiles)
    result = await _call(supa)

    assert result["conversion"]["distribucija"] == {"basic": 2, "professional": 0, "enterprise": 0}
    assert "ne stopa konverzije" in result["conversion"]["napomena"]
    assert "subscription_history" in result["conversion"]["napomena"]


# ═══════════════════════════════════════════════════════════════════════════
# Upgrade candidates
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_upgrade_candidate_flagged_at_80_percent_of_limit():
    profiles = [{"id": "u1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0}]
    # case_dna has mesecni_limit=10 in _POLICIES; 8/10 = 80% -> flagged
    usage_month = [{"user_id": "u1", "feature_key": "case_dna", "broj_koriscenja": 8}]
    supa = _mock_supa(profiles, feature_usage_month=usage_month)
    result = await _call(supa)

    assert len(result["upgrade_candidates"]) == 1
    cand = result["upgrade_candidates"][0]
    assert cand["user_id"] == "u1"
    assert cand["trenutna_tarifa"] == "basic"
    assert cand["predlog_tarife"] == "professional"
    assert cand["iskoriscenost_pct"] == 80.0


@pytest.mark.anyio
async def test_not_upgrade_candidate_below_80_percent():
    profiles = [{"id": "u1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0}]
    usage_month = [{"user_id": "u1", "feature_key": "case_dna", "broj_koriscenja": 3}]  # 30%
    supa = _mock_supa(profiles, feature_usage_month=usage_month)
    result = await _call(supa)
    assert result["upgrade_candidates"] == []


@pytest.mark.anyio
async def test_no_limit_feature_never_flags_upgrade_candidate():
    """strategija has mesecni_limit=None — unlimited features can't trigger
    an upgrade suggestion regardless of usage volume."""
    profiles = [{"id": "u1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0}]
    usage_month = [{"user_id": "u1", "feature_key": "strategija", "broj_koriscenja": 500}]
    supa = _mock_supa(profiles, feature_usage_month=usage_month)
    result = await _call(supa)
    assert result["upgrade_candidates"] == []


@pytest.mark.anyio
async def test_projected_mrr_includes_upgrade_candidate_uplift():
    profiles = [{"id": "u1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0}]
    usage_month = [{"user_id": "u1", "feature_key": "case_dna", "broj_koriscenja": 9}]  # 90% -> candidate
    supa = _mock_supa(profiles, feature_usage_month=usage_month)
    result = await _call(supa)

    # mrr=29 (1 basic), projected = 29 + (79-29) if the 1 candidate converts
    assert result["revenue"]["mrr_eur"] == 29.0
    assert result["revenue"]["projected_mrr_eur"] == 29.0 + (79 - 29)


# ═══════════════════════════════════════════════════════════════════════════
# Unused features
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_unused_features_excludes_recently_used():
    supa = _mock_supa([], feature_usage_30d=[{"feature_key": "case_dna"}])
    result = await _call(supa)

    unused_keys = {f["feature_key"] for f in result["unused_features"]}
    assert "case_dna" not in unused_keys
    assert "strategija" in unused_keys  # never used in the 30d window


@pytest.mark.anyio
async def test_unused_features_excludes_zero_credit_features():
    """predmeti_crud has krediti=0 (not an AI feature) — must never appear
    in an 'unused AI feature' report regardless of usage."""
    supa = _mock_supa([])
    result = await _call(supa)
    unused_keys = {f["feature_key"] for f in result["unused_features"]}
    assert "predmeti_crud" not in unused_keys


# ═══════════════════════════════════════════════════════════════════════════
# Admin guard
# ═══════════════════════════════════════════════════════════════════════════

def test_revenue_intelligence_declares_require_admin_dependency():
    """pi_revenue_intelligence's user param defaults to Depends(_require_admin) —
    calling the endpoint directly (as every other test above does) bypasses
    FastAPI's DI and thus _require_admin itself, same as this codebase's
    established pattern elsewhere. _require_admin's own founder/non-founder
    behavior is already covered by test_product_intelligence.py's
    test_require_admin_blocks_non_founder / test_require_admin_allows_founder —
    this just confirms the endpoint actually wires that dependency in, not a
    different/missing guard."""
    import inspect
    from routers.product_intelligence import pi_revenue_intelligence, _require_admin
    sig = inspect.signature(pi_revenue_intelligence)
    user_param = sig.parameters["user"]
    assert user_param.default.dependency is _require_admin
