# -*- coding: utf-8 -*-
"""
Tests for shared/business_groups.py + Admin Business Groups Console (routers/
admin_dashboard.py) + GET /api/plan/pricing-matrix (routers/plans.py) —
migracija 071.

Verifies business_groups je genuinski jedini izvor grupisanja za Pricing
Modal: reader service, cache invalidation, Admin Console PATCH mirrors
Tier Config's pattern, i da je pricing-matrix IZVEDENA (join u letu) —
FOUNDATION i COMING_SOON funkcije se nikad ne pojavljuju, svaka funkcija
se pojavljuje u tačno jednoj grupi.
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
             "path": "/api/admin/business-groups", "app": MagicMock(), "state": MagicMock()}
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
# shared/business_groups.py — reader service
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_group_reads_from_cache_after_load():
    import shared.business_groups as bg
    bg._CACHE = {}
    bg._CACHE_LOADED_AT = 0.0

    rows = [
        {"id": "g1", "key": "ai_pravna_analiza", "display_name": "AI pravna analiza", "display_order": 1},
        {"id": "g2", "key": "strategija_predmeta", "display_name": "Strategija predmeta", "display_order": 2},
    ]
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))

    with patch("shared.business_groups._get_supa", return_value=supa):
        group = await bg.get_group("strategija_predmeta")

    assert group["id"] == "g2"
    assert group["display_name"] == "Strategija predmeta"


@pytest.mark.anyio
async def test_get_group_rejects_unknown_key():
    import shared.business_groups as bg
    bg._CACHE = {"x": {"key": "x"}}
    bg._CACHE_LOADED_AT = 999999999.0
    with pytest.raises(RuntimeError):
        await bg.get_group("nonexistent_group")


@pytest.mark.anyio
async def test_get_all_groups_sorted_by_display_order():
    import shared.business_groups as bg
    bg._CACHE = {}
    bg._CACHE_LOADED_AT = 0.0

    rows = [
        {"id": "g3", "key": "c", "display_order": 3},
        {"id": "g1", "key": "a", "display_order": 1},
        {"id": "g2", "key": "b", "display_order": 2},
    ]
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))

    with patch("shared.business_groups._get_supa", return_value=supa):
        groups = await bg.get_all_groups()

    assert [g["key"] for g in groups] == ["a", "b", "c"]


@pytest.mark.anyio
async def test_invalidate_forces_reload():
    import shared.business_groups as bg
    bg._CACHE = {"a": {"key": "a", "display_name": "Old"}}
    bg._CACHE_LOADED_AT = 999999999.0

    rows = [{"id": "g1", "key": "a", "display_name": "New"}]
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(rows))

    bg.invalidate()
    with patch("shared.business_groups._get_supa", return_value=supa):
        group = await bg.get_group("a")

    assert group["display_name"] == "New"


# ═══════════════════════════════════════════════════════════════════════════
# Admin Business Groups Console — GET/PATCH mirror Tier Config's pattern
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_business_groups_list_founder_only():
    from routers.admin_dashboard import business_groups_list
    with pytest.raises(Exception):  # HTTPException 403 from _require_founder
        await business_groups_list(_req(), user={"user_id": "x", "email": "not-founder@test.rs"})


@pytest.mark.anyio
async def test_business_groups_update_writes_and_invalidates_and_audits():
    from routers.admin_dashboard import business_groups_update, BusinessGroupUpdate

    old_row = {"key": "ai_pravna_analiza", "display_name": "AI pravna analiza"}
    supa = MagicMock()

    def _table(name):
        if name == "business_groups":
            chain = _make_chain(old_row)
            chain.update = MagicMock(return_value=_make_chain([{"key": "ai_pravna_analiza", "display_name": "AI Pravna Analiza (v2)"}]))
            return chain
        if name == "business_groups_audit":
            return _make_chain([{"id": "audit-1"}])
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.admin_dashboard._get_supa", return_value=supa), \
         patch("shared.business_groups.invalidate") as mock_invalidate:
        result = await business_groups_update(
            "ai_pravna_analiza", BusinessGroupUpdate(display_name="AI Pravna Analiza (v2)"), _req(), _founder()
        )

    assert result["azurirano"]["display_name"] == "AI Pravna Analiza (v2)"
    mock_invalidate.assert_called_once()

    audit_calls = [c for c in supa.table.call_args_list if c.args[0] == "business_groups_audit"]
    assert len(audit_calls) == 1


@pytest.mark.anyio
async def test_business_groups_update_rejects_unknown_group():
    from routers.admin_dashboard import business_groups_update, BusinessGroupUpdate
    from fastapi import HTTPException

    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(None))

    with patch("routers.admin_dashboard._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await business_groups_update("not_a_group", BusinessGroupUpdate(display_name="x"), _req(), _founder())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_business_groups_update_no_fields_rejected():
    from routers.admin_dashboard import business_groups_update, BusinessGroupUpdate
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await business_groups_update("ai_pravna_analiza", BusinessGroupUpdate(), _req(), _founder())
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_feature_registry_update_writes_business_group_id():
    from routers.admin_dashboard import feature_registry_update, FeatureRegistryUpdate

    old_row = {"feature_key": "case_dna", "business_group_id": None}
    supa = MagicMock()

    def _table(name):
        if name == "feature_registry":
            chain = _make_chain(old_row)
            chain.update = MagicMock(return_value=_make_chain([{"feature_key": "case_dna", "business_group_id": "g3"}]))
            return chain
        return _make_chain([{"id": "audit-1"}])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.admin_dashboard._get_supa", return_value=supa), \
         patch("shared.feature_registry.invalidate"):
        result = await feature_registry_update(
            "case_dna", FeatureRegistryUpdate(business_group_id="g3"), _req(), _founder()
        )
    assert result["azurirano"]["business_group_id"] == "g3"


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/plan/pricing-matrix — derived join, not a stored table
# ═══════════════════════════════════════════════════════════════════════════

def _policy(key, naziv, feature_type, status, visible, group_id, minimum_plan="professional", addon=None, krediti=1):
    return {
        "feature_key": key, "naziv": naziv, "opis": "x", "feature_type": feature_type,
        "status": status, "visible": visible, "business_group_id": group_id,
        "minimum_plan": minimum_plan, "addon": addon, "krediti": krediti,
    }


@pytest.mark.anyio
async def test_pricing_matrix_groups_features_correctly():
    from routers.plans import pricing_matrix

    groups = [
        {"id": "g1", "key": "ai_pravna_analiza", "display_name": "AI pravna analiza", "description": "d1", "display_order": 1, "visible": True},
        {"id": "g2", "key": "strategija_predmeta", "display_name": "Strategija predmeta", "description": "d2", "display_order": 2, "visible": True},
    ]
    policies = [
        _policy("ai_pravna_pitanja", "AI pravna pitanja", "SUBSCRIPTION", "ACTIVE", "visible", "g1"),
        _policy("strategija", "Strategija", "SUBSCRIPTION", "ACTIVE", "visible", "g2"),
    ]

    with patch("routers.plans.get_all_groups", new=AsyncMock(return_value=groups)), \
         patch("routers.plans.get_all_policies", new=AsyncMock(return_value=policies)):
        result = await pricing_matrix()

    keys = [g["key"] for g in result["grupe"]]
    assert keys == ["ai_pravna_analiza", "strategija_predmeta"]
    assert result["grupe"][0]["broj_funkcija"] == 1
    assert result["grupe"][0]["funkcije"][0]["feature_key"] == "ai_pravna_pitanja"


@pytest.mark.anyio
async def test_pricing_matrix_excludes_foundation_and_coming_soon():
    from routers.plans import pricing_matrix

    groups = [{"id": "g6", "key": "upravljanje_kancelarijom", "display_name": "Upravljanje kancelarijom", "display_order": 6, "visible": True}]
    policies = [
        _policy("crm", "CRM osnovno", "FOUNDATION", "ACTIVE", "visible", None),
        _policy("api_external", "Eksterni API", "SUBSCRIPTION", "COMING_SOON", "visible", None),
        _policy("conflict_check", "Provera sukoba interesa", "SUBSCRIPTION", "ACTIVE", "visible", "g6"),
    ]

    with patch("routers.plans.get_all_groups", new=AsyncMock(return_value=groups)), \
         patch("routers.plans.get_all_policies", new=AsyncMock(return_value=policies)):
        result = await pricing_matrix()

    all_keys = [f["feature_key"] for g in result["grupe"] for f in g["funkcije"]]
    assert "crm" not in all_keys
    assert "api_external" not in all_keys
    assert "conflict_check" in all_keys


@pytest.mark.anyio
async def test_pricing_matrix_no_feature_in_two_groups():
    from routers.plans import pricing_matrix

    groups = [
        {"id": "g1", "key": "a", "display_name": "A", "display_order": 1, "visible": True},
        {"id": "g2", "key": "b", "display_name": "B", "display_order": 2, "visible": True},
    ]
    # Same feature_key can only carry ONE business_group_id in the registry —
    # this proves the matrix reflects that (single membership), not a fan-out.
    policies = [_policy("x", "X", "SUBSCRIPTION", "ACTIVE", "visible", "g1")]

    with patch("routers.plans.get_all_groups", new=AsyncMock(return_value=groups)), \
         patch("routers.plans.get_all_policies", new=AsyncMock(return_value=policies)):
        result = await pricing_matrix()

    occurrences = [f["feature_key"] for g in result["grupe"] for f in g["funkcije"] if f["feature_key"] == "x"]
    assert len(occurrences) == 1


@pytest.mark.anyio
async def test_pricing_matrix_includes_addon_group():
    from routers.plans import pricing_matrix

    groups = [{"id": "g7", "key": "digitalna_imovina", "display_name": "Digitalna imovina & usklađenost", "display_order": 7, "visible": True}]
    policies = [_policy("da_aml_audit", "AML/KYC revizija", "ADDON", "ACTIVE", "visible", "g7", minimum_plan=None, addon="digital_assets")]

    with patch("routers.plans.get_all_groups", new=AsyncMock(return_value=groups)), \
         patch("routers.plans.get_all_policies", new=AsyncMock(return_value=policies)):
        result = await pricing_matrix()

    assert result["grupe"][0]["funkcije"][0]["feature_key"] == "da_aml_audit"


# ═══════════════════════════════════════════════════════════════════════════
# validate_feature_registry.py — business_group_id consistency checks
# ═══════════════════════════════════════════════════════════════════════════

def _import_validator():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "validate_feature_registry.py")
    spec = importlib.util.spec_from_file_location("validate_feature_registry", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_row(**overrides):
    row = {
        "feature_key": "x", "naziv": "X", "kategorija": "litigation",
        "minimum_plan": "professional", "addon": None, "krediti": 1, "status": "ACTIVE",
        "visible": "visible", "priority": "MEDIUM", "opis": "x",
        "feature_type": "SUBSCRIPTION", "chargeable": True, "business_group_id": "g3",
    }
    row.update(overrides)
    return row


def test_active_subscription_without_business_group_is_fatal():
    mod = _import_validator()
    findings = mod._validate_row(_base_row(business_group_id=None))
    assert any(sev == "FATAL" and "business_group_id je prazan" in msg for sev, msg in findings)


def test_active_subscription_with_business_group_is_clean():
    mod = _import_validator()
    findings = mod._validate_row(_base_row())
    assert not any("business_group_id" in msg for sev, msg in findings)


def test_foundation_with_business_group_warns():
    mod = _import_validator()
    findings = mod._validate_row(_base_row(feature_type="FOUNDATION", krediti=0, business_group_id="g6"))
    assert any(sev == "WARNING" and "FOUNDATION ali business_group_id" in msg for sev, msg in findings)


def test_coming_soon_with_business_group_warns():
    mod = _import_validator()
    findings = mod._validate_row(_base_row(status="COMING_SOON", business_group_id="g8"))
    assert any(sev == "WARNING" and "COMING_SOON ali business_group_id" in msg for sev, msg in findings)
