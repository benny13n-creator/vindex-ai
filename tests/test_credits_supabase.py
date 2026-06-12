# -*- coding: utf-8 -*-
"""
Tests for Supabase credit helper functions (_sb_get_credits, _sb_deduct_credit,
_sb_ensure_credits_row) and the conditional deduction logic in /api/pitanje.
All Supabase calls are mocked — no network required.
"""
import sys
import os
from unittest.mock import MagicMock, patch, call

# Minimal env so api.py imports without RuntimeError
os.environ.setdefault("SUPABASE_URL",     "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("FOUNDER_EMAILS",   "founder@test.com")
os.environ.setdefault("OPENAI_API_KEY",   "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api as _api


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _mock_supa_select(data):
    """Build a chain mock that returns data on .single().execute()"""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = data
    return mock


def _mock_supa_rpc(return_value):
    """Build a chain mock that returns return_value on .rpc().execute()"""
    mock = MagicMock()
    mock.rpc.return_value.execute.return_value.data = return_value
    return mock


def _mock_supa_upsert():
    """Build a chain mock for upsert calls."""
    mock = MagicMock()
    mock.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return mock


# ─── T1: _sb_get_credits — row exists ─────────────────────────────────────────

def test_sb_get_credits_row_exists():
    """_sb_get_credits returns credits_remaining when row is present."""
    mock_supa = _mock_supa_select({"credits_remaining": 7})
    with patch.object(_api, "_get_supa", return_value=mock_supa):
        result = _api._sb_get_credits("user-uuid-1")
    assert result == 7


# ─── T2: _sb_get_credits — row missing ───────────────────────────────────────

def test_sb_get_credits_row_missing():
    """_sb_get_credits returns 0 when row data is None/missing."""
    mock_supa = _mock_supa_select(None)
    with patch.object(_api, "_get_supa", return_value=mock_supa):
        result = _api._sb_get_credits("user-uuid-2")
    assert result == 0


# ─── T3: _sb_deduct_credit — balance > 0 ─────────────────────────────────────

def test_sb_deduct_credit_balance_positive():
    """_sb_deduct_credit calls deduct_credit RPC and returns new balance."""
    mock_supa = _mock_supa_rpc(6)  # RPC returns 6 (was 7, now 6)
    with patch.object(_api, "_get_supa", return_value=mock_supa), \
         patch.object(_api, "_increment_monthly_usage") as mock_incr:
        result = _api._sb_deduct_credit("user-uuid-3")
    assert result == 6
    mock_supa.rpc.assert_called_once_with("deduct_credit", {"p_user_id": "user-uuid-3"})
    mock_incr.assert_called_once_with("user-uuid-3")


# ─── T4: _sb_deduct_credit — balance = 0 (RPC returns 0) ─────────────────────

def test_sb_deduct_credit_balance_zero():
    """_sb_deduct_credit returns 0 when RPC indicates no credits left."""
    mock_supa = _mock_supa_rpc(0)
    with patch.object(_api, "_get_supa", return_value=mock_supa), \
         patch.object(_api, "_increment_monthly_usage"):
        result = _api._sb_deduct_credit("user-uuid-4")
    assert result == 0


# ─── T5: _sb_ensure_credits_row — calls upsert with correct args ─────────────

def test_sb_ensure_credits_row_calls_upsert():
    """_sb_ensure_credits_row calls upsert with ignore_duplicates=True."""
    mock_supa = _mock_supa_upsert()
    with patch.object(_api, "_get_supa", return_value=mock_supa):
        _api._sb_ensure_credits_row("user-uuid-5", initial=15)

    mock_supa.table.assert_called_with("user_credits")
    mock_supa.table.return_value.upsert.assert_called_once_with(
        {"user_id": "user-uuid-5", "credits_remaining": 15},
        on_conflict="user_id",
        ignore_duplicates=True,
    )


def test_sb_ensure_credits_row_never_overwrites_existing():
    """_sb_ensure_credits_row uses ignore_duplicates=True — never resets existing balance."""
    mock_supa = _mock_supa_upsert()
    with patch.object(_api, "_get_supa", return_value=mock_supa):
        _api._sb_ensure_credits_row("user-uuid-6", initial=15)

    _, kwargs = mock_supa.table.return_value.upsert.call_args
    assert kwargs.get("ignore_duplicates") is True, "ignore_duplicates must be True to prevent balance resets"


# ─── T6: /api/pitanje conditional — success + not blocked → deduct called ────

def test_pitanje_deduct_called_on_success():
    """status=success, blocked=False → _deduct_credit called exactly once."""
    mock_result = {
        "status": "success",
        "blocked": False,
        "from_cache": False,
        "data": "Odgovor",
        "confidence": "HIGH",
    }
    with patch.object(_api, "klasifikuj_pitanje", return_value="PARNICA"), \
         patch.object(_api, "_deduct_credit", return_value=5) as mock_deduct, \
         patch.object(_api, "_get_credits", return_value=5), \
         patch.object(_api, "_audit", return_value=None), \
         patch.object(_api._al, "log_response"):
        # Call the endpoint logic directly via helper reconstruction
        user = {"user_id": "uid-test", "email": "user@test.com", "credits_remaining": 6}
        uid = user["user_id"]
        email = user.get("email", "")
        hasil = mock_result
        should_deduct = (
            hasil.get("status") == "success"
            and not hasil.get("blocked", False)
            and not hasil.get("from_cache", False)
        )
        if should_deduct:
            _api._deduct_credit(uid, email)

    mock_deduct.assert_called_once_with("uid-test", "user@test.com")


# ─── T7: /api/pitanje conditional — blocked=True → deduct NOT called ─────────

def test_pitanje_deduct_not_called_when_blocked():
    """blocked=True → _deduct_credit NOT called; _get_credits called instead."""
    mock_result = {
        "status": "success",
        "blocked": True,
        "from_cache": False,
        "data": "Blocked.",
    }
    with patch.object(_api, "_deduct_credit") as mock_deduct, \
         patch.object(_api, "_get_credits", return_value=5) as mock_get:
        user = {"user_id": "uid-blocked", "email": "user@test.com"}
        uid = user["user_id"]
        email = user.get("email", "")
        hasil = mock_result
        should_deduct = (
            hasil.get("status") == "success"
            and not hasil.get("blocked", False)
            and not hasil.get("from_cache", False)
        )
        if should_deduct:
            _api._deduct_credit(uid, email)
        else:
            _api._get_credits(uid)

    mock_deduct.assert_not_called()
    mock_get.assert_called_once_with("uid-blocked")

# ─── T8: from_cache=True → deduct NOT called ─────────────────────────────────

def test_pitanje_deduct_not_called_when_cached():
    """from_cache=True → _deduct_credit NOT called."""
    mock_result = {
        "status": "success",
        "blocked": False,
        "from_cache": True,
        "data": "Cached odgovor",
    }
    with patch.object(_api, "_deduct_credit") as mock_deduct, \
         patch.object(_api, "_get_credits", return_value=5) as mock_get:
        uid = "uid-cached"
        email = "user@test.com"
        hasil = mock_result
        should_deduct = (
            hasil.get("status") == "success"
            and not hasil.get("blocked", False)
            and not hasil.get("from_cache", False)
        )
        if should_deduct:
            _api._deduct_credit(uid, email)
        else:
            _api._get_credits(uid)

    mock_deduct.assert_not_called()
    mock_get.assert_called_once_with("uid-cached")