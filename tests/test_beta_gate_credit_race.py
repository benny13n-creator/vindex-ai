# -*- coding: utf-8 -*-
"""
Final Beta Gate — F5 (CRITICAL): deduct_n_credits had no balance-floor guard,
combined with a check-then-act TOCTOU in UsageService.consume, let concurrent
requests near/at exhaustion both "succeed" and get free AI usage on any
multiplier feature (strategija, multi_agent, strategy_simulator, digital_twin,
smart contract analyzer).

Fix: migrations/smart_contract_analyses.sql's deduct_n_credits RPC now has a
WHERE credits_remaining >= p_n guard (matching deduct_credit's own pattern)
and returns -1 (never a floored-at-0 value) when the deduction did not
happen. shared/deps.py::_deduct_n_credits propagates that -1 sentinel
faithfully instead of coercing failures to 0, and only increments monthly
usage on an actual successful deduction. shared/usage.py::UsageService.consume
already had a dormant `if preostalo < 0: raise 402` check that could never
fire before this fix — it fires now.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _policy(krediti=2, credit_multiplier=6, **extra):
    base = {
        "krediti": krediti, "credit_multiplier": credit_multiplier,
        "dnevni_limit": None, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o", "estimated_cost_usd": None,
    }
    base.update(extra)
    return base


# ─── SQL guard present in the migration file ──────────────────────────────

def _migration_107() -> str:
    path = os.path.join(
        os.path.dirname(__file__), "..", "migrations", "107_beta_gate_credit_race_closure.sql"
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_deduct_n_credits_migration_has_balance_guard():
    """Beta Gate Blocker Closure (2026-08-08): this assertion originally
    targeted migrations/smart_contract_analyses.sql. That was the bug -- the
    fix had been written into a migration already applied on 2026-06-11, so
    there was no new artifact for the operator to run and the guard never
    reached production, while this test stayed green the whole time. The
    authoritative definition now lives in its own numbered migration."""
    sql = _migration_107()
    assert "CREATE OR REPLACE FUNCTION public.deduct_n_credits" in sql
    body = sql.split("CREATE OR REPLACE FUNCTION public.deduct_n_credits", 1)[1]
    assert "credits_remaining >= p_n" in body, (
        "deduct_n_credits must gate the UPDATE on sufficient balance, "
        "matching deduct_credit's own WHERE guard"
    )
    assert "GREATEST(0, credits_remaining - p_n)" not in body, (
        "the old unconditional floor-at-0 UPDATE must be gone — it always "
        "'succeeded' regardless of balance"
    )
    assert "RETURN -1" in body, "insufficient-balance/no-row case must return a distinguishable sentinel"


def test_migration_107_rejects_non_positive_amounts():
    """A negative p_n under the pre-107 body INCREASED the balance."""
    body = _migration_107().split("CREATE OR REPLACE FUNCTION public.deduct_n_credits", 1)[1]
    assert "p_n IS NULL OR p_n <= 0" in body


def test_migration_107_hardens_search_path():
    """SECURITY DEFINER without an explicit search_path is a privilege-
    escalation vector; deduct_credit already sets it, deduct_n_credits did not."""
    body = _migration_107().split("CREATE OR REPLACE FUNCTION public.deduct_n_credits", 1)[1]
    assert "SET search_path = public" in body.split("$$", 1)[0]


def test_migration_107_defines_atomic_refund_functions():
    """refund_one_credit was called by shared/deps.py but defined in NO
    migration, so every refund fell through to a read-modify-write fallback
    that could erase a concurrent charge."""
    sql = _migration_107()
    assert "CREATE OR REPLACE FUNCTION public.refund_n_credits" in sql
    assert "CREATE OR REPLACE FUNCTION public.refund_one_credit" in sql
    refund_body = sql.split("CREATE OR REPLACE FUNCTION public.refund_n_credits", 1)[1]
    assert "credits_remaining + p_n" in refund_body, "refund must be a single atomic statement"


def test_migration_107_reasserts_privilege_lockdown():
    """CREATE OR REPLACE preserves ACLs, but the two NEW functions would
    otherwise inherit Postgres's EXECUTE-to-PUBLIC default."""
    sql = _migration_107()
    for fn_sig in (
        "public.deduct_n_credits(UUID, INTEGER)",
        "public.refund_n_credits(UUID, INTEGER)",
        "public.refund_one_credit(UUID)",
    ):
        assert f"REVOKE ALL ON FUNCTION {fn_sig} FROM PUBLIC;" in sql
        assert f"REVOKE ALL ON FUNCTION {fn_sig} FROM anon;" in sql
        assert f"REVOKE ALL ON FUNCTION {fn_sig} FROM authenticated;" in sql
        assert f"GRANT EXECUTE ON FUNCTION {fn_sig} TO service_role;" in sql


def test_superseded_migration_no_longer_defines_the_function():
    """smart_contract_analyses.sql must not contain an executable
    deduct_n_credits definition: filename ordering puts 107_* BEFORE
    smart_contract_analyses.sql, so on a fresh rebuild a definition left there
    would silently overwrite the fixed one and reintroduce the vulnerability."""
    path = os.path.join(os.path.dirname(__file__), "..", "migrations", "smart_contract_analyses.sql")
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    executable = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert "CREATE OR REPLACE FUNCTION public.deduct_n_credits" not in executable
    assert "107_beta_gate_credit_race_closure.sql" in sql, "must point to its successor"


# ─── shared/deps.py::_deduct_n_credits propagates the sentinel ────────────

def test_deps_deduct_n_credits_propagates_insufficient_sentinel():
    from shared import deps

    fake_result = MagicMock()
    fake_result.data = -1  # RPC's new sentinel for "not charged"

    with patch("shared.deps._get_supa") as mock_supa, \
         patch("shared.deps._is_founder", return_value=False), \
         patch("shared.deps._increment_monthly_usage") as mock_incr:
        mock_supa.return_value.rpc.return_value.execute.return_value = fake_result
        result = deps._deduct_n_credits("uid-race-loser", "lawyer@vindex.rs", 6)

    assert result == -1
    mock_incr.assert_not_called(), "a rejected deduction must not count against monthly usage limits"


def test_deps_deduct_n_credits_success_still_increments_usage():
    from shared import deps

    fake_result = MagicMock()
    fake_result.data = 14  # real remaining balance after a successful deduction

    with patch("shared.deps._get_supa") as mock_supa, \
         patch("shared.deps._is_founder", return_value=False), \
         patch("shared.deps._increment_monthly_usage") as mock_incr:
        mock_supa.return_value.rpc.return_value.execute.return_value = fake_result
        result = deps._deduct_n_credits("uid-winner", "lawyer@vindex.rs", 6)

    assert result == 14
    mock_incr.assert_called_once_with("uid-winner")


def test_deps_deduct_n_credits_exception_returns_sentinel_not_zero():
    from shared import deps

    with patch("shared.deps._get_supa", side_effect=RuntimeError("boom")), \
         patch("shared.deps._is_founder", return_value=False):
        result = deps._deduct_n_credits("uid-x", "lawyer@vindex.rs", 6)

    assert result == -1, "an RPC failure must never be indistinguishable from a real 0 balance"


# ─── shared/usage.py::UsageService.consume rejects the race loser ─────────

@pytest.mark.anyio
async def test_consume_rejects_when_deduct_n_credits_signals_insufficient():
    """Simulates the TOCTOU race: the pre-check (_get_credits) saw enough
    balance, but the atomic RPC lost the race and reports -1. consume() must
    raise 402 and must NOT record usage for a charge that never happened."""
    from fastapi import HTTPException
    from shared.usage import UsageService

    policy = _policy(krediti=2, credit_multiplier=6)  # 12 credits needed

    with patch("shared.usage.get_policy", new_callable=AsyncMock, return_value=policy), \
         patch("shared.usage._is_founder", return_value=False), \
         patch("shared.usage._get_credits", return_value=12), \
         patch("shared.usage._deduct_n_credits", return_value=-1) as mock_deduct, \
         patch("shared.usage._increment_usage", new_callable=AsyncMock) as mock_incr_usage, \
         patch("shared.usage._log_usage_event", new_callable=AsyncMock) as mock_log, \
         patch("shared.usage._seconds_since_last_call", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_usage_row", new_callable=AsyncMock, return_value=None), \
         patch("shared.usage._get_monthly_count", new_callable=AsyncMock, return_value=0):
        with pytest.raises(HTTPException) as exc_info:
            await UsageService.consume("uid-race-loser", "lawyer@vindex.rs", "strategija")

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["code"] == "NO_CREDITS"
    mock_deduct.assert_called_once()
    mock_incr_usage.assert_not_called()
    mock_log.assert_not_called()
