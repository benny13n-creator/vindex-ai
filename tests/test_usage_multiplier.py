# -*- coding: utf-8 -*-
"""
Tests for shared/usage.py's UsageService.consume() multiplier resolution —
Tier Configuration priority #2 (Feature Registry credit_multiplier, migracija
069). Confirms:
  - multiplier=None (default) reads feature_registry.credit_multiplier
  - explicit multiplier= overrides the registry value (dynamic cases, e.g.
    multi_agent.py's per-call agent count)
  - a feature with credit_multiplier absent/1 behaves exactly as before
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _policy(krediti=1, credit_multiplier=1, **extra):
    base = {
        "krediti": krediti, "credit_multiplier": credit_multiplier,
        "dnevni_limit": None, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o", "estimated_cost_usd": None,
    }
    base.update(extra)
    return base


@pytest.mark.anyio
async def test_consume_uses_registry_credit_multiplier_by_default():
    from shared.usage import UsageService
    policy = _policy(krediti=2, credit_multiplier=6)  # e.g. strategija: 2 kredita base, 6x for kompletna_analiza row

    with patch("shared.usage.get_policy", new_callable=AsyncMock, return_value=policy), \
         patch("shared.usage._is_founder", return_value=False), \
         patch("shared.usage._get_credits", return_value=100), \
         patch("shared.usage._deduct_n_credits", return_value=88) as mock_deduct, \
         patch("shared.usage._increment_usage", new_callable=AsyncMock), \
         patch("shared.usage._log_usage_event", new_callable=AsyncMock), \
         patch("shared.usage._seconds_since_last_call", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_usage_row", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_monthly_count", new_callable=AsyncMock, return_value=0):
        preostalo = await UsageService.consume("uid-1", "test@vindex.rs", "strategija")

    # 2 krediti base * 6 (registry multiplier, NOT passed by caller) = 12
    mock_deduct.assert_called_once_with("uid-1", "test@vindex.rs", 12)
    assert preostalo == 88


@pytest.mark.anyio
async def test_consume_explicit_multiplier_overrides_registry():
    """Dynamic case (e.g. multi_agent.py's n_needed) — explicit multiplier=
    must win over whatever the registry has, since it's computed at runtime."""
    from shared.usage import UsageService
    policy = _policy(krediti=1, credit_multiplier=6)  # registry says 6, caller overrides to 3

    with patch("shared.usage.get_policy", new_callable=AsyncMock, return_value=policy), \
         patch("shared.usage._is_founder", return_value=False), \
         patch("shared.usage._get_credits", return_value=100), \
         patch("shared.usage._deduct_n_credits", return_value=97) as mock_deduct, \
         patch("shared.usage._increment_usage", new_callable=AsyncMock), \
         patch("shared.usage._log_usage_event", new_callable=AsyncMock), \
         patch("shared.usage._seconds_since_last_call", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_usage_row", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_monthly_count", new_callable=AsyncMock, return_value=0):
        await UsageService.consume("uid-1", "test@vindex.rs", "multi_agent", multiplier=3)

    mock_deduct.assert_called_once_with("uid-1", "test@vindex.rs", 3)


@pytest.mark.anyio
async def test_consume_explicit_multiplier_1_overrides_registry_down():
    """The digital_twin sta_ako / strategija single-module case: registry has
    a >1 multiplier for the feature_key's expensive variant, but this call is
    the cheap variant and must explicitly force multiplier=1."""
    from shared.usage import UsageService
    policy = _policy(krediti=3, credit_multiplier=3)  # digital_twin: 3 kredita, registry multiplier=3 for kreiraj_simulaciju

    with patch("shared.usage.get_policy", new_callable=AsyncMock, return_value=policy), \
         patch("shared.usage._is_founder", return_value=False), \
         patch("shared.usage._get_credits", return_value=100), \
         patch("shared.usage._deduct_n_credits", return_value=97) as mock_deduct, \
         patch("shared.usage._increment_usage", new_callable=AsyncMock), \
         patch("shared.usage._log_usage_event", new_callable=AsyncMock), \
         patch("shared.usage._seconds_since_last_call", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_usage_row", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_monthly_count", new_callable=AsyncMock, return_value=0):
        await UsageService.consume("uid-1", "test@vindex.rs", "digital_twin", multiplier=1)

    # 3 krediti base * 1 (explicit override, NOT registry's 3) = 3
    mock_deduct.assert_called_once_with("uid-1", "test@vindex.rs", 3)


@pytest.mark.anyio
async def test_consume_no_multiplier_field_defaults_to_1():
    """A feature_registry row without credit_multiplier at all (e.g. before
    migration 069 backfilled the default) must behave exactly like multiplier=1 —
    no regression for the ~66 features that never had a multiplier concept."""
    from shared.usage import UsageService
    policy = {
        "krediti": 5, "dnevni_limit": None, "mesecni_limit": None,
        "cooldown_seconds": None, "ai_model": "gpt-4o", "estimated_cost_usd": None,
        # no "credit_multiplier" key at all
    }

    with patch("shared.usage.get_policy", new_callable=AsyncMock, return_value=policy), \
         patch("shared.usage._is_founder", return_value=False), \
         patch("shared.usage._get_credits", return_value=100), \
         patch("shared.usage._deduct_n_credits", return_value=95) as mock_deduct, \
         patch("shared.usage._increment_usage", new_callable=AsyncMock), \
         patch("shared.usage._log_usage_event", new_callable=AsyncMock), \
         patch("shared.usage._seconds_since_last_call", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_usage_row", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_monthly_count", new_callable=AsyncMock, return_value=0):
        await UsageService.consume("uid-1", "test@vindex.rs", "case_dna")

    mock_deduct.assert_called_once_with("uid-1", "test@vindex.rs", 5)
