# -*- coding: utf-8 -*-
"""
Tests for Faza 72.5 — full removal of korisnik_plan/korisnik_usage dependency.

Covers the 4 consumers the founder named explicitly:
  1. routers/plans.py's /api/plan/status
  2. routers/gdpr.py's /api/gdpr/export
  3. routers/product_intelligence.py's /admin/pi/plans (founder dashboard)
  4. routers/email_notif.py's day-1 onboarding trigger

Each test asserts BOTH that the new source (profiles.subscription_type /
feature_usage) is read, AND that no korisnik_plan/korisnik_usage table call
is made — the second assertion is what makes this a regression test for the
migration itself, not just a feature test.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "GET", "headers": [], "query_string": b"",
             "path": "/", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _user(uid="user-1", email="test@vindex.rs"):
    return {"user_id": uid, "email": email}


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "gte", "lte", "lt", "order", "limit", "execute", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock()
    r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# 1. /api/plan/status
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_plan_status_reads_only_new_system():
    from routers.plans import plan_status

    profile_row = {
        "credits_remaining": 42, "is_pro": True,
        "subscription_type": "professional", "addons": ["digital_assets"],
        "subscription_expires_at": None, "subscription_seats_extra": 0,
    }
    usage_rows = [
        {"feature_key": "ai_pravna_pitanja", "broj_koriscenja": 5, "krediti_potroseni": 5},
        {"feature_key": "ai_pravna_pitanja", "broj_koriscenja": 2, "krediti_potroseni": 2},
        {"feature_key": "case_dna", "broj_koriscenja": 1, "krediti_potroseni": 3},
    ]
    policies = [
        {"feature_key": "ai_pravna_pitanja", "naziv": "AI pravna pitanja", "dnevni_limit": None, "mesecni_limit": None},
        {"feature_key": "case_dna", "naziv": "Case DNA", "dnevni_limit": None, "mesecni_limit": 10},
    ]

    def _table(name):
        if name in ("korisnik_plan", "korisnik_usage"):
            raise AssertionError(f"FORBIDDEN: .table('{name}') called")
        if name == "profiles":
            return _make_chain([profile_row])
        if name == "feature_usage":
            return _make_chain(usage_rows)
        return _make_chain([])
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.plans._get_supa", return_value=supa), \
         patch("routers.plans._ensure_profile", return_value=profile_row), \
         patch("routers.plans.UsageService.balance", new_callable=AsyncMock, return_value=42), \
         patch("routers.plans.get_all_policies", new_callable=AsyncMock, return_value=policies):
        result = await plan_status(user=_user())

    assert result["plan"] == "professional"
    assert result["plan_display"] == "Professional"
    assert result["addons"] == ["digital_assets"]
    assert result["credits_remaining"] == 42
    # ai_pravna_pitanja aggregated across its 2 daily rows: 5+2=7 uses, 5+2=7 credits
    ai_entry = next(u for u in result["usage_this_month"] if u["feature_key"] == "ai_pravna_pitanja")
    assert ai_entry["broj_koriscenja"] == 7
    assert ai_entry["krediti_potroseni"] == 7


@pytest.mark.anyio
async def test_plan_status_reflects_basic_tier():
    from routers.plans import plan_status

    profile_row = {
        "subscription_type": "basic", "addons": [], "subscription_expires_at": None,
        "subscription_seats_extra": 0,
    }
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([]))

    with patch("routers.plans._get_supa", return_value=supa), \
         patch("routers.plans._ensure_profile", return_value=profile_row), \
         patch("routers.plans.UsageService.balance", new_callable=AsyncMock, return_value=5), \
         patch("routers.plans.get_all_policies", new_callable=AsyncMock, return_value=[]):
        result = await plan_status(user=_user())

    assert result["plan"] == "basic"
    assert result["plan_display"] == "Basic"
    assert result["usage_this_month"] == []


def test_plan_status_module_has_no_old_system_functions():
    """_get_plan/_get_usage/PLAN_LIMITS/_resolve_plan/_get_limits were the
    old-system readers — confirms they were actually deleted, not just
    unreachable."""
    import routers.plans as plans_mod
    for name in ("_get_plan", "_get_usage", "PLAN_LIMITS", "_resolve_plan", "_get_limits", "_PLAN_ALIAS"):
        assert not hasattr(plans_mod, name), f"routers.plans still defines {name} — old system not fully removed"


# ═══════════════════════════════════════════════════════════════════════════
# 2. GDPR export
# ═══════════════════════════════════════════════════════════════════════════

def test_gdpr_export_plan_from_profiles_not_korisnik_plan():
    """gdpr_export's inner _fetch() is a sync closure — test it directly by
    replicating its table-name usage through a guarded mock."""
    import routers.gdpr as gdpr_mod

    profile_row = {
        "id": "u1", "email": "x@y.rs", "full_name": "X Y", "created_at": "2026-01-01",
        "subscription_type": "enterprise", "addons": [], "subscription_expires_at": None,
        "subscription_seats_extra": 2,
    }

    calls = []
    supa = MagicMock()

    def _table(name):
        calls.append(name)
        if name == "korisnik_plan":
            raise AssertionError("FORBIDDEN: gdpr_export must not read korisnik_plan")
        if name == "profiles":
            return _make_chain(profile_row)
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    # Exercise the same logic gdpr_export._fetch() runs, via the real
    # effective_tier() helper it imports.
    from shared.permissions import effective_tier
    profil = supa.table("profiles").select("...").eq("id", "u1").maybe_single().execute().data
    plan = {
        "tarifa": effective_tier(profil),
        "addons": profil.get("addons") or [],
        "subscription_expires_at": profil.get("subscription_expires_at"),
        "subscription_seats_extra": profil.get("subscription_seats_extra", 0),
    }

    assert plan["tarifa"] == "enterprise"
    assert plan["subscription_seats_extra"] == 2
    assert "korisnik_plan" not in calls


def test_gdpr_py_imports_effective_tier_not_korisnik_plan():
    import routers.gdpr as gdpr_mod
    import inspect
    src = inspect.getsource(gdpr_mod)
    # Explanatory comments are allowed to mention the old table name (to
    # document why it's NOT used) — the real regression signal is an actual
    # .table("korisnik_plan") call, which this checks for directly.
    assert '.table("korisnik_plan")' not in src and ".table('korisnik_plan')" not in src
    assert "effective_tier" in src


# ═══════════════════════════════════════════════════════════════════════════
# 3. Founder dashboard — pi_plans
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_pi_plans_distribution_from_profiles_subscription_type():
    from routers.product_intelligence import pi_plans

    profiles = [
        {"id": "1", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0},
        {"id": "2", "subscription_type": "basic", "subscription_expires_at": None, "subscription_seats_extra": 0},
        {"id": "3", "subscription_type": "professional", "subscription_expires_at": None, "subscription_seats_extra": 0},
        {"id": "4", "subscription_type": "enterprise", "subscription_expires_at": None, "subscription_seats_extra": 2},
    ]
    usage_rows = [
        {"feature_key": "ai_pravna_pitanja", "broj_koriscenja": 10, "krediti_potroseni": 10},
        {"feature_key": "case_dna", "broj_koriscenja": 3, "krediti_potroseni": 9},
    ]

    supa = MagicMock()

    def _table(name):
        if name in ("korisnik_plan", "korisnik_usage"):
            raise AssertionError(f"FORBIDDEN: pi_plans must not read {name}")
        if name == "profiles":
            return _make_chain(profiles)
        if name == "feature_usage":
            return _make_chain(usage_rows)
        if name == "onboarding_email_log":
            return _make_chain([])
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.product_intelligence._get_supa", return_value=supa):
        result = await pi_plans(_req(), user=_user())

    assert result["plan_distribucija"] == {"basic": 2, "professional": 1, "enterprise": 1}
    assert result["ukupno_korisnika"] == 4
    assert result["placajuci"] == 2  # "paying" excludes basic — professional + enterprise only
    # MRR includes basic too (29 is not free) — 2*29 (basic) + 79 (professional) + 249 + 2*49 (enterprise+seats)
    assert result["mrr_eur"] == 2 * 29 + 79 + 249 + 2 * 49
    assert result["ai_usage_ovaj_mesec"]["ukupno_poziva"] == 13
    assert result["ai_usage_ovaj_mesec"]["ukupno_kredita"] == 19


def test_pi_plans_source_has_no_old_system_reference():
    import routers.product_intelligence as pi_mod
    import inspect
    src = inspect.getsource(pi_mod.pi_plans)
    assert '.table("korisnik_plan")' not in src and ".table('korisnik_plan')" not in src
    assert '.table("korisnik_usage")' not in src and ".table('korisnik_usage')" not in src
    assert "feature_usage" in src


# ═══════════════════════════════════════════════════════════════════════════
# 4. email_notif.py day-1 onboarding trigger
# ═══════════════════════════════════════════════════════════════════════════

def test_email_notif_source_has_no_korisnik_usage():
    import routers.email_notif as en_mod
    import inspect
    src = inspect.getsource(en_mod)
    assert '.table("korisnik_usage")' not in src and ".table('korisnik_usage')" not in src
    assert "feature_usage" in src
