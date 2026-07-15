# -*- coding: utf-8 -*-
"""
Tests for feature_registry.feature_type/chargeable (migracija 070) — Admin
Console wiring + scripts/validate_feature_registry.py's new consistency
checks. Covers the exact 3 conflict categories found while auditing the
Registry for the Pricing Modal redesign:
  A) Foundation Layer (predmeti_crud etc.) — never in Pricing table
  B) firm_memory/knowledge_hygiene — subscription perk, not chargeable
  C) placeholder Enterprise features — COMING_SOON, not advertised
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "PATCH", "headers": [], "query_string": b"",
             "path": "/api/admin/feature-registry/x", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _founder():
    return {"user_id": "f-1", "email": "benny13.n@gmail.com"}


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# Admin Console — feature_type / chargeable writable via PATCH
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_feature_registry_update_writes_feature_type():
    from routers.admin_dashboard import feature_registry_update, FeatureRegistryUpdate

    old_row = {"feature_key": "predmeti_crud", "feature_type": "SUBSCRIPTION"}
    supa = MagicMock()

    def _table(name):
        if name == "feature_registry":
            chain = _make_chain(old_row)
            chain.update = MagicMock(return_value=_make_chain([{"feature_key": "predmeti_crud", "feature_type": "FOUNDATION"}]))
            return chain
        return _make_chain([{"id": "audit-1"}])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.admin_dashboard._get_supa", return_value=supa), \
         patch("shared.feature_registry.invalidate"):
        result = await feature_registry_update(
            "predmeti_crud", FeatureRegistryUpdate(feature_type="FOUNDATION"), _req(), _founder()
        )
    assert result["azurirano"]["feature_type"] == "FOUNDATION"


@pytest.mark.anyio
async def test_feature_registry_update_rejects_invalid_feature_type():
    from routers.admin_dashboard import feature_registry_update, FeatureRegistryUpdate
    from fastapi import HTTPException

    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain({"feature_key": "x"}))

    with patch("routers.admin_dashboard._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await feature_registry_update("x", FeatureRegistryUpdate(feature_type="NOT_A_TYPE"), _req(), _founder())
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_feature_registry_update_writes_chargeable():
    from routers.admin_dashboard import feature_registry_update, FeatureRegistryUpdate

    supa = MagicMock()

    def _table(name):
        if name == "feature_registry":
            chain = _make_chain({"feature_key": "firm_memory"})
            chain.update = MagicMock(return_value=_make_chain([{"feature_key": "firm_memory", "chargeable": False}]))
            return chain
        return _make_chain([{"id": "audit-1"}])
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.admin_dashboard._get_supa", return_value=supa), \
         patch("shared.feature_registry.invalidate"):
        result = await feature_registry_update(
            "firm_memory", FeatureRegistryUpdate(chargeable=False, krediti=0), _req(), _founder()
        )
    assert result["azurirano"]["chargeable"] is False
    assert result["azurirano"]["krediti"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# validate_feature_registry.py — new consistency checks
# ═══════════════════════════════════════════════════════════════════════════

def _import_validator():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "validate_feature_registry.py")
    spec = importlib.util.spec_from_file_location("validate_feature_registry", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_foundation_with_credits_warns():
    mod = _import_validator()
    row = {
        "feature_key": "predmeti_crud", "naziv": "Predmeti", "kategorija": "crm",
        "minimum_plan": "basic", "addon": None, "krediti": 2, "status": "ACTIVE",
        "visible": "visible", "priority": "MEDIUM", "opis": "x",
        "feature_type": "FOUNDATION", "chargeable": True,
    }
    findings = mod._validate_row(row)
    assert any("FOUNDATION ali krediti" in msg for sev, msg in findings if sev == "WARNING")


def test_chargeable_false_with_credits_is_fatal_contradiction():
    mod = _import_validator()
    row = {
        "feature_key": "firm_memory", "naziv": "Law Firm Brain", "kategorija": "znanje",
        "minimum_plan": "professional", "addon": None, "krediti": 1, "status": "ACTIVE",
        "visible": "visible", "priority": "MEDIUM", "opis": "x",
        "feature_type": "SUBSCRIPTION", "chargeable": False,
    }
    findings = mod._validate_row(row)
    assert any(sev == "FATAL" and "kontradiktorno" in msg for sev, msg in findings)


def test_chargeable_false_with_zero_credits_is_clean():
    mod = _import_validator()
    row = {
        "feature_key": "firm_memory", "naziv": "Law Firm Brain", "kategorija": "znanje",
        "minimum_plan": "professional", "addon": None, "krediti": 0, "status": "ACTIVE",
        "visible": "visible", "priority": "MEDIUM", "opis": "x",
        "feature_type": "SUBSCRIPTION", "chargeable": False, "business_group_id": "g5",
    }
    findings = mod._validate_row(row)
    assert not any(sev == "FATAL" for sev, msg in findings)


def test_addon_type_without_addon_field_warns():
    mod = _import_validator()
    row = {
        "feature_key": "da_aml_audit", "naziv": "AML", "kategorija": "digital_assets",
        "minimum_plan": None, "addon": None, "krediti": 1, "status": "ACTIVE",
        "visible": "visible", "priority": "MEDIUM", "opis": "x",
        "feature_type": "ADDON", "chargeable": True,
    }
    findings = mod._validate_row(row)
    assert any("ADDON ali addon polje" in msg for sev, msg in findings if sev == "WARNING")


def test_invalid_feature_type_is_fatal():
    mod = _import_validator()
    row = {
        "feature_key": "x", "naziv": "X", "kategorija": "crm",
        "minimum_plan": "basic", "addon": None, "krediti": 0, "status": "ACTIVE",
        "visible": "visible", "priority": "MEDIUM", "opis": "x",
        "feature_type": "NOT_REAL", "chargeable": True,
    }
    findings = mod._validate_row(row)
    assert any(sev == "FATAL" and "feature_type=" in msg for sev, msg in findings)
